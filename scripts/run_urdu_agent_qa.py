from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import uuid

from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.dialogue_service import APP_TZ, INITIAL_GREETING_URDU
from services.turn_service import process_turn
from storage.mongo_store import MongoStore


def main() -> int:
    load_dotenv(".env")
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    source_name = os.getenv("MONGODB_DB_NAME", "voice_agent")
    qa_name = f"{source_name}_urdu_qa_{uuid.uuid4().hex[:8]}"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    source = client[source_name]
    qa_db = client[qa_name]

    failures: list[str] = []
    transcript_log: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    def turn(store: MongoStore, session: str, utterance: str):
        response = process_turn(
            session_id=session,
            transcript=utterance,
            return_tts=False,
            store=store,
        )
        transcript_log.append(
            f"[{session}] USER: {utterance}\n"
            f"[{session}] AGENT: {response.assistant_text}\n"
            f"[{session}] STATE: intent={response.intent.intent}, "
            f"missing={response.missing_fields}, entities={response.intent.entities}"
        )
        return response

    try:
        for collection_name in ("doctors", "doctor_availability", "patients"):
            documents = list(source[collection_name].find({}))
            if documents:
                qa_db[collection_name].insert_many(documents)

        store = MongoStore(uri, qa_name)
        tomorrow = datetime.now(APP_TZ).date() + timedelta(days=1)
        weekday = tomorrow.strftime("%A")
        doctor = next(
            (
                item
                for item in store.get_doctors()
                if item.get("status") == "Available"
                and item.get("urdu_name")
                and any(
                    row.get("day") == weekday and len(row.get("slots") or []) >= 4
                    for row in item.get("availability") or []
                )
            ),
            None,
        )
        if not doctor:
            raise RuntimeError(f"No available doctor has enough {weekday} slots for QA.")
        slots = next(
            row["slots"]
            for row in doctor["availability"]
            if row.get("day") == weekday
        )
        doctor_name = doctor.get("urdu_name") or doctor["name"]
        patient = store.get_patient_by_id("PC7")
        if not patient:
            raise RuntimeError("QA requires the existing PC7 fixture.")

        now = datetime.now(APP_TZ)
        qa_db.appointments.insert_many(
            [
                {
                    "appointment_id": "APT13",
                    "patient_id": "PC7",
                    "doctor_id": doctor["doctor_id"],
                    "department": doctor.get("department"),
                    "scheduled_for": f"{tomorrow.isoformat()} {slots[0]}",
                    "status": "Booked",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "appointment_id": "APT14",
                    "patient_id": "PC7",
                    "doctor_id": doctor["doctor_id"],
                    "department": doctor.get("department"),
                    "scheduled_for": f"{tomorrow.isoformat()} {slots[1]}",
                    "status": "Booked",
                    "created_at": now,
                    "updated_at": now,
                },
            ]
        )

        # Greeting.
        greeting = turn(store, "qa-greeting", "السلام علیکم")
        check(greeting.assistant_text == INITIAL_GREETING_URDU, "Greeting was not deterministic.")
        check("اسسٹنٹ ہوں" in greeting.assistant_text, "Male grammatical greeting was not used.")

        # Complete new-patient booking with Urdu name and spoken phone digits.
        session = "qa-new-booking"
        first = turn(store, session, f"میں {doctor_name} سے کل اپائنٹمنٹ لینا چاہتا ہوں")
        check(first.intent.intent == "book_appointment", "New booking intent was not retained.")
        check(first.missing_fields and first.missing_fields[0] == "time", "Agent did not ask for time first.")
        selected = turn(store, session, slots[2].replace(":", " "))
        check(
            selected.missing_fields and selected.missing_fields[0] == "patient_type",
            "Selected slot was not retained before patient type.",
        )
        turn(store, session, "میں نیا مریض ہوں")
        named = turn(store, session, "میرا نام احمد رضا ہے")
        check(named.missing_fields and named.missing_fields[0] == "phone", "Patient name was not retained.")
        before_patients = qa_db.patients.count_documents({})
        phone = turn(
            store,
            session,
            "میرا فون نمبر زیرو تین ایک دو تین چار پانچ چھ سات آٹھ نو ہے",
        )
        check(phone.intent.entities.get("phone") == "03123456789", "Urdu phone was extracted incorrectly.")
        check(phone.missing_fields == ["confirmation"], "Final summary confirmation was not requested once.")
        check(qa_db.patients.count_documents({}) == before_patients, "Patient was created before confirmation.")
        confirmed = turn(store, session, "جی ہاں، حتمی تصدیق کریں")
        check(not confirmed.missing_fields, "Confirmed booking remained incomplete.")
        check(
            qa_db.appointments.count_documents({"source_session_id": session}) == 1,
            "Confirmed booking did not create exactly one appointment.",
        )
        check(
            qa_db.patients.count_documents({"phone": "03123456789"}) == 1,
            "Confirmed booking did not create exactly one patient.",
        )

        # Cancellation with the exact spoken form that failed in #42DF8910.
        cancel = turn(store, "qa-cancel", "میری پچھلی اپائنٹمنٹ کینسل کر دیں")
        check(cancel.missing_fields == ["appointment_id"], "Cancellation did not request appointment ID.")
        cancelled = turn(store, "qa-cancel", "اے پی ٹی سلیش زیرو زیروون3")
        check(cancelled.intent.entities.get("appointment_id") == "APT13", "Spoken APT13 was not normalized.")
        check(
            qa_db.appointments.find_one({"appointment_id": "APT13"}).get("status") == "Cancelled",
            "APT13 was not cancelled.",
        )

        # Invalid appointment ID must stay in cancellation instead of drifting.
        turn(store, "qa-invalid-cancel", "میری اپائنٹمنٹ کینسل کریں")
        invalid_cancel = turn(store, "qa-invalid-cancel", "اے پی ٹی ننانوے")
        check(invalid_cancel.intent.intent == "cancel_appointment", "Invalid cancellation drifted to another intent.")
        check(
            invalid_cancel.missing_fields == ["valid_appointment"],
            "Unknown appointment ID did not request a valid appointment.",
        )

        # Registered patient path must still end with one summary confirmation.
        registered_session = "qa-registered"
        turn(store, registered_session, f"{doctor_name} سے کل اپائنٹمنٹ چاہیے")
        turn(store, registered_session, slots[3].replace(":", " "))
        turn(store, registered_session, "میں رجسٹرڈ مریض ہوں")
        registered = turn(store, registered_session, "میرا مریض آئی ڈی پی سی سات ہے")
        check(
            registered.missing_fields == ["confirmation"],
            "Registered patient booking skipped final summary confirmation.",
        )

        # Reschedule with spoken compact appointment ID.
        rescheduled = turn(
            store,
            "qa-reschedule",
            f"میری اپائنٹمنٹ اے پی ٹی چودہ کو کل {slots[-1].replace(':', ' ')} پر کر دیں",
        )
        check(rescheduled.intent.intent == "reschedule_appointment", "Reschedule intent was not detected.")
        check(
            qa_db.appointments.find_one({"appointment_id": "APT14"}).get("scheduled_for")
            == f"{tomorrow.isoformat()} {slots[-1]}",
            "APT14 was not rescheduled to the requested slot.",
        )

        # Exact unavailable doctor names must not be silently substituted.
        unknown = turn(
            store,
            "qa-unknown-doctor",
            "مجھے ڈاکٹر فہد سے کل اپائنٹمنٹ چاہیے",
        )
        check(
            unknown.missing_fields and unknown.missing_fields[0] == "doctor_name",
            "Unknown doctor was silently substituted.",
        )
        check(
            "ہسپتال میں دستیاب نہیں" in unknown.assistant_text,
            "Unknown doctor reply did not clearly say the doctor is unavailable.",
        )

        # Symptom routing should remain an availability workflow.
        symptom = turn(
            store,
            "qa-symptom",
            "میرے سینے میں درد اور سانس لینے میں مشکل ہے، مجھے کون سا ڈاکٹر دکھانا چاہیے؟",
        )
        check(symptom.intent.intent == "check_availability", "Chest symptoms did not start doctor discovery.")
        check(
            symptom.intent.entities.get("department") == "Cardiology",
            "Chest symptoms were not routed to Cardiology.",
        )

        print("\n\n".join(transcript_log))
        if failures:
            print("\nQA FAILURES:")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print(f"\nAll Urdu agent scenarios passed in isolated database {qa_name}.")
        return 0
    finally:
        client.drop_database(qa_name)


if __name__ == "__main__":
    sys.exit(main())
