from __future__ import annotations

from datetime import datetime, timezone
import os
import re
import sys
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient


ID_FIELDS = {
    "patient_id": "patient",
    "doctor_id": "doctor",
    "_offered_doctor_id": "doctor",
    "appointment_id": "appointment",
}
SPECS = {
    "patient": ("patients", "patient_id", "PC"),
    "doctor": ("doctors", "doctor_id", "DC"),
    "appointment": ("appointments", "appointment_id", "APT"),
}


def _mapping_for(collection, field: str, prefix: str) -> dict[str, str]:
    documents = list(collection.find({field: {"$type": "string"}}, {field: 1}))
    used: set[int] = set()
    pending: list[tuple[str, int | None]] = []
    for document in documents:
        old = str(document.get(field) or "")
        match = re.search(r"(\d+)$", old)
        preferred = int(match.group(1)) if match and int(match.group(1)) > 0 else None
        pending.append((old, preferred))

    mapping: dict[str, str] = {}
    next_number = 1
    for old, preferred in sorted(pending, key=lambda item: (item[1] is None, item[1] or 0, item[0])):
        number = preferred
        if number is None or number in used:
            while next_number in used:
                next_number += 1
            number = next_number
        used.add(number)
        mapping[old] = f"{prefix}{number}"
    return mapping


def _extend_mapping(mapping: dict[str, str], values: set[str], prefix: str) -> None:
    used = {
        int(match.group(1))
        for value in mapping.values()
        if (match := re.fullmatch(rf"{re.escape(prefix)}(\d+)", value))
    }
    next_number = 1
    for old in sorted(values - set(mapping)):
        match = re.search(r"(\d+)$", old)
        preferred = int(match.group(1)) if match and int(match.group(1)) > 0 else None
        number = preferred
        if number is None or number in used:
            while next_number in used:
                next_number += 1
            number = next_number
        used.add(number)
        mapping[old] = f"{prefix}{number}"


def _include_reference_ids(db, mappings: dict[str, dict[str, str]]) -> None:
    doctor_refs = {
        str(item["doctor_id"])
        for collection_name in ("doctor_availability", "appointments", "call_logs")
        for item in db[collection_name].find(
            {"doctor_id": {"$type": "string"}},
            {"doctor_id": 1},
        )
    }
    patient_refs = {
        str(item["patient_id"])
        for collection_name in ("appointments", "call_logs")
        for item in db[collection_name].find(
            {"patient_id": {"$type": "string"}},
            {"patient_id": 1},
        )
    }
    _extend_mapping(mappings["doctor"], doctor_refs, "DC")
    _extend_mapping(mappings["patient"], patient_refs, "PC")


def _rewrite_structured_ids(value: Any, mappings: dict[str, dict[str, str]]) -> Any:
    if isinstance(value, list):
        return [_rewrite_structured_ids(item, mappings) for item in value]
    if not isinstance(value, dict):
        return value

    rewritten: dict[str, Any] = {}
    for key, item in value.items():
        kind = ID_FIELDS.get(key)
        if kind and isinstance(item, str):
            rewritten[key] = mappings[kind].get(item, item)
        else:
            rewritten[key] = _rewrite_structured_ids(item, mappings)
    return rewritten


def _backup_database(client: MongoClient, source_name: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{source_name}_backup_before_compact_ids_{timestamp}"
    source = client[source_name]
    backup = client[backup_name]
    if backup.list_collection_names():
        raise RuntimeError(f"Backup database already exists: {backup_name}")

    for collection_name in source.list_collection_names():
        documents = list(source[collection_name].find({}))
        if documents:
            backup[collection_name].insert_many(documents, ordered=True)
        else:
            backup.create_collection(collection_name)
    backup["_migration_manifest"].insert_one(
        {
            "source_database": source_name,
            "created_at": datetime.now(timezone.utc),
            "purpose": "Backup before APT/DC/PC compact ID migration",
        }
    )
    return backup_name


def _update_primary_ids(db, mappings: dict[str, dict[str, str]]) -> None:
    for kind, (collection_name, field, _) in SPECS.items():
        collection = db[collection_name]
        temporary: list[tuple[str, str]] = []
        for index, (old, new) in enumerate(mappings[kind].items(), start=1):
            if old == new:
                continue
            temp = f"__ID_MIGRATION_{kind}_{index}__"
            collection.update_one({field: old}, {"$set": {field: temp}})
            temporary.append((temp, new))
        for temp, new in temporary:
            collection.update_one({field: temp}, {"$set": {field: new}})


def _update_references(db, mappings: dict[str, dict[str, str]]) -> None:
    for old, new in mappings["doctor"].items():
        if old != new:
            db.doctor_availability.update_many({"doctor_id": old}, {"$set": {"doctor_id": new}})
            db.appointments.update_many({"doctor_id": old}, {"$set": {"doctor_id": new}})
            db.call_logs.update_many({"doctor_id": old}, {"$set": {"doctor_id": new}})
    for old, new in mappings["patient"].items():
        if old != new:
            db.appointments.update_many({"patient_id": old}, {"$set": {"patient_id": new}})
            db.call_logs.update_many({"patient_id": old}, {"$set": {"patient_id": new}})

    for collection_name in ("call_logs", "sessions"):
        collection = db[collection_name]
        for document in collection.find({}):
            rewritten = _rewrite_structured_ids(document, mappings)
            rewritten.pop("_id", None)
            collection.replace_one({"_id": document["_id"]}, rewritten)


def _verify(db) -> None:
    patients = {item["patient_id"] for item in db.patients.find({}, {"patient_id": 1})}
    doctors = {item["doctor_id"] for item in db.doctors.find({}, {"doctor_id": 1})}
    appointments = {
        item["appointment_id"]
        for item in db.appointments.find({}, {"appointment_id": 1})
    }
    if any(not re.fullmatch(r"PC[1-9]\d*", value) for value in patients):
        raise RuntimeError("Patient ID verification failed.")
    if any(not re.fullmatch(r"DC[1-9]\d*", value) for value in doctors):
        raise RuntimeError("Doctor ID verification failed.")
    if any(not re.fullmatch(r"APT[1-9]\d*", value) for value in appointments):
        raise RuntimeError("Appointment ID verification failed.")

    dangling_patients = db.appointments.count_documents(
        {"patient_id": {"$nin": list(patients), "$ne": None}}
    )
    dangling_doctors = db.appointments.count_documents(
        {"doctor_id": {"$nin": list(doctors), "$ne": None}}
    )
    noncanonical_availability = db.doctor_availability.count_documents(
        {"doctor_id": {"$not": re.compile(r"^DC[1-9]\d*$")}}
    )
    if dangling_patients or dangling_doctors or noncanonical_availability:
        raise RuntimeError(
            "Reference verification failed: "
            f"patients={dangling_patients}, doctors={dangling_doctors}, "
            f"noncanonical_availability={noncanonical_availability}"
        )


def main() -> int:
    load_dotenv(".env")
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name = os.getenv("MONGODB_DB_NAME", "voice_agent")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[database_name]

    mappings = {
        kind: _mapping_for(db[collection], field, prefix)
        for kind, (collection, field, prefix) in SPECS.items()
    }
    _include_reference_ids(db, mappings)
    backup_name = _backup_database(client, database_name)
    print(f"Backup created: {backup_name}")
    _update_primary_ids(db, mappings)
    _update_references(db, mappings)
    _verify(db)
    for kind in ("appointment", "doctor", "patient"):
        changed = sum(old != new for old, new in mappings[kind].items())
        print(f"{kind}: migrated {changed} IDs")
    print("Compact ID migration completed and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
