import unittest
from datetime import datetime

from domain.phone_normalization import (
    has_phone_context,
    has_phone_number_signal,
    normalize_phone_number,
    spoken_phone_digits,
)
from schemas import IntentResult
from services.dialogue_service import APP_TZ, build_receptionist_context, get_missing_fields
from services.llm_service import _booking_follow_up
from services.turn_service import (
    _apply_phone_resolution,
    _deterministic_booking_reply,
    _merge_workflow_entities,
    _without_nullish_entities,
)


class PhoneNormalizationTests(unittest.TestCase):
    def test_urdu_digit_words(self):
        self.assertEqual(
            normalize_phone_number(
                "میرا نمبر زیرو تین ایک دو تین چار پانچ چھ سات آٹھ نو ہے"
            ),
            "03123456789",
        )

    def test_english_digit_words(self):
        self.assertEqual(
            normalize_phone_number(
                "zero three one two three four five six seven eight nine"
            ),
            "03123456789",
        )

    def test_roman_urdu_digit_words(self):
        self.assertEqual(
            normalize_phone_number(
                "zero teen aik do teen chaar paanch chay saat aath nau"
            ),
            "03123456789",
        )

    def test_urdu_numeric_characters(self):
        self.assertEqual(normalize_phone_number("۰۳۱۲۳۴۵۶۷۸۹"), "03123456789")

    def test_recent_asr_zero_prefix_artifact(self):
        self.assertEqual(
            normalize_phone_number("ز تین ایک دو تین چار پانچ چھ سات آٹھ نو"),
            "03123456789",
        )

    def test_numeric_chunks_and_international_prefix(self):
        self.assertEqual(normalize_phone_number("0312-3456789"), "03123456789")
        self.assertEqual(normalize_phone_number("+92 312 3456789"), "03123456789")

    def test_double_digit(self):
        self.assertEqual(
            normalize_phone_number(
                "zero three one double two three four five six seven eight"
            ),
            "03122345678",
        )

    def test_compound_spoken_values_are_split_into_digits(self):
        self.assertEqual(spoken_phone_digits("zero teen bara"), "0312")

    def test_accepts_flexible_length_and_prefix(self):
        self.assertEqual(normalize_phone_number("03180388"), "03180388")
        self.assertEqual(normalize_phone_number("02123456789"), "02123456789")
        self.assertEqual(
            normalize_phone_number("زیرو 312 983 381"),
            "0312983381",
        )

    def test_rejects_only_unusable_numeric_fragments(self):
        self.assertIsNone(normalize_phone_number("0318"))
        self.assertIsNone(normalize_phone_number("1234567890123456"))
        self.assertIsNone(normalize_phone_number("null"))

    def test_invalid_attempt_clears_old_phone_and_marks_retry(self):
        previous, incoming = _apply_phone_resolution(
            {"phone": "03123456789"},
            {"phone": "0318"},
            "میرا فون نمبر 0318 ہے",
            phone_expected=False,
        )
        self.assertNotIn("phone", previous)
        self.assertNotIn("phone", incoming)
        self.assertTrue(incoming["_phone_invalid"])

    def test_later_phone_mention_does_not_erase_captured_number(self):
        previous, incoming = _apply_phone_resolution(
            {"phone": "03480155024"},
            {},
            "میں فون نمبر پہلے بتا چکا ہوں",
            phone_expected=False,
        )
        self.assertEqual(previous["phone"], "03480155024")
        self.assertNotIn("_phone_invalid", incoming)

    def test_model_phone_is_rejected_without_current_speech_evidence(self):
        previous, incoming = _apply_phone_resolution(
            {"phone": "03123456789"},
            {"phone": "03999999999"},
            "جی میں تصدیق کرتا ہوں",
            phone_expected=False,
        )
        self.assertEqual(previous["phone"], "03123456789")
        self.assertNotIn("phone", incoming)

    def test_phone_signal_detects_words_and_spoken_digits(self):
        self.assertTrue(has_phone_number_signal("میرا موبائل نمبر یہ ہے"))
        self.assertTrue(has_phone_number_signal("zero three one two"))
        self.assertFalse(has_phone_number_signal("جی میں تصدیق کرتا ہوں"))
        self.assertTrue(has_phone_context("میرا موبائل نمبر یہ ہے"))
        self.assertFalse(has_phone_context("09 30"))

    def test_clock_time_is_not_invalidated_as_a_phone_attempt(self):
        previous, incoming = _apply_phone_resolution(
            {},
            {"time": "09:30"},
            "09 30",
            phone_expected=False,
        )
        self.assertNotIn("_phone_invalid", incoming)
        self.assertEqual(incoming["time"], "09:30")

    def test_invalid_phone_remains_missing_and_asks_for_retry(self):
        doctor = {
            "doctor_id": "DOC-0001",
            "name": "Dr. Test",
            "status": "Available",
            "availability": [{"day": "Sunday", "slots": ["09:00"]}],
        }
        intent = IntentResult(
            intent="book_appointment",
            entities={
                "doctor_id": "DOC-0001",
                "doctor_name": "Dr. Test",
                "_doctor_locked": True,
                "date": "2026-07-26",
                "time": "09:00",
                "patient_type": "new",
                "patient_name": "Ali",
                "phone": "0318",
                "_phone_invalid": True,
            },
        )
        context = build_receptionist_context(
            intent,
            "0318",
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
        self.assertEqual(missing, ["phone"])
        self.assertIn("دوبارہ", reply)

    def test_recent_phone_turn_cannot_replace_collected_name(self):
        previous = {
            "patient_type": "new",
            "patient_name": "حسیب نجاوت",
        }
        result = _booking_follow_up(
            "زیرو تین ایک ایک چھ اٹھ صفر تین اٹھ",
            expected_fields=["phone"],
            previous_intent="book_appointment",
            active_intent="book_appointment",
        )
        merged = _merge_workflow_entities(previous, result.entities)
        self.assertEqual(result.entities["phone"], "031168038")
        self.assertEqual(merged["patient_name"], "حسیب نجاوت")
        self.assertEqual(merged["phone"], "031168038")

    def test_partial_phone_turn_stays_out_of_llm_name_extraction(self):
        result = _booking_follow_up(
            "زیرو تری فور ا",
            expected_fields=["phone"],
            previous_intent="book_appointment",
            active_intent="book_appointment",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "book_appointment")
        self.assertEqual(result.entities, {})

    def test_nullish_model_entities_are_removed(self):
        self.assertEqual(
            _without_nullish_entities(
                {"patient_name": "null", "reason": "None", "time": "08:00"}
            ),
            {"time": "08:00"},
        )


if __name__ == "__main__":
    unittest.main()
