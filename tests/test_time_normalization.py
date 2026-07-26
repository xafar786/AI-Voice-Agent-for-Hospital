import unittest

from domain.time_normalization import mentions_clock_time, normalize_time_for_slots
from services.turn_service import _apply_time_resolution, _time_normalization_slots


class TimeNormalizationTests(unittest.TestCase):
    def test_symptom_onset_period_is_not_a_clock_time(self):
        self.assertFalse(mentions_clock_time("مجھے کل رات سے معدے میں تکلیف ہے"))
        self.assertTrue(mentions_clock_time("رات 9 بجے"))

    def assert_normalizes(self, phrases, expected):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                result = normalize_time_for_slots(phrase, [expected])
                self.assertTrue(result.recognized)
                self.assertFalse(result.ambiguous)
                self.assertEqual(result.value, expected)

    def test_urdu_roman_english_and_numeric_whole_hour(self):
        self.assert_normalizes(
            [
                "8 بجے",
                "آٹھ بجے",
                "8 baje",
                "eight o'clock",
                "8:00",
            ],
            "08:00",
        )
        self.assert_normalizes(
            ["9 بجے", "نو بجے", "9 baje", "nine o'clock", "9:00"],
            "09:00",
        )

    def test_quarter_past_variations(self):
        self.assert_normalizes(
            [
                "8 بج کر 15 منٹ",
                "آٹھ بج کر پندرہ منٹ",
                "8 baj kar 15",
                "eight fifteen",
                "8:15",
            ],
            "08:15",
        )
        self.assert_normalizes(
            [
                "9 بج کر 15 منٹ",
                "نو بج کر پندرہ منٹ",
                "9 baj kar 15",
                "nine fifteen",
                "9:15",
            ],
            "09:15",
        )

    def test_half_past_variations(self):
        self.assert_normalizes(
            [
                "ساڑھے آٹھ",
                "ساڑھے 8",
                "saray 8",
                "saadhe aath",
                "half past eight",
                "8 بج کر 30 منٹ",
                "8:30",
            ],
            "08:30",
        )

    def test_quarter_to_variations(self):
        self.assert_normalizes(
            [
                "پونے نو",
                "ponay 9",
                "quarter to nine",
                "8 بج کر 45 منٹ",
                "8 baj kar 45",
                "8:45",
            ],
            "08:45",
        )

    def test_asr_dropped_connective_and_compact_time(self):
        self.assert_normalizes(["نو 15"], "09:15")
        self.assert_normalizes(["زیرو900", "900", "0900"], "09:00")

    def test_all_quarter_hour_database_slots_are_dynamic(self):
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                expected = f"{hour:02d}:{minute:02d}"
                phrase = f"{hour}:{minute:02d}"
                with self.subTest(slot=expected):
                    result = normalize_time_for_slots(phrase, [expected])
                    self.assertEqual(result.value, expected)

    def test_period_resolves_against_database_slots(self):
        morning = normalize_time_for_slots("9 بجے", ["09:00"])
        evening = normalize_time_for_slots("9 بجے", ["21:00"])
        explicit_evening = normalize_time_for_slots("9 pm", ["09:00", "21:00"])

        self.assertEqual(morning.value, "09:00")
        self.assertEqual(evening.value, "21:00")
        self.assertEqual(explicit_evening.value, "21:00")

    def test_genuine_morning_evening_ambiguity_requests_clarification(self):
        result = normalize_time_for_slots("9 بجے", ["09:00", "21:00"])

        self.assertTrue(result.recognized)
        self.assertTrue(result.ambiguous)
        self.assertIsNone(result.value)
        self.assertEqual(result.candidates, ("09:00", "21:00"))

        clarified = normalize_time_for_slots("صبح", result.candidates)
        self.assertEqual(clarified.value, "09:00")

    def test_d2106309_uses_offered_doctors_real_slots(self):
        doctors = [
            {
                "doctor_id": "DOC-0007",
                "name": "Dr. Abdul Malik Sheikh",
                "department": "Cardiology",
                "status": "Available",
                "availability": [
                    {
                        "day": "Sunday",
                        "slots": ["09:00", "09:15", "09:30", "09:45"],
                    }
                ],
            }
        ]
        previous = {
            "department": "Cardiology",
            "date": "2026-07-26",
            "_offered_doctor_id": "DOC-0007",
            "_offered_doctor_name": "Dr. Abdul Malik Sheikh",
            "time": "15:00",
        }
        slots = _time_normalization_slots(
            previous_entities=previous,
            incoming_entities={},
            intent_name="check_availability",
            transcript="نو بجے",
            doctors=doctors,
            appointments=[],
        )

        for phrase in ("نو بجے", "9 بجے"):
            with self.subTest(phrase=phrase):
                result = normalize_time_for_slots(phrase, slots)
                self.assertEqual(result.value, "09:00")
                self.assertNotEqual(result.value, previous["time"])
                remembered, incoming = _apply_time_resolution(
                    previous,
                    {"time": "15:00"},
                    result,
                )
                self.assertNotIn("time", remembered)
                self.assertEqual(incoming["time"], "09:00")


if __name__ == "__main__":
    unittest.main()
