import unittest
from datetime import datetime
from unittest.mock import patch

from domain.symptom_routing import infer_department_from_symptoms
from schemas import IntentResult
from services.dialogue_service import APP_TZ, build_receptionist_context
from services.llm_service import _heuristic_entities, _heuristic_intent, detect_intent
from services.turn_service import (
    _deterministic_recommendation_reply,
    _enrich_entities_for_scheduler,
    process_turn,
)


class SymptomRoutingTests(unittest.TestCase):
    def test_common_symptoms_route_to_database_departments(self):
        examples = {
            "I have pain in my back": "Orthopedic Surgery",
            "I have a skin rash and itching": "Dermatology",
            "My tooth is hurting": "Dentistry and Orthodontics",
            "I have difficulty breathing because of asthma": "Pulmonology",
            "میرے پیٹ میں درد اور تیزابیت ہے": "Gastroenterology and Hepatology",
            "میری آنکھ میں درد ہے": "Ophthalmology",
            "مجھے بہت گھبراہٹ اور بے چینی ہے": "Psychiatry",
        }

        for transcript, expected in examples.items():
            with self.subTest(transcript=transcript):
                self.assertEqual(
                    infer_department_from_symptoms(transcript),
                    expected,
                )

    def test_symptom_message_starts_availability_workflow_and_keeps_reason(self):
        result = detect_intent("I have pain in my back")

        self.assertEqual(result.intent, "check_availability")
        self.assertEqual(result.entities["department"], "Orthopedic Surgery")
        self.assertEqual(result.entities["reason"], "I have pain in my back")
        self.assertTrue(result.entities["_department_explicit"])

    def test_symptom_onset_is_not_treated_as_appointment_date(self):
        transcript = (
            "مجھے کل رات سے معدے میں تکلیف ہے اور میرا پیٹ خراب ہے، "
            "میں کسی ڈاکٹر سے چیک اپ کروانا چاہتا ہوں"
        )

        result = detect_intent(transcript)

        self.assertEqual(result.intent, "check_availability")
        self.assertEqual(
            result.entities["department"],
            "Gastroenterology and Hepatology",
        )
        self.assertNotIn("date", result.entities)
        self.assertNotIn("natural_date", result.entities)

    def test_d210630f_flow_recommends_doctor_before_date_and_time(self):
        class FakeStore:
            def __init__(self):
                self.saved_state = None

            def get_session(self, session_id):
                return {"session_id": session_id, "history": [], "state": {}}

            def get_doctors(self):
                return [
                    {
                        "doctor_id": "DOC-GASTRO",
                        "name": "Dr. Gastro",
                        "department": "Gastroenterology and Hepatology",
                        "status": "Available",
                        "availability": [
                            {"day": "Sunday", "slots": ["12:00", "12:15"]}
                        ],
                    }
                ]

            def get_appointments(self):
                return []

            def get_patients(self):
                return []

            def append_session(self, *args):
                pass

            def update_session_state(self, *args, **kwargs):
                self.saved_state = kwargs

            def persist_turn(self, **kwargs):
                pass

        store = FakeStore()
        response = process_turn(
            session_id="d210630f-regression",
            transcript=(
                "مجھے کل رات سے معدے میں تکلیف ہے اور میرا پیٹ خراب ہے، "
                "میں کسی ڈاکٹر سے چیک اپ کروانا چاہتا ہوں"
            ),
            return_tts=False,
            store=store,
        )

        self.assertEqual(response.intent.intent, "check_availability")
        self.assertEqual(response.missing_fields, ["date"])
        self.assertIn("Dr. Gastro", response.assistant_text)
        self.assertNotIn("12:00", response.assistant_text)
        self.assertNotIn("_time_ambiguous_candidates", store.saved_state["entities"])
        self.assertEqual(
            store.saved_state["entities"]["_offered_doctor_id"],
            "DOC-GASTRO",
        )

    def test_d2106317_available_word_is_not_a_gastro_symptom(self):
        transcript = (
            "جس وقت وہ دستیاب ہیں میں اس وقت میری اپائنٹمنٹ "
            "ان کے ساتھ بک کر دیں"
        )

        self.assertIsNone(infer_department_from_symptoms(transcript))
        self.assertNotIn("department", _heuristic_entities(transcript))

    def test_d2106317_nail_injury_date_is_not_an_appointment_date(self):
        transcript = (
            "میں کل گرا تھا، گرنے کی وجہ سے میرے بائیں پاؤں کا ناخن "
            "ٹوٹ گیا ہے اور میں کسی ڈاکٹر کو دکھانا چاہتا ہوں"
        )

        result = detect_intent(transcript)

        self.assertEqual(result.intent, "check_availability")
        self.assertEqual(result.entities["department"], "Dermatology")
        self.assertNotIn("date", result.entities)
        self.assertNotIn("natural_date", result.entities)

    def test_d2106317_keeps_selected_doctor_and_requests_another_date(self):
        class FakeStore:
            def __init__(self):
                self.saved_state = None

            def get_session(self, session_id):
                return {
                    "session_id": session_id,
                    "history": [],
                    "state": {
                        "active_intent": "book_appointment",
                        "last_intent": "book_appointment",
                        "missing_fields": ["time"],
                        "entities": {
                            "doctor_id": "DOC-0004",
                            "doctor_name": "Dr. Aamna Batool Khan",
                            "department": "Dermatology",
                            "date": "2026-07-26",
                            "reason": "left foot toenail broken after fall",
                            "_doctor_locked": True,
                        },
                    },
                }

            def get_doctors(self):
                return [
                    {
                        "doctor_id": "DOC-0004",
                        "name": "Dr. Aamna Batool Khan",
                        "department": "Dermatology",
                        "status": "Available",
                        "availability": [
                            {"day": "Monday", "slots": ["08:30", "08:45"]}
                        ],
                    },
                    {
                        "doctor_id": "DOC-0016",
                        "name": "Dr. Adnan",
                        "department": "Gastroenterology and Hepatology",
                        "status": "Available",
                        "availability": [
                            {"day": "Sunday", "slots": ["16:15", "16:45"]}
                        ],
                    },
                ]

            def get_appointments(self):
                return []

            def get_patients(self):
                return []

            def append_session(self, *args):
                pass

            def update_session_state(self, *args, **kwargs):
                self.saved_state = kwargs

            def persist_turn(self, **kwargs):
                pass

        store = FakeStore()
        classifier_result = IntentResult(
            intent="check_availability",
            confidence=0.74,
            entities={
                # Simulate an ungrounded model inference. It must not replace
                # the patient's explicitly selected doctor.
                "department": "Gastroenterology and Hepatology",
                "reason": "book me whenever she is available",
            },
        )
        with patch(
            "services.turn_service.detect_intent",
            return_value=classifier_result,
        ):
            response = process_turn(
                session_id="d2106317-regression",
                transcript=(
                    "جس وقت وہ دستیاب ہیں میں اس وقت میری اپائنٹمنٹ "
                    "ان کے ساتھ بک کر دیں"
                ),
                return_tts=False,
                store=store,
            )

        self.assertEqual(response.missing_fields, ["date"])
        self.assertIn("Dr. Aamna Batool Khan", response.assistant_text)
        self.assertNotIn("Dr. Adnan", response.assistant_text)
        self.assertEqual(
            store.saved_state["entities"]["doctor_id"],
            "DOC-0004",
        )
        self.assertEqual(
            store.saved_state["entities"]["department"],
            "Dermatology",
        )
        self.assertTrue(store.saved_state["entities"]["_doctor_locked"])

    def test_recommends_an_available_doctor_then_offers_real_slots(self):
        doctors = [
            {
                "doctor_id": "DOC-BUSY",
                "name": "Dr. Busy",
                "department": "Dermatology",
                "status": "Busy",
                "availability": [{"day": "Sunday", "slots": ["08:00"]}],
            },
            {
                "doctor_id": "DOC-AVAILABLE",
                "name": "Dr. Skin",
                "department": "Dermatology",
                "status": "Available",
                "availability": [
                    {"day": "Sunday", "slots": ["09:00", "09:30", "10:00"]}
                ],
            },
        ]
        intent = IntentResult(
            intent="check_availability",
            entities=_heuristic_entities("I have a skin rash"),
        )
        initial_context = build_receptionist_context(
            intent,
            "I have a skin rash",
            doctors=doctors,
            appointments=[],
            now=datetime(2026, 7, 25, 12, 0, tzinfo=APP_TZ),
        )

        self.assertEqual(initial_context.selected_doctor["doctor_id"], "DOC-AVAILABLE")
        initial_entities = _enrich_entities_for_scheduler(intent, initial_context)
        self.assertEqual(initial_entities["_offered_doctor_id"], "DOC-AVAILABLE")
        self.assertIn(
            "Dr. Skin",
            _deterministic_recommendation_reply(
                intent_name="check_availability",
                entities=initial_entities,
                context=initial_context,
            ),
        )

        dated_intent = IntentResult(
            intent="check_availability",
            entities={
                **intent.entities,
                "date": "2026-07-26",
            },
        )
        dated_context = build_receptionist_context(
            dated_intent,
            "tomorrow",
            doctors=doctors,
            appointments=[
                {
                    "doctor_id": "DOC-AVAILABLE",
                    "scheduled_for": "2026-07-26 09:00",
                    "status": "Booked",
                }
            ],
            now=datetime(2026, 7, 25, 12, 0, tzinfo=APP_TZ),
        )
        reply = _deterministic_recommendation_reply(
            intent_name="check_availability",
            entities=_enrich_entities_for_scheduler(dated_intent, dated_context),
            context=dated_context,
        )

        self.assertEqual(dated_context.selected_doctor["doctor_id"], "DOC-AVAILABLE")
        self.assertNotIn("09:00", reply)
        self.assertIn("09:30", reply)
        self.assertIn("10:00", reply)


if __name__ == "__main__":
    unittest.main()
