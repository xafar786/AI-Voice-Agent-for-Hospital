import unittest
from datetime import datetime
from threading import Barrier
from unittest.mock import Mock, patch

from services.dialogue_service import (
    APP_TZ,
    build_receptionist_context,
    generate_agent_text,
    get_missing_fields,
)
from services.llm_service import (
    _booking_follow_up,
    _ground_doctor_entities,
    _heuristic_entities,
    _is_urdu_script_reply,
    _mentions_date,
    detect_intent,
)
from services.turn_service import (
    _apply_offered_doctor_selection,
    _allow_doctor_change,
    _can_persist_appointment,
    _canonical_patient_id,
    _deterministic_booking_reply,
    _enrich_entities_for_scheduler,
    _hydrate_registered_patient,
    _merge_workflow_entities,
    _suggested_slots,
    process_turn,
    to_call_log_view,
)
from schemas import IntentResult
from storage.mongo_store import MongoStore


class ConversationStateTests(unittest.TestCase):
    def test_registered_patient_answer_and_id_are_extracted_locally(self):
        registered = _booking_follow_up(
            "میں پہلے سے رجسٹرڈ مریض ہوں",
            expected_fields=["patient_type"],
            previous_intent="book_appointment",
            active_intent="book_appointment",
        )
        patient_id = _booking_follow_up(
            "میرا مریض آئی ڈی PAT-0007 ہے",
            expected_fields=["patient_id"],
            previous_intent="book_appointment",
            active_intent="book_appointment",
        )

        self.assertEqual(registered.entities["patient_type"], "registered")
        self.assertEqual(patient_id.entities["patient_id"], "PC7")

    def test_registered_patient_is_hydrated_from_backend_record(self):
        patients = [
            {
                "patient_id": "PAT-0007",
                "name": "Fahad",
                "phone": "03145678925",
            }
        ]
        hydrated = _hydrate_registered_patient(
            {"patient_type": "registered", "patient_id": "pat 7"},
            patients,
        )

        self.assertEqual(_canonical_patient_id("pat 7"), "PC7")
        self.assertEqual(hydrated["patient_name"], "Fahad")
        self.assertEqual(hydrated["phone"], "03145678925")
        self.assertTrue(hydrated["_registered_patient_valid"])

    def test_registered_patient_persistence_uses_existing_patient_id(self):
        class PatientsCollection:
            def __init__(self):
                self.inserted = False

            def find_one(self, query):
                if query == {"patient_id": "PAT-0007"}:
                    return {"patient_id": "PAT-0007", "name": "Fahad"}
                return None

            def insert_one(self, document):
                self.inserted = True

        store = object.__new__(MongoStore)
        store.patients = PatientsCollection()
        patient_id = store._resolve_patient(
            {
                "patient_id": "PAT-0007",
                "patient_name": "Untrusted Override",
            }
        )

        self.assertEqual(patient_id, "PAT-0007")
        self.assertFalse(store.patients.inserted)

    def test_unconfirmed_turn_never_creates_patient(self):
        store = object.__new__(MongoStore)
        store._resolve_patient = Mock(return_value="PAT-WRONG")
        store._resolve_doctor = Mock(return_value="DOC-0001")
        store._now = Mock(return_value=datetime(2026, 7, 26, 12, 0))
        store.get_session = Mock(return_value={"history": []})
        store.call_logs = Mock()
        store.appointments = Mock()

        store.persist_turn(
            session_id="partial-booking",
            transcript="میرا نام احمد علی ہے",
            intent_name="book_appointment",
            confidence=1.0,
            entities={"patient_name": "احمد علی", "phone": "03480155024"},
            assistant_text="اپنا فون نمبر بتائیں۔",
            audio_mime=None,
            persist_appointment=False,
        )

        store._resolve_patient.assert_not_called()
        store.appointments.find_one.assert_not_called()
        written = store.call_logs.update_one.call_args.args[1]["$set"]
        self.assertNotIn("patient_id", written)
        self.assertNotIn("appointment_id_ref", written)

    def test_booking_retry_reuses_session_patient_before_resolution(self):
        store = object.__new__(MongoStore)
        store._resolve_patient = Mock(return_value="PAT-DUPLICATE")
        store._resolve_doctor = Mock(return_value="DOC-0001")
        store._handle_appointment = Mock()
        store._now = Mock(return_value=datetime(2026, 7, 26, 12, 0))
        store.get_session = Mock(return_value={"history": []})
        store.call_logs = Mock()
        store.appointments = Mock()
        store.appointments.find_one.return_value = {
            "_id": "mongo-appointment-id",
            "patient_id": "PAT-0028",
            "doctor_id": "DOC-0003",
        }

        store.persist_turn(
            session_id="already-booked",
            transcript="جی ہاں",
            intent_name="book_appointment",
            confidence=1.0,
            entities={"patient_name": "احمد علی", "phone": "999999999"},
            assistant_text="اپائنٹمنٹ بک ہو گئی ہے۔",
            audio_mime=None,
            persist_appointment=True,
        )

        store._resolve_patient.assert_not_called()
        store._handle_appointment.assert_not_called()
        written = store.call_logs.update_one.call_args.args[1]["$set"]
        self.assertEqual(written["patient_id"], "PAT-0028")
        self.assertEqual(written["doctor_id"], "DOC-0003")
        self.assertEqual(written["appointment_id_ref"], "mongo-appointment-id")

    def test_valid_registered_patient_id_requires_final_summary_confirmation(self):
        class FakeStore:
            def __init__(self):
                self.persisted = None

            def get_session(self, session_id):
                return {
                    "session_id": session_id,
                    "history": [],
                    "state": {
                        "active_intent": "book_appointment",
                        "last_intent": "book_appointment",
                        "awaiting_final_confirmation": False,
                        "missing_fields": ["patient_id"],
                        "entities": {
                            "doctor_id": "DC1",
                            "doctor_name": "Dr. Aamer Nabi Nur",
                            "_doctor_locked": True,
                            "department": "Orthopedic Surgery",
                            "date": "2026-08-02",
                            "time": "09:00",
                            "patient_type": "registered",
                        },
                    },
                }

            def get_doctors(self):
                return [
                    {
                        "doctor_id": "DC1",
                        "name": "Dr. Aamer Nabi Nur",
                        "department": "Orthopedic Surgery",
                        "status": "Available",
                        "availability": [
                            {"day": "Sunday", "slots": ["09:00"]},
                        ],
                    }
                ]

            def get_appointments(self):
                return []

            def get_patients(self):
                return [
                    {
                        "patient_id": "PC7",
                        "name": "Fahad",
                        "phone": "03145678925",
                    }
                ]

            def append_session(self, *args):
                pass

            def update_session_state(self, *args, **kwargs):
                self.state_update = kwargs

            def persist_turn(self, **kwargs):
                self.persisted = kwargs

            def complete_session(self, session_id):
                pass

        store = FakeStore()
        with patch(
            "services.turn_service.detect_intent",
            return_value=IntentResult(
                intent="book_appointment",
                confidence=1.0,
                entities={"patient_id": "PC7"},
            ),
        ):
            response = process_turn(
                session_id="registered-patient-booking",
                transcript="میرا مریض آئی ڈی PC7 ہے",
                return_tts=False,
                store=store,
            )

        self.assertFalse(store.persisted["persist_appointment"])
        self.assertEqual(store.persisted["entities"]["patient_id"], "PC7")
        self.assertEqual(store.persisted["entities"]["patient_name"], "Fahad")
        self.assertEqual(response.missing_fields, ["confirmation"])
        self.assertTrue(response.needs_clarification)
        self.assertIn("Fahad", response.assistant_text)

    def test_unknown_registered_patient_id_is_rejected(self):
        hydrated = _hydrate_registered_patient(
            {
                "patient_type": "registered",
                "patient_id": "PAT-9999",
                "patient_name": "Untrusted Name",
                "phone": "03000000000",
            },
            [],
        )
        doctor = {
            "doctor_id": "DOC-0001",
            "name": "Dr. Aamer Nabi Nur",
            "department": "Orthopedic Surgery",
            "availability": [{"day": "Sunday", "slots": ["09:00"]}],
        }
        intent = IntentResult(
            intent="book_appointment",
            entities={
                **hydrated,
                "doctor_id": "DOC-0001",
                "doctor_name": "Dr. Aamer Nabi Nur",
                "_doctor_locked": True,
                "date": "2026-07-26",
                "time": "09:00",
            },
        )
        context = build_receptionist_context(
            intent,
            "PAT-9999",
            doctors=[doctor],
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )

        self.assertNotIn("patient_name", hydrated)
        self.assertNotIn("phone", hydrated)
        self.assertEqual(
            get_missing_fields(intent, context),
            ["valid_patient_id"],
        )

    def test_verified_registered_patient_needs_no_name_phone_or_confirmation(self):
        doctor = {
            "doctor_id": "DOC-0001",
            "name": "Dr. Aamer Nabi Nur",
            "department": "Orthopedic Surgery",
            "availability": [{"day": "Sunday", "slots": ["09:00"]}],
        }
        entities = {
            "doctor_id": "DOC-0001",
            "doctor_name": "Dr. Aamer Nabi Nur",
            "_doctor_locked": True,
            "date": "2026-07-26",
            "time": "09:00",
            "patient_type": "registered",
            "patient_id": "PAT-0007",
            "patient_name": "Fahad",
            "phone": "03145678925",
            "_registered_patient_valid": True,
        }
        intent = IntentResult(intent="book_appointment", entities=entities)
        context = build_receptionist_context(
            intent,
            "PAT-0007",
            doctors=[doctor],
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )
        enriched = _enrich_entities_for_scheduler(intent, context)
        final_reply = _deterministic_booking_reply(
            intent_name="book_appointment",
            missing_fields=[],
            appointment_persisted=True,
            entities=enriched,
            context=context,
        )

        self.assertEqual(get_missing_fields(intent, context), [])
        self.assertTrue(
            _can_persist_appointment(
                "book_appointment",
                enriched,
                context,
                needs_clarification=False,
            )
        )
        self.assertIn("Fahad", final_reply)
        self.assertIn("اپائنٹمنٹ بک کر دی گئی", final_reply)
        self.assertNotIn("03145678925", final_reply)

    def test_new_patient_branch_still_requests_name_and_phone(self):
        doctor = {
            "doctor_id": "DOC-0001",
            "name": "Dr. Aamer Nabi Nur",
            "availability": [{"day": "Sunday", "slots": ["09:00"]}],
        }
        intent = IntentResult(
            intent="book_appointment",
            entities={
                "doctor_id": "DOC-0001",
                "doctor_name": "Dr. Aamer Nabi Nur",
                "_doctor_locked": True,
                "date": "2026-07-26",
                "time": "09:00",
                "patient_type": "new",
            },
        )
        context = build_receptionist_context(
            intent,
            "میں نیا مریض ہوں",
            doctors=[doctor],
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )

        self.assertEqual(
            get_missing_fields(intent, context),
            ["patient_name", "phone"],
        )

    def test_patient_type_is_requested_after_doctor_date_and_time(self):
        doctor = {
            "doctor_id": "DOC-0001",
            "name": "Dr. Aamer Nabi Nur",
            "availability": [{"day": "Sunday", "slots": ["09:00"]}],
        }
        intent = IntentResult(
            intent="book_appointment",
            entities={
                "doctor_id": "DOC-0001",
                "doctor_name": "Dr. Aamer Nabi Nur",
                "_doctor_locked": True,
                "date": "2026-07-26",
                "time": "09:00",
            },
        )
        context = build_receptionist_context(
            intent,
            "نو بجے",
            doctors=[doctor],
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )
        missing = get_missing_fields(intent, context)
        reply = _deterministic_booking_reply(
            intent_name="book_appointment",
            missing_fields=missing,
            appointment_persisted=False,
            entities=intent.entities,
            context=context,
        )

        self.assertEqual(missing, ["patient_type"])
        self.assertEqual(reply, "کیا آپ پہلے سے رجسٹرڈ مریض ہیں یا نئے مریض؟")

    def test_availability_reply_exposes_at_most_two_slots(self):
        self.assertEqual(
            _suggested_slots(["10:00", "10:15", "10:30", "10:45"]),
            ["10:00", "10:15"],
        )

    def test_selecting_offered_slot_preserves_single_doctor_for_booking(self):
        previous = {
            "department": "Orthopedic Surgery",
            "date": "2026-07-26",
            "_offered_doctor_id": "DOC-0001",
            "_offered_doctor_name": "Dr. Aamer Nabi Nur",
        }
        incoming = _apply_offered_doctor_selection(
            "book_appointment",
            previous,
            {"time": "11:30"},
        )

        self.assertEqual(incoming["doctor_id"], "DOC-0001")
        self.assertEqual(incoming["doctor_name"], "Dr. Aamer Nabi Nur")
        self.assertTrue(incoming["_doctor_locked"])

    def test_explicit_book_slot_cannot_drift_to_availability_intent(self):
        with patch(
            "services.llm_service._detect_with_openai",
            return_value=IntentResult(
                intent="check_availability",
                confidence=0.55,
                entities={"time": "11:30"},
            ),
        ):
            result = detect_intent(
                "11 30 بجے کی اپوائنٹمنٹ بک کر دیں",
                previous_intent="check_availability",
            )

        self.assertEqual(result.intent, "book_appointment")
        self.assertEqual(result.entities["time"], "11:30")

    def test_complete_offered_slot_workflow_is_persistable(self):
        doctors = [
            {
                "doctor_id": "DOC-0001",
                "name": "Dr. Aamer Nabi Nur",
                "department": "Orthopedic Surgery",
                "status": "Available",
                "availability": [
                    {"day": "Sunday", "slots": ["10:00", "10:15", "11:30"]},
                ],
            }
        ]
        availability_intent = IntentResult(
            intent="check_availability",
            entities={
                "department": "Orthopedic Surgery",
                "date": "2026-07-26",
            },
        )
        availability_context = build_receptionist_context(
            availability_intent,
            "کل ارتھوپیڈک ڈاکٹر کی دستیابی بتائیں",
            doctors=doctors,
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )
        remembered = _enrich_entities_for_scheduler(
            availability_intent,
            availability_context,
        )
        selected_slot = _apply_offered_doctor_selection(
            "book_appointment",
            remembered,
            {"time": "11:30"},
        )
        booking_entities = _merge_workflow_entities(remembered, selected_slot)
        booking_entities.update(
            {
                "patient_name": "فہد خالد",
                "phone": "03180388123",
                "confirmation": True,
            }
        )
        booking_intent = IntentResult(
            intent="book_appointment",
            entities=booking_entities,
        )
        booking_context = build_receptionist_context(
            booking_intent,
            "جی میں تصدیق کرتا ہوں",
            doctors=doctors,
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )
        enriched = _enrich_entities_for_scheduler(booking_intent, booking_context)

        self.assertEqual(get_missing_fields(booking_intent, booking_context), [])
        self.assertEqual(enriched["doctor_id"], "DOC-0001")
        self.assertTrue(
            _can_persist_appointment(
                "book_appointment",
                enriched,
                booking_context,
                needs_clarification=False,
            )
        )

    def test_urdu_doctor_selection_is_not_saved_as_patient_name(self):
        doctors = [{"doctor_id": "DOC-0001", "name": "Dr. Aamer Nabi Nur"}]
        transcript = "ڈاکٹر عامر نبی نور کو منتخب کر دیں"
        grounded = _ground_doctor_entities(
            transcript=transcript,
            entities={"patient_name": "Dr. Aamer Nabi Nur"},
            heuristic_entities=_heuristic_entities(transcript),
            doctors=doctors,
        )

        self.assertEqual(grounded["doctor_id"], "DOC-0001")
        self.assertTrue(grounded["_doctor_locked"])
        self.assertNotIn("patient_name", grounded)

    def test_booking_prompts_do_not_repeat_collected_details(self):
        context = type(
            "BookingContext",
            (),
            {
                "selected_doctor": {"name": "Dr. Aamer Nabi Nur"},
                "resolved_date": datetime(2026, 7, 26).date(),
            },
        )()
        entities = {
            "doctor_name": "Dr. Aamer Nabi Nur",
            "date": "2026-07-26",
            "time": "11:30",
            "patient_name": "فہد خالد",
            "phone": "03180388123",
        }

        phone_prompt = _deterministic_booking_reply(
            intent_name="book_appointment",
            missing_fields=["phone"],
            appointment_persisted=False,
            entities={key: value for key, value in entities.items() if key != "phone"},
            context=context,
        )
        confirmation_prompt = _deterministic_booking_reply(
            intent_name="book_appointment",
            missing_fields=["confirmation"],
            appointment_persisted=False,
            entities=entities,
            context=context,
        )
        final_reply = _deterministic_booking_reply(
            intent_name="book_appointment",
            missing_fields=[],
            appointment_persisted=True,
            entities=entities,
            context=context,
        )

        self.assertEqual(
            phone_prompt,
            "براہ کرم مریض کا فون نمبر بتا دیں۔",
        )
        self.assertIn("Aamer Nabi Nur", confirmation_prompt)
        self.assertIn("26-07-2026", confirmation_prompt)
        self.assertIn("11:30", confirmation_prompt)
        self.assertIn("03180388123", confirmation_prompt)
        self.assertEqual(confirmation_prompt.count("حتمی تصدیق"), 1)
        self.assertIn("Aamer Nabi Nur", final_reply)
        self.assertIn("03180388123", final_reply)

    def test_department_only_turn_does_not_persist_arbitrary_doctor(self):
        class DoctorsCollection:
            def find_one(self, query):
                self.query = query
                return {"doctor_id": "DOC-WRONG"}

        store = object.__new__(MongoStore)
        store.doctors = DoctorsCollection()

        self.assertIsNone(store._resolve_doctor({"department": "Cardiology"}))
        self.assertFalse(hasattr(store.doctors, "query"))

    def test_long_yes_specialty_request_is_not_booking_confirmation(self):
        entities = _heuristic_entities(
            "ہاں آپ مجھے کوئی کارڈیولوجسٹ کوئی بھی ڈاکٹر ریکمنڈ کر دیں"
        )
        result = _booking_follow_up(
            "ہاں آپ مجھے کوئی کارڈیالوجسٹ ڈاکٹر ریکمنڈ کر دیں",
            expected_fields=["confirmation"],
            previous_intent="check_availability",
            active_intent="book_appointment",
        )

        self.assertIsNone(result)
        self.assertEqual(entities.get("department"), "Cardiology")
        self.assertNotIn("doctor_name", entities)

    def test_nonexistent_fahad_cannot_be_substituted_with_ijaz(self):
        doctors = [
            {
                "doctor_id": "DOC-0060",
                "name": "Dr. Ejaz Ahmed Khan (P)",
            },
            {
                "doctor_id": "DOC-0063",
                "name": "Dr. Fahd Jan Mian",
            },
        ]
        transcript = "مجھے ڈاکٹر فہد کے ساتھ اپوائنٹمنٹ بک کرنی ہے"
        heuristic = _heuristic_entities(transcript)

        grounded = _ground_doctor_entities(
            transcript=transcript,
            entities={
                "doctor_id": "DOC-0060",
                "doctor_name": "Dr. Ejaz Ahmed Khan (P)",
                "department": "Pediatrics",
            },
            heuristic_entities=heuristic,
            doctors=doctors,
        )

        self.assertNotIn("doctor_id", grounded)
        self.assertEqual(grounded["doctor_name"], "Dr. فہد")
        self.assertFalse(grounded["_doctor_locked"])

    def test_exact_amjad_khan_match_outranks_similar_masood_khan_without_id_sorting(self):
        doctors = [
            {
                "doctor_id": "DC142",
                "name": "Dr. Masood Khan",
                "urdu_name": "\u0688\u0627\u06a9\u0679\u0631 \u0645\u0633\u0639\u0648\u062f \u062e\u0627\u0646",
                "department": "Pediatrics",
                "status": "Available",
            },
            {
                "doctor_id": "DC27",
                "name": "Dr. Amjad Khan",
                "urdu_name": "\u0688\u0627\u06a9\u0679\u0631 \u0627\u0645\u062c\u062f \u062e\u0627\u0646",
                "department": "Dermatology",
                "status": "Available",
            },
        ]
        transcript = (
            "\u0645\u062c\u06be\u06d2 \u0688\u0627\u06a9\u0679\u0631 \u0627\u0645\u062c\u062f \u062e\u0627\u0646 "
            "\u06a9\u06d2 \u0633\u0627\u062a\u06be \u0627\u067e\u0648\u0627\u0626\u0646\u0679\u0645\u0646\u0679 "
            "\u0628\u06a9 \u06a9\u0631\u0646\u06cc \u06c1\u06d2"
        )

        grounded = _ground_doctor_entities(
            transcript=transcript,
            entities={
                "doctor_name": "Dr. Masood Khan",
                "department": "Cardiology",
            },
            heuristic_entities=_heuristic_entities(transcript),
            doctors=doctors,
        )

        self.assertEqual(grounded["doctor_id"], "DC27")
        self.assertEqual(grounded["doctor_name"], "Dr. Amjad Khan")
        self.assertEqual(grounded["department"], "Dermatology")
        self.assertTrue(grounded["_doctor_locked"])

        intent = IntentResult(intent="book_appointment", entities=grounded)
        context = build_receptionist_context(
            intent,
            transcript,
            doctors=doctors,
            appointments=[],
        )
        missing = get_missing_fields(intent, context)

        self.assertEqual(context.selected_doctor["doctor_id"], "DC27")
        self.assertEqual(
            [doctor["doctor_id"] for doctor in context.matched_doctors],
            ["DC27"],
        )
        self.assertNotIn("department", missing)

    def test_specialty_availability_does_not_lock_recommended_doctor(self):
        doctors = [
            {
                "doctor_id": "DOC-0007",
                "name": "Dr. Abdul Malik Sheikh",
                "department": "Cardiology",
                "status": "Available",
                "availability": [
                    {"day": "Sunday", "slots": ["09:00", "10:00"]},
                ],
            },
            {
                "doctor_id": "DOC-0037",
                "name": "Dr. Asaad Akbar Khan",
                "department": "Cardiology",
                "status": "Available",
                "availability": [
                    {"day": "Monday", "slots": ["11:00"]},
                ],
            },
        ]
        intent = IntentResult(
            intent="check_availability",
            entities={
                "department": "Cardiology",
                "date": "2026-07-26",
            },
        )

        context = build_receptionist_context(
            intent,
            "کل کوئی کارڈیالوجسٹ دستیاب ہے",
            doctors=doctors,
            appointments=[],
            now=datetime(2026, 7, 25, 2, 0, tzinfo=APP_TZ),
        )
        enriched = _enrich_entities_for_scheduler(intent, context)

        self.assertEqual(context.selected_doctor["doctor_id"], "DOC-0007")
        self.assertFalse(context.doctor_selected_by_user)
        self.assertEqual(
            context.available_slots_by_doctor["DOC-0007"],
            ["09:00", "10:00"],
        )
        self.assertNotIn("doctor_id", enriched)
        self.assertNotIn("doctor_name", enriched)

    def test_identical_doctor_names_do_not_require_department(self):
        doctors = [
            {
                "doctor_id": "DOC-0011",
                "name": "Dr. Abid Ilyas",
                "department": "Internal Medicine",
                "status": "Available",
                "availability": [
                    {"day": "Saturday", "slots": ["08:00", "09:00"]},
                ],
            },
            {
                "doctor_id": "DOC-0012",
                "name": "Dr. Abid Ilyas",
                "department": "Critical Care",
                "status": "Available",
                "availability": [
                    {"day": "Sunday", "slots": ["11:00", "12:00"]},
                ],
            },
        ]
        intent = IntentResult(
            intent="book_appointment",
            entities={"doctor_name": "Dr. Abid Ilyas"},
        )

        context = build_receptionist_context(
            intent,
            "ڈاکٹر عابد الیاس",
            doctors=doctors,
            appointments=[],
            now=datetime(2026, 7, 25, 2, 18, tzinfo=APP_TZ),
        )
        missing = get_missing_fields(intent, context)

        self.assertEqual(context.selected_doctor["doctor_id"], "DOC-0011")
        self.assertFalse(context.duplicate_name)
        self.assertNotIn("department", missing)
        self.assertIn("date", missing)

    def test_duplicate_doctor_uses_record_with_real_date_availability(self):
        doctors = [
            {
                "doctor_id": "DOC-0011",
                "name": "Dr. Abid Ilyas",
                "status": "Available",
                "availability": [
                    {"day": "Saturday", "slots": ["08:00", "09:00"]},
                ],
            },
            {
                "doctor_id": "DOC-0010",
                "name": "Dr. Abid Ilyas",
                "status": "Available",
                "availability": [
                    {"day": "Sunday", "slots": ["11:00"]},
                ],
            },
        ]
        intent = IntentResult(
            intent="check_availability",
            entities={"doctor_name": "Dr. Abid Ilyas", "date": "2026-07-25"},
        )

        context = build_receptionist_context(
            intent,
            "25 جولائی کو ڈاکٹر عابد الیاس",
            doctors=doctors,
            appointments=[],
            now=datetime(2026, 7, 24, 12, 0, tzinfo=APP_TZ),
        )

        self.assertEqual(context.selected_doctor["doctor_id"], "DOC-0011")
        self.assertEqual(
            context.available_slots_by_doctor["DOC-0011"],
            ["08:00", "09:00"],
        )

    def test_unverified_classifier_doctor_cannot_replace_remembered_doctor(self):
        previous = {
            "doctor_id": "DOC-0011",
            "doctor_name": "Dr. Abid Ilyas",
            "_doctor_locked": True,
        }
        incorrect_incoming = {
            "doctor_id": "DOC-0047",
            "doctor_name": "Attia Rehman",
            "_doctor_locked": False,
        }

        self.assertFalse(
            _allow_doctor_change(
                previous,
                incorrect_incoming,
                "مجھے ڈاکٹر عابد الیاس کے ساتھ اپائنٹمنٹ بک کرنی ہے",
            )
        )
        self.assertTrue(
            _allow_doctor_change(
                previous,
                incorrect_incoming,
                "نہیں، اس کے بجائے ڈاکٹر عطیہ رحمان سے وقت لینا ہے",
            )
        )

    def test_date_is_not_inferred_from_unrelated_urdu_word(self):
        self.assertFalse(_mentions_date("ڈاکٹر عابد الیاس"))
        self.assertNotIn("natural_date", _heuristic_entities("بالکل ٹھیک ہے"))
        self.assertTrue(_mentions_date("25 جولائی کو"))

    def test_call_log_view_contains_full_history_and_recording_status(self):
        turns = [
            {
                "transcript": "السلام علیکم",
                "assistant_text": "وعلیکم السلام!",
                "intent": "greeting",
                "entities": {},
            },
            {
                "transcript": "میرا نام علی ہے",
                "assistant_text": "شکریہ، علی صاحب۔",
                "intent": "book_appointment",
                "entities": {
                    "patient_name": "علی",
                    "phone": "03001234567",
                },
            },
            {
                "transcript": "خدا حافظ",
                "assistant_text": "خدا حافظ۔",
                "intent": "end_conversation",
                "entities": {},
            },
        ]

        view = to_call_log_view(
            {
                "id": "call-1",
                "session_id": "session-1",
                "entities": {},
                "turns": turns,
                "recording_file_id": "recording-1",
                "recording_mime": "audio/webm",
                "recording_size": 1024,
                "recording_duration_seconds": 93.417,
                "updated_at": datetime(2026, 7, 26, 21, 15, tzinfo=APP_TZ),
            }
        )

        self.assertEqual(view["turns"], turns)
        self.assertTrue(view["has_recording"])
        self.assertEqual(view["recording_duration_seconds"], 93.417)
        self.assertEqual(view["patient_name"], "علی")
        self.assertEqual(view["phone"], "03001234567")
        self.assertEqual(
            view["updated_at"],
            datetime(2026, 7, 26, 21, 15, tzinfo=APP_TZ),
        )

    def test_greeting_does_not_expose_backend_date_or_time(self):
        context = type(
            "GreetingContext",
            (),
            {"now": datetime(2026, 7, 25, 1, 54, tzinfo=APP_TZ)},
        )()

        reply = generate_agent_text(
            IntentResult(intent="greeting", entities={}),
            "السلام علیکم",
            context=context,
        )

        self.assertNotIn("2026", reply)
        self.assertNotIn("01:54", reply)
        self.assertNotIn("25-07", reply)
        self.assertTrue(_is_urdu_script_reply(reply))

    def test_roman_urdu_reply_is_rejected(self):
        self.assertFalse(
            _is_urdu_script_reply(
                "Doctor aaj available hain, lekin is waqt koi slot nahi hai."
            )
        )
        self.assertTrue(
            _is_urdu_script_reply(
                "ڈاکٹر آج دستیاب ہیں، لیکن اس وقت کوئی خالی وقت موجود نہیں ہے۔"
            )
        )

    def test_end_phrase_overrides_active_booking_field(self):
        result = detect_intent(
            "بس ٹھیک ہے، خدا حافظ",
            active_intent="book_appointment",
            expected_fields=["patient_name"],
            previous_intent="book_appointment",
        )

        self.assertEqual(result.intent, "end_conversation")

    def test_short_time_answer_keeps_active_booking_intent(self):
        result = _booking_follow_up(
            "10 بجے 10 بجے",
            expected_fields=["time", "patient_name", "phone"],
            previous_intent="book_appointment",
            active_intent="book_appointment",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "book_appointment")
        self.assertEqual(result.entities, {"time": "10:00"})

    def test_time_after_availability_does_not_reextract_old_history(self):
        result = _booking_follow_up(
            "10:00",
            expected_fields=[],
            previous_intent="check_availability",
            active_intent=None,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "check_availability")
        self.assertEqual(result.entities, {"time": "10:00"})

    def test_short_time_does_not_replace_remembered_doctor_or_date(self):
        remembered = {
            "doctor_id": "DOC-0006",
            "doctor_name": "Dr. Abdul Hakim",
            "date": "2026-07-26",
            "natural_date": "kal",
        }

        merged = _merge_workflow_entities(remembered, {"time": "10:00"})

        self.assertEqual(merged["doctor_id"], "DOC-0006")
        self.assertEqual(merged["date"], "2026-07-26")
        self.assertEqual(merged["time"], "10:00")

    def test_new_date_replaces_both_old_date_forms(self):
        remembered = {"date": "2026-07-25", "natural_date": "aaj"}

        merged = _merge_workflow_entities(remembered, {"natural_date": "kal"})

        self.assertNotIn("date", merged)
        self.assertEqual(merged["natural_date"], "kal")

    def test_remembered_sunday_slot_is_available(self):
        doctor = {
            "doctor_id": "DOC-0006",
            "name": "Dr. Abdul Hakim",
            "availability": [
                {"day": "Sunday", "slots": ["09:00", "10:00", "11:00"]},
            ],
        }
        intent = IntentResult(
            intent="book_appointment",
            entities={
                "doctor_id": "DOC-0006",
                "date": "2026-07-26",
                "time": "10:00",
            },
        )

        context = build_receptionist_context(
            intent,
            "10 بجے",
            doctors=[doctor],
            appointments=[],
            now=datetime(2026, 7, 25, 9, 0, tzinfo=APP_TZ),
        )

        self.assertEqual(
            context.available_slots_by_doctor["DOC-0006"],
            ["09:00", "10:00", "11:00"],
        )

    def test_end_conversation_completes_session(self):
        class FakeStore:
            def __init__(self):
                self.completed_session_id = None

            def get_session(self, session_id):
                return {
                    "session_id": session_id,
                    "history": [],
                    "state": {
                        "active_intent": "book_appointment",
                        "last_intent": "book_appointment",
                        "missing_fields": ["patient_name"],
                        "entities": {"date": "2026-07-26"},
                    },
                }

            def get_doctors(self):
                return []

            def get_appointments(self):
                return []

            def get_patients(self):
                return []

            def append_session(self, *args):
                pass

            def update_session_state(self, *args, **kwargs):
                pass

            def persist_turn(self, **kwargs):
                pass

            def complete_session(self, session_id):
                self.completed_session_id = session_id

        store = FakeStore()
        response = process_turn(
            session_id="urdu-end-test",
            transcript="اللہ حافظ، بات ختم کریں",
            return_tts=False,
            store=store,
        )

        self.assertTrue(response.conversation_ended)
        self.assertEqual(response.intent.intent, "end_conversation")
        self.assertEqual(store.completed_session_id, "urdu-end-test")
        self.assertTrue(_is_urdu_script_reply(response.assistant_text))


if __name__ == "__main__":
    unittest.main()
