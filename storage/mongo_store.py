from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any
import hashlib
import re
import secrets

from bson import ObjectId
from gridfs import GridFSBucket
from gridfs.errors import NoFile
from pymongo import MongoClient
from pymongo.collection import Collection


WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ORDER = {day: idx for idx, day in enumerate(WEEK_DAYS)}
SLOT_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class MongoStore:
    def __init__(self, uri: str, db_name: str):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.patients: Collection = self.db["patients"]
        self.doctors: Collection = self.db["doctors"]
        self.doctor_availability: Collection = self.db["doctor_availability"]
        self.appointments: Collection = self.db["appointments"]
        self.call_logs: Collection = self.db["call_logs"]
        self.sessions: Collection = self.db["sessions"]
        self.admin_users: Collection = self.db["admin_users"]
        self.call_recordings = GridFSBucket(self.db, bucket_name="call_recordings")

        self._create_indexes()
        self._backfill_external_ids()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_availability(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []

        day_to_slots: dict[str, set[str]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            day = str(item.get("day") or "").strip()
            if day not in DAY_ORDER:
                continue

            raw_slots = item.get("slots")
            if raw_slots is None:
                raw_slots = item.get("timeslots") or []
            if not isinstance(raw_slots, list):
                raw_slots = []

            if day not in day_to_slots:
                day_to_slots[day] = set()
            for slot in raw_slots:
                slot_text = str(slot).strip()
                if SLOT_PATTERN.match(slot_text):
                    day_to_slots[day].add(slot_text)

        normalized: list[dict[str, Any]] = []
        for day in sorted(day_to_slots.keys(), key=lambda d: DAY_ORDER[d]):
            sorted_slots = sorted(day_to_slots[day])
            if sorted_slots:
                normalized.append({"day": day, "slots": sorted_slots})
        return normalized

    @staticmethod
    def _clean_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _create_indexes(self):
        self.patients.create_index("patient_id", unique=True, sparse=True)
        self.patients.create_index("name")
        self.patients.create_index("phone")

        self.doctors.create_index("doctor_id", unique=True, sparse=True)
        self.doctors.create_index("name")
        self.doctors.create_index("urdu_name")
        self.doctors.create_index("department")
        self.doctors.create_index("qualification")

        self.doctor_availability.create_index("doctor_id", unique=True)
        self.appointments.create_index("appointment_id", unique=True, sparse=True)
        self.appointments.create_index("scheduled_for")
        self.appointments.create_index("patient_id")
        self.appointments.create_index("doctor_id")
        self.appointments.create_index("source_session_id", unique=True, sparse=True)

        self.call_logs.create_index("created_at")
        self.call_logs.create_index("session_id")
        self.sessions.create_index("session_id", unique=True)

        self.admin_users.create_index("username", unique=True)

    def _backfill_external_ids(self):
        patient_id_by_oid: dict[str, str] = {}
        doctor_id_by_oid: dict[str, str] = {}

        for patient in self.patients.find({}):
            pid = patient.get("patient_id")
            if not pid:
                pid = self._next_patient_id()
                self.patients.update_one({"_id": patient["_id"]}, {"$set": {"patient_id": pid}})
            patient_id_by_oid[str(patient["_id"])] = pid

        for doctor in self.doctors.find({}):
            did = doctor.get("doctor_id")
            doctor_updates: dict[str, Any] = {}
            if not did:
                did = self._next_doctor_id()
                doctor_updates["doctor_id"] = did
            if "specialization" not in doctor:
                doctor_updates["specialization"] = None
            if "urdu_name" not in doctor:
                doctor_updates["urdu_name"] = None
            if "qualification" not in doctor:
                doctor_updates["qualification"] = None
            if doctor_updates:
                self.doctors.update_one({"_id": doctor["_id"]}, {"$set": doctor_updates})
            doctor_id_by_oid[str(doctor["_id"])] = did
            if self.doctor_availability.count_documents({"doctor_id": did}) == 0:
                self._set_doctor_availability(did, doctor.get("availability"))

        for appt in self.appointments.find({}):
            updates: dict[str, Any] = {}
            patient_ref = appt.get("patient_id")
            doctor_ref = appt.get("doctor_id")
            if isinstance(patient_ref, str) and patient_ref in patient_id_by_oid:
                updates["patient_id"] = patient_id_by_oid[patient_ref]
            if isinstance(doctor_ref, str) and doctor_ref in doctor_id_by_oid:
                updates["doctor_id"] = doctor_id_by_oid[doctor_ref]
            if updates:
                updates["updated_at"] = self._now()
                self.appointments.update_one({"_id": appt["_id"]}, {"$set": updates})

        for log in self.call_logs.find({}):
            updates: dict[str, Any] = {}
            patient_ref = log.get("patient_id")
            doctor_ref = log.get("doctor_id")
            if isinstance(patient_ref, str) and patient_ref in patient_id_by_oid:
                updates["patient_id"] = patient_id_by_oid[patient_ref]
            if isinstance(doctor_ref, str) and doctor_ref in doctor_id_by_oid:
                updates["doctor_id"] = doctor_id_by_oid[doctor_ref]
            if updates:
                self.call_logs.update_one({"_id": log["_id"]}, {"$set": updates})

    def _next_prefixed_id(self, *, collection: Collection, field: str, prefix: str) -> str:
        max_num = 0
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        for doc in collection.find({field: {"$regex": rf"^{re.escape(prefix)}\d+$"}}):
            match = pattern.match(str(doc.get(field) or ""))
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"{prefix}{max_num + 1}"

    def _next_patient_id(self) -> str:
        return self._next_prefixed_id(collection=self.patients, field="patient_id", prefix="PC")

    def _next_doctor_id(self) -> str:
        return self._next_prefixed_id(collection=self.doctors, field="doctor_id", prefix="DC")

    def _next_appointment_id(self) -> str:
        return self._next_prefixed_id(collection=self.appointments, field="appointment_id", prefix="APT")

    @staticmethod
    def _serialize_patient(doc: dict[str, Any]) -> dict[str, Any]:
        out = dict(doc)
        out.pop("_id", None)
        out["id"] = out.get("patient_id")
        return out

    @staticmethod
    def _serialize_doctor(doc: dict[str, Any], availability: list[dict[str, Any]]) -> dict[str, Any]:
        out = dict(doc)
        out.pop("_id", None)
        out["id"] = out.get("doctor_id")
        out["availability"] = availability
        return out

    @staticmethod
    def _serialize_appointment(doc: dict[str, Any]) -> dict[str, Any]:
        out = dict(doc)
        if "_id" in out:
            out["id"] = str(out.pop("_id"))
        return out

    @staticmethod
    def _serialize_call_log(doc: dict[str, Any]) -> dict[str, Any]:
        out = dict(doc)
        if "_id" in out:
            out["id"] = str(out.pop("_id"))
        if isinstance(out.get("recording_file_id"), ObjectId):
            out["recording_file_id"] = str(out["recording_file_id"])
        return out

    def _availability_map(self) -> dict[str, list[dict[str, Any]]]:
        mapping: dict[str, list[dict[str, Any]]] = {}
        for doc in self.doctor_availability.find({}):
            doctor_id = doc.get("doctor_id")
            if not doctor_id:
                continue
            mapping[doctor_id] = self._normalize_availability(doc.get("availability"))
        return mapping

    def _set_doctor_availability(self, doctor_id: str, availability: Any):
        normalized = self._normalize_availability(availability)
        now = self._now()
        self.doctor_availability.update_one(
            {"doctor_id": doctor_id},
            {
                "$set": {
                    "doctor_id": doctor_id,
                    "availability": normalized,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def append_session(self, session_id: str, role: str, content: str):
        self.sessions.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "history": {
                        "role": role,
                        "content": content,
                        "created_at": self._now(),
                    }
                },
                "$setOnInsert": {"created_at": self._now()},
            },
            upsert=True,
        )

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.find_one({"session_id": session_id}) or {"session_id": session_id, "history": []}
        if "_id" in session:
            session["id"] = str(session.pop("_id"))
        return session

    def update_session_state(
        self,
        session_id: str,
        *,
        active_intent: str | None,
        last_intent: str,
        awaiting_final_confirmation: bool,
        entities: dict[str, Any],
        missing_fields: list[str],
    ):
        self.sessions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "state.active_intent": active_intent,
                    "state.last_intent": last_intent,
                    "state.awaiting_final_confirmation": awaiting_final_confirmation,
                    "state.entities": entities,
                    "state.missing_fields": missing_fields,
                    "updated_at": self._now(),
                },
                "$setOnInsert": {"created_at": self._now()},
            },
            upsert=True,
        )

    def complete_session(self, session_id: str):
        now = self._now()
        self.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "Completed", "completed_at": now, "updated_at": now}},
        )
        self.call_logs.update_one(
            {"session_id": session_id},
            {"$set": {"status": "Completed", "completed_at": now, "updated_at": now}},
        )

    def _resolve_patient(self, entities: dict[str, Any]) -> str | None:
        provided_patient_id = str(entities.get("patient_id") or "").strip().upper()
        if provided_patient_id:
            patient = self.patients.find_one({"patient_id": provided_patient_id})
            return patient.get("patient_id") if patient else None

        patient_name = entities.get("patient_name")
        phone = entities.get("phone")
        if not patient_name and not phone:
            return None

        query: dict[str, Any] = {}
        if phone:
            query["phone"] = phone
        elif patient_name:
            query["name"] = patient_name

        now = self._now()
        patient = self.patients.find_one(query)
        if patient:
            update_fields = {"updated_at": now}
            if patient_name:
                update_fields["name"] = patient_name
            if phone:
                update_fields["phone"] = phone
            self.patients.update_one({"_id": patient["_id"]}, {"$set": update_fields})
            return patient.get("patient_id")

        patient_id = self._next_patient_id()
        self.patients.insert_one(
            {
                "patient_id": patient_id,
                "name": patient_name or "Unknown Patient",
                "phone": phone,
                "created_at": now,
                "updated_at": now,
                "conditions": [entities.get("reason")] if entities.get("reason") else [],
                "status": "Active",
            }
        )
        return patient_id

    def _resolve_doctor(self, entities: dict[str, Any]) -> str | None:
        doctor_id = str(entities.get("doctor_id") or "").strip()
        if doctor_id:
            doctor = self.doctors.find_one({"doctor_id": doctor_id})
            if doctor:
                return doctor.get("doctor_id")

        doctor_name = str(entities.get("doctor_name") or "").strip()
        if not doctor_name:
            return None

        query: dict[str, Any] = {
            "name": {"$regex": f"^{re.escape(doctor_name)}$", "$options": "i"}
        }
        department = str(entities.get("department") or "").strip()
        if department:
            query["department"] = {
                "$regex": f"^{re.escape(department)}$",
                "$options": "i",
            }

        doctor = self.doctors.find_one(query)
        if doctor:
            return doctor.get("doctor_id")
        return None

    @staticmethod
    def _extract_appointment_date_and_slot(entities: dict[str, Any]) -> tuple[str | None, str | None]:
        date = str(entities.get("date") or "").strip()
        slot = str(entities.get("time") or "").strip()
        return (date or None), (slot or None)

    @staticmethod
    def _parse_scheduled_for(entities: dict[str, Any]) -> str | None:
        date = entities.get("date") or entities.get("natural_date")
        time = entities.get("time") or entities.get("natural_time")
        if date and time:
            return f"{date} {time}"
        if date:
            return str(date)
        if time:
            return str(time)
        return None

    @staticmethod
    def _parse_scheduled_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None

        text = text.replace("/", "-")
        formats = [
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _handle_appointment(
        self,
        intent_name: str,
        entities: dict[str, Any],
        patient_id: str | None,
        doctor_id: str | None,
        session_id: str | None = None,
    ) -> str | None:
        now = self._now()
        appointment_id = entities.get("appointment_id")

        if intent_name == "book_appointment":
            if session_id:
                existing_booking = self.appointments.find_one(
                    {"source_session_id": session_id}
                )
                if existing_booking:
                    return str(existing_booking["_id"])
            appointment_date, slot = self._extract_appointment_date_and_slot(entities)
            if not doctor_id or not appointment_date or not slot:
                return None
            doctor, scheduled_for = self._validate_doctor_slot(
                doctor_id=doctor_id,
                appointment_date=appointment_date,
                slot=slot,
            )
            document = {
                "appointment_id": appointment_id or self._next_appointment_id(),
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "department": doctor.get("department"),
                "scheduled_for": scheduled_for,
                "reason": entities.get("reason"),
                "status": "Booked",
                **({"source_session_id": session_id} if session_id else {}),
                "created_at": now,
                "updated_at": now,
            }
            inserted = self.appointments.insert_one(document)
            return str(inserted.inserted_id)

        if intent_name in {"reschedule_appointment", "cancel_appointment"}:
            if not appointment_id:
                return None

            appt = self.appointments.find_one({"appointment_id": appointment_id})
            if not appt:
                return None

            updates: dict[str, Any] = {"updated_at": now}
            if intent_name == "reschedule_appointment":
                appointment_date, slot = self._extract_appointment_date_and_slot(entities)
                if not appointment_date or not slot or not appt.get("doctor_id"):
                    return None
                doctor, scheduled_for = self._validate_doctor_slot(
                    doctor_id=appt.get("doctor_id"),
                    appointment_date=appointment_date,
                    slot=slot,
                    exclude_id=str(appt["_id"]),
                )
                updates["department"] = doctor.get("department")
                updates["scheduled_for"] = scheduled_for
                updates["status"] = "Rescheduled"
            else:
                if str(appt.get("status") or "").lower() == "cancelled":
                    return str(appt["_id"])
                updates["status"] = "Cancelled"
            self.appointments.update_one({"_id": appt["_id"]}, {"$set": updates})
            return str(appt["_id"])

        return None

    def persist_turn(
        self,
        *,
        session_id: str,
        transcript: str,
        intent_name: str,
        confidence: float,
        entities: dict[str, Any],
        assistant_text: str,
        audio_mime: str | None,
        persist_appointment: bool = True,
    ):
        doctor_id = self._resolve_doctor(entities)
        patient_id = None
        appointment_id = None

        # A patient is a committed booking record, not a partial conversation
        # record. Never create one while the agent is still collecting or
        # clarifying fields. Also reuse an already committed booking for this
        # session before resolving the patient, so retries cannot create a
        # second patient with a differently transcribed phone number.
        if persist_appointment:
            existing_booking = (
                self.appointments.find_one({"source_session_id": session_id})
                if intent_name == "book_appointment" and session_id
                else None
            )
            if existing_booking:
                patient_id = existing_booking.get("patient_id")
                doctor_id = existing_booking.get("doctor_id") or doctor_id
                appointment_id = str(existing_booking["_id"])
            else:
                if intent_name == "book_appointment":
                    patient_id = self._resolve_patient(entities)
                appointment_id = self._handle_appointment(
                    intent_name,
                    entities,
                    patient_id,
                    doctor_id,
                    session_id=session_id,
                )

        now = self._now()
        turn = {
            "transcript": transcript,
            "assistant_text": assistant_text,
            "intent": intent_name,
            "confidence": confidence,
            "entities": entities,
            "created_at": now,
        }
        latest_fields = {
            "session_id": session_id,
            # These top-level fields are the accumulated/latest view used by
            # the existing dashboard. The full exchange is retained in turns.
            "transcript": "\n".join(
                item.get("content", "")
                for item in self.get_session(session_id).get("history", [])
                if item.get("role") == "user"
            ),
            "assistant_text": assistant_text,
            "intent": intent_name,
            "confidence": confidence,
            "entities": entities,
            "audio_mime": audio_mime,
            "status": "In Progress",
            "updated_at": now,
        }
        # Do not erase committed references on a later non-booking turn (for
        # example, when the caller says goodbye after the booking).
        if patient_id is not None:
            latest_fields["patient_id"] = patient_id
        if doctor_id is not None:
            latest_fields["doctor_id"] = doctor_id
        if appointment_id is not None:
            latest_fields["appointment_id_ref"] = appointment_id

        self.call_logs.update_one(
            {"session_id": session_id},
            {
                "$set": latest_fields,
                "$setOnInsert": {"created_at": now},
                "$push": {"turns": turn},
            },
            upsert=True,
        )

    def get_doctors(self) -> list[dict[str, Any]]:
        docs = list(self.doctors.find({}).sort("name", 1))
        availability_map = self._availability_map()
        out: list[dict[str, Any]] = []
        for doc in docs:
            doctor_id = doc.get("doctor_id")
            availability = availability_map.get(doctor_id, [])
            out.append(self._serialize_doctor(doc, availability))
        return out

    def get_doctor_by_id(self, doctor_id: str) -> dict[str, Any] | None:
        doc = self.doctors.find_one({"doctor_id": doctor_id})
        if not doc:
            return None
        availability_map = self._availability_map()
        return self._serialize_doctor(doc, availability_map.get(doctor_id, []))

    def create_doctor(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        doctor_id = self._next_doctor_id()
        doc = {
            "doctor_id": doctor_id,
            "name": payload["name"].strip(),
            "urdu_name": self._clean_optional_text(payload.get("urdu_name")),
            "department": self._clean_optional_text(payload.get("department")),
            "specialization": self._clean_optional_text(payload.get("specialization")),
            "qualification": self._clean_optional_text(payload.get("qualification")),
            "status": payload.get("status") or "Available",
            "created_at": now,
            "updated_at": now,
        }
        self.doctors.insert_one(doc)
        self._set_doctor_availability(doctor_id, payload.get("availability"))
        return self._serialize_doctor(doc, self._normalize_availability(payload.get("availability")))

    def update_doctor(self, doctor_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.doctors.find_one({"doctor_id": doctor_id})
        if not existing:
            return None

        update_fields: dict[str, Any] = {"updated_at": self._now()}
        for key in ["name", "urdu_name", "department", "specialization", "qualification", "status"]:
            if key in payload and payload[key] is not None:
                value = payload[key].strip() if key in {"name", "status"} and isinstance(payload[key], str) else payload[key]
                if key in {"urdu_name", "department", "specialization", "qualification"}:
                    value = self._clean_optional_text(payload[key])
                update_fields[key] = value

        self.doctors.update_one({"doctor_id": doctor_id}, {"$set": update_fields})
        if "availability" in payload and payload["availability"] is not None:
            self._set_doctor_availability(doctor_id, payload.get("availability"))

        updated = self.doctors.find_one({"doctor_id": doctor_id})
        availability_map = self._availability_map()
        return self._serialize_doctor(updated or {}, availability_map.get(doctor_id, []))

    def delete_doctor(self, doctor_id: str) -> bool:
        self.appointments.update_many({"doctor_id": doctor_id}, {"$set": {"doctor_id": None, "updated_at": self._now()}})
        self.call_logs.update_many({"doctor_id": doctor_id}, {"$set": {"doctor_id": None}})
        self.doctor_availability.delete_one({"doctor_id": doctor_id})
        deleted = self.doctors.delete_one({"doctor_id": doctor_id})
        return deleted.deleted_count > 0

    def get_patients(self) -> list[dict[str, Any]]:
        docs = list(self.patients.find({}).sort("updated_at", -1))
        return [self._serialize_patient(doc) for doc in docs]

    def create_patient(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        doc = {
            "patient_id": self._next_patient_id(),
            "name": payload["name"].strip(),
            "phone": payload.get("phone"),
            "conditions": payload.get("conditions") or [],
            "status": payload.get("status") or "Active",
            "created_at": now,
            "updated_at": now,
        }
        self.patients.insert_one(doc)
        return self._serialize_patient(doc)

    def get_patient_by_id(self, patient_id: str) -> dict[str, Any] | None:
        doc = self.patients.find_one({"patient_id": patient_id})
        if not doc:
            return None
        return self._serialize_patient(doc)

    def update_patient(self, patient_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.patients.find_one({"patient_id": patient_id})
        if not existing:
            return None

        update_fields: dict[str, Any] = {"updated_at": self._now()}
        for key in ["name", "phone", "status", "conditions"]:
            if key in payload and payload[key] is not None:
                value = payload[key].strip() if isinstance(payload[key], str) else payload[key]
                update_fields[key] = value

        self.patients.update_one({"patient_id": patient_id}, {"$set": update_fields})
        updated = self.patients.find_one({"patient_id": patient_id})
        return self._serialize_patient(updated or {})

    def delete_patient(self, patient_id: str) -> bool:
        self.appointments.update_many({"patient_id": patient_id}, {"$set": {"patient_id": None, "updated_at": self._now()}})
        self.call_logs.update_many({"patient_id": patient_id}, {"$set": {"patient_id": None}})
        deleted = self.patients.delete_one({"patient_id": patient_id})
        return deleted.deleted_count > 0

    def get_appointments(self) -> list[dict[str, Any]]:
        docs = list(self.appointments.find({}).sort("updated_at", -1))
        return [self._serialize_appointment(doc) for doc in docs]

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        docs = list(self.appointments.find({"patient_id": patient_id}).sort("updated_at", -1))
        return [self._serialize_appointment(doc) for doc in docs]

    def create_manual_appointment(self, payload: dict[str, Any]) -> dict[str, Any]:
        patient_type = payload.get("patient_type")
        doctor_id = payload.get("doctor_id")
        appointment_date = str(payload.get("appointment_date") or "").strip()
        slot = payload.get("slot")
        reason = payload.get("reason")

        if patient_type not in {"new", "old"}:
            raise ValueError("Invalid patient type.")
        if not doctor_id:
            raise ValueError("Doctor is required.")
        if not appointment_date:
            raise ValueError("Appointment date is required.")
        if not isinstance(slot, str) or not SLOT_PATTERN.match(slot.strip()):
            raise ValueError("Valid slot is required.")

        try:
            date_obj = datetime.strptime(appointment_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Appointment date must be in YYYY-MM-DD format.")
        day = date_obj.strftime("%A")

        patient_payload: dict[str, Any] | None = None
        patient_id: str | None = None
        if patient_type == "old":
            provided_patient_id = str(payload.get("patient_id") or "").strip()
            patient = self.get_patient_by_id(provided_patient_id)
            if not patient:
                raise ValueError("Patient not found for provided patient ID.")
            patient_id = patient.get("patient_id")
        else:
            incoming = payload.get("patient")
            if not isinstance(incoming, dict):
                raise ValueError("Patient details are required.")
            name = str(incoming.get("name") or "").strip()
            if not name:
                raise ValueError("Patient name is required.")
            patient_payload = incoming

        doctor = self.get_doctor_by_id(doctor_id)
        if not doctor:
            raise ValueError("Doctor not found.")

        available_slots: list[str] = []
        for row in doctor.get("availability") or []:
            if row.get("day") == day:
                available_slots = [str(value) for value in row.get("slots") or []]
                break
        if slot not in available_slots:
            raise ValueError("Selected slot is not available for this doctor.")

        scheduled_for = f"{appointment_date} {slot}"
        clash = self.appointments.find_one(
            {
                "doctor_id": doctor_id,
                "scheduled_for": scheduled_for,
                "status": {"$nin": ["Cancelled"]},
            }
        )
        if clash:
            raise ValueError("Selected slot is already booked.")

        if patient_type == "new":
            assert patient_payload is not None
            created = self.create_patient(
                {
                    "name": str(patient_payload.get("name") or "").strip(),
                    "phone": patient_payload.get("phone"),
                    "conditions": patient_payload.get("conditions") or [],
                    "status": patient_payload.get("status") or "Active",
                }
            )
            patient_id = created.get("patient_id")

        now = self._now()
        doc = {
            "appointment_id": self._next_appointment_id(),
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "department": doctor.get("department"),
            "scheduled_for": scheduled_for,
            "reason": reason,
            "status": "Booked",
            "created_at": now,
            "updated_at": now,
        }
        inserted = self.appointments.insert_one(doc)
        created = self.appointments.find_one({"_id": inserted.inserted_id}) or doc
        return self._serialize_appointment(created)

    def _validate_doctor_slot(self, *, doctor_id: str, appointment_date: str, slot: str, exclude_id: str | None = None):
        doctor = self.get_doctor_by_id(doctor_id)
        if not doctor:
            raise ValueError("Doctor not found.")

        try:
            date_obj = datetime.strptime(appointment_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Appointment date must be in YYYY-MM-DD format.")
        day = date_obj.strftime("%A")

        available_slots: list[str] = []
        for row in doctor.get("availability") or []:
            if row.get("day") == day:
                available_slots = [str(value) for value in row.get("slots") or []]
                break
        if slot not in available_slots:
            raise ValueError("Selected slot is not available for this doctor.")

        scheduled_for = f"{appointment_date} {slot}"
        clash_query: dict[str, Any] = {
            "doctor_id": doctor_id,
            "scheduled_for": scheduled_for,
            "status": {"$nin": ["Cancelled"]},
        }
        clash = self.appointments.find_one(clash_query)
        if clash and (exclude_id is None or str(clash.get("_id")) != exclude_id):
            raise ValueError("Selected slot is already booked.")

        return doctor, scheduled_for

    def cancel_appointment(self, appt_id: str) -> dict[str, Any] | None:
        if not ObjectId.is_valid(appt_id):
            return None
        oid = ObjectId(appt_id)
        result = self.appointments.update_one(
            {"_id": oid},
            {"$set": {"status": "Cancelled", "updated_at": self._now()}},
        )
        if result.matched_count == 0:
            return None
        updated = self.appointments.find_one({"_id": oid})
        return self._serialize_appointment(updated or {})

    def delete_appointment(self, appointment_identifier: str) -> bool:
        identifier = str(appointment_identifier or "").strip()
        if not identifier:
            return False
        query: dict[str, Any]
        if ObjectId.is_valid(identifier):
            query = {"_id": ObjectId(identifier)}
        else:
            query = {"appointment_id": identifier.upper()}
        deleted = self.appointments.delete_one(query)
        return deleted.deleted_count > 0

    def update_appointment(self, appt_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not ObjectId.is_valid(appt_id):
            return None
        oid = ObjectId(appt_id)
        current = self.appointments.find_one({"_id": oid})
        if not current:
            return None

        update_fields: dict[str, Any] = {"updated_at": self._now()}
        if "reason" in payload and payload.get("reason") is not None:
            update_fields["reason"] = payload.get("reason")
        if "status" in payload and payload.get("status") is not None:
            update_fields["status"] = payload.get("status")

        doctor_id = payload.get("doctor_id") or current.get("doctor_id")
        next_date = payload.get("appointment_date")
        next_slot = payload.get("slot")

        current_scheduled = str(current.get("scheduled_for") or "")
        current_date = ""
        current_slot = ""
        parts = current_scheduled.split(" ")
        if len(parts) >= 2:
            current_date = parts[0]
            current_slot = parts[1]

        appointment_date = next_date or current_date
        slot = next_slot or current_slot

        slot_or_date_or_doctor_changed = bool(next_date or next_slot or payload.get("doctor_id"))
        if slot_or_date_or_doctor_changed:
            if not appointment_date or not slot:
                raise ValueError("Appointment date and slot are required for update.")
            doctor, scheduled_for = self._validate_doctor_slot(
                doctor_id=doctor_id,
                appointment_date=appointment_date,
                slot=slot,
                exclude_id=str(oid),
            )
            update_fields["doctor_id"] = doctor_id
            update_fields["department"] = doctor.get("department")
            update_fields["scheduled_for"] = scheduled_for

        self.appointments.update_one({"_id": oid}, {"$set": update_fields})
        updated = self.appointments.find_one({"_id": oid})
        return self._serialize_appointment(updated or {})

    def get_call_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        docs = list(self.call_logs.find({}).sort("created_at", -1).limit(limit))
        return [self._serialize_call_log(doc) for doc in docs]

    def save_call_recording(
        self,
        *,
        session_id: str,
        audio_bytes: bytes,
        content_type: str,
        filename: str,
        duration_seconds: float | None = None,
    ) -> str:
        if not audio_bytes:
            raise ValueError("Call recording is empty.")

        existing = self.call_logs.find_one(
            {"session_id": session_id},
            {"recording_file_id": 1},
        )
        if not existing:
            raise ValueError("Call session was not found.")
        previous_file_id = (existing or {}).get("recording_file_id")
        file_id = self.call_recordings.upload_from_stream(
            filename or f"{session_id}.webm",
            BytesIO(audio_bytes),
            metadata={
                "session_id": session_id,
                "content_type": content_type or "audio/webm",
            },
        )
        self.call_logs.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "recording_file_id": file_id,
                    "recording_mime": content_type or "audio/webm",
                    "recording_size": len(audio_bytes),
                    **(
                        {"recording_duration_seconds": round(float(duration_seconds), 3)}
                        if duration_seconds is not None and duration_seconds > 0
                        else {}
                    ),
                    "updated_at": self._now(),
                }
            },
            upsert=False,
        )

        if previous_file_id and previous_file_id != file_id:
            try:
                self.call_recordings.delete(previous_file_id)
            except NoFile:
                pass
        return str(file_id)

    def open_call_recording(self, session_id: str):
        call_log = self.call_logs.find_one(
            {"session_id": session_id},
            {"recording_file_id": 1, "recording_mime": 1},
        )
        file_id = (call_log or {}).get("recording_file_id")
        if not file_id:
            return None
        try:
            stream = self.call_recordings.open_download_stream(file_id)
        except NoFile:
            return None
        metadata = stream.metadata or {}
        mime = (
            (call_log or {}).get("recording_mime")
            or metadata.get("content_type")
            or "audio/webm"
        )
        return stream, mime

    def get_dashboard_summary(self) -> dict[str, Any]:
        total_appointments = self.appointments.count_documents({})
        active_doctors = self.doctors.count_documents({"status": "Available"})
        calls_today = self.call_logs.count_documents(
            {"created_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)}}
        )

        today = datetime.now().date()
        doctors = {d.get("doctor_id"): d for d in self.get_doctors()}
        patients = {p.get("patient_id"): p for p in self.get_patients()}

        enriched_today: list[tuple[datetime, dict[str, Any]]] = []
        for appt in self.get_appointments():
            scheduled_dt = self._parse_scheduled_datetime(appt.get("scheduled_for"))
            if not scheduled_dt:
                continue
            if scheduled_dt.date() != today:
                continue
            if str(appt.get("status") or "").lower() == "cancelled":
                continue

            doctor = doctors.get(appt.get("doctor_id"))
            patient = patients.get(appt.get("patient_id"))
            enriched_today.append(
                (
                    scheduled_dt,
                    {
                        **appt,
                        "doctor_name": doctor.get("name") if doctor else None,
                        "patient_name": patient.get("name") if patient else None,
                        "patient_phone": patient.get("phone") if patient else None,
                    },
                )
            )

        enriched_today.sort(key=lambda pair: pair[0])
        upcoming = [row for _, row in enriched_today[:6]]
        recent_calls = self.get_call_logs(limit=6)
        return {
            "stats": {
                "total_appointments": total_appointments,
                "active_doctors": active_doctors,
                "calls_today": calls_today,
                "system_status": "Online" if self.ping() else "Degraded",
            },
            "upcoming_appointments": upcoming,
            "recent_calls": recent_calls,
        }

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()

    @staticmethod
    def _public_admin(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "admin_id": user.get("admin_id"),
            "name": user.get("name"),
            "username": user.get("username"),
            "profile_picture": user.get("profile_picture"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
        }

    def create_admin_user(self, *, name: str, username: str, password: str) -> dict[str, Any]:
        now = self._now()
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        admin_id = self._next_prefixed_id(collection=self.admin_users, field="admin_id", prefix="ADM")
        doc = {
            "admin_id": admin_id,
            "name": name.strip(),
            "username": username.strip().lower(),
            "password_hash": password_hash,
            "password_salt": salt,
            "created_at": now,
            "updated_at": now,
        }
        self.admin_users.insert_one(doc)
        return self._public_admin(doc)

    def get_admin_user(self, *, username: str) -> dict[str, Any] | None:
        user = self.admin_users.find_one({"username": username.strip().lower()})
        return self._public_admin(user) if user else None

    def update_admin_user(
        self,
        *,
        current_username: str,
        name: str,
        username: str,
    ) -> dict[str, Any] | None:
        current = self.admin_users.find_one(
            {"username": current_username.strip().lower()}
        )
        if not current:
            return None
        self.admin_users.update_one(
            {"_id": current["_id"]},
            {
                "$set": {
                    "name": name.strip(),
                    "username": username.strip().lower(),
                    "updated_at": self._now(),
                }
            },
        )
        updated = self.admin_users.find_one({"_id": current["_id"]})
        return self._public_admin(updated or current)

    def set_admin_profile_picture(
        self,
        *,
        username: str,
        profile_picture: str,
    ) -> dict[str, Any] | None:
        user = self.admin_users.find_one({"username": username.strip().lower()})
        if not user:
            return None
        self.admin_users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "profile_picture": profile_picture,
                    "updated_at": self._now(),
                }
            },
        )
        updated = self.admin_users.find_one({"_id": user["_id"]})
        return self._public_admin(updated or user)

    def authenticate_admin(self, *, username: str, password: str) -> dict[str, Any] | None:
        user = self.admin_users.find_one({"username": username.strip().lower()})
        if not user:
            return None
        expected = user.get("password_hash")
        salt = user.get("password_salt")
        if not expected or not salt:
            return None
        if self._hash_password(password, salt) != expected:
            return None
        return self._public_admin(user)

    def reset_admin_password(self, *, username: str, new_password: str) -> bool:
        user = self.admin_users.find_one({"username": username.strip().lower()})
        if not user:
            return False
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(new_password, salt)
        result = self.admin_users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": password_hash, "password_salt": salt, "updated_at": self._now()}},
        )
        return result.modified_count > 0
