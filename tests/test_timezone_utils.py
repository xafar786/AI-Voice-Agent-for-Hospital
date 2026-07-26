import unittest
from datetime import datetime, timezone

from domain.timezone_utils import PAKISTAN_TZ, pakistan_day_utc_bounds


class PakistanTimezoneTests(unittest.TestCase):
    def test_pakistan_midnight_is_previous_day_1900_utc(self):
        moment = datetime(2026, 7, 27, 12, 30, tzinfo=PAKISTAN_TZ)

        start_utc, end_utc = pakistan_day_utc_bounds(moment)

        self.assertEqual(
            start_utc,
            datetime(2026, 7, 26, 19, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            end_utc,
            datetime(2026, 7, 27, 19, 0, tzinfo=timezone.utc),
        )

    def test_utc_moment_is_converted_before_selecting_pakistan_day(self):
        moment = datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)

        start_utc, end_utc = pakistan_day_utc_bounds(moment)

        self.assertEqual(
            start_utc,
            datetime(2026, 7, 26, 19, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            end_utc,
            datetime(2026, 7, 27, 19, 0, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
