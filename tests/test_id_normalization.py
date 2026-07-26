import unittest

from domain.id_normalization import (
    normalize_appointment_id,
    normalize_doctor_id,
    normalize_patient_id,
)
from services.llm_service import _booking_follow_up


class IdNormalizationTests(unittest.TestCase):
    def test_current_and_legacy_appointment_ids_have_one_format(self):
        self.assertEqual(normalize_appointment_id("APT13"), "APT13")
        self.assertEqual(normalize_appointment_id("APT-0013"), "APT13")
        self.assertEqual(normalize_appointment_id("APT zero zero one three"), "APT13")
        self.assertEqual(
            normalize_appointment_id("اے پی ٹی سلیش زیرو زیروون3"),
            "APT13",
        )

    def test_doctor_and_patient_ids_drop_hyphens_and_padding(self):
        self.assertEqual(normalize_doctor_id("DOC-0013"), "DC13")
        self.assertEqual(normalize_doctor_id("DC13"), "DC13")
        self.assertEqual(normalize_patient_id("PAT-0007"), "PC7")
        self.assertEqual(normalize_patient_id("PC7"), "PC7")

    def test_expected_cancellation_id_is_extracted_without_llm(self):
        result = _booking_follow_up(
            "zero zero one three",
            expected_fields=["appointment_id"],
            previous_intent="cancel_appointment",
            active_intent="cancel_appointment",
        )

        self.assertEqual(result.intent, "cancel_appointment")
        self.assertEqual(result.entities["appointment_id"], "APT13")

    def test_id_digits_stop_before_reschedule_time(self):
        self.assertEqual(
            normalize_appointment_id("اے پی ٹی چودہ کو کل 11 15 پر کر دیں"),
            "APT14",
        )

    def test_urdu_ninety_nine_id(self):
        self.assertEqual(normalize_appointment_id("اے پی ٹی ننانوے"), "APT99")


if __name__ == "__main__":
    unittest.main()
