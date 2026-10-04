import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sepa_bot.ckan_client import resource_updated_on
from sepa_bot.main import _captura_pendiente


class WeeklyScheduleTests(unittest.TestCase):
    timezone = ZoneInfo("America/Argentina/Buenos_Aires")
    scheduled_time = time(14, 0)

    def test_monday_before_fourteen_is_not_due(self):
        now = datetime(2026, 10, 5, 13, 59, tzinfo=self.timezone)

        self.assertIsNone(_captura_pendiente(now, self.scheduled_time))

    def test_monday_at_fourteen_captures_monday(self):
        now = datetime(2026, 10, 5, 14, 0, tzinfo=self.timezone)

        self.assertEqual(_captura_pendiente(now, self.scheduled_time), (date(2026, 10, 5), False))

    def test_tuesday_is_catch_up_for_monday(self):
        now = datetime(2026, 10, 6, 8, 0, tzinfo=self.timezone)

        self.assertEqual(_captura_pendiente(now, self.scheduled_time), (date(2026, 10, 5), True))

    def test_wednesday_does_not_catch_up(self):
        now = datetime(2026, 10, 7, 8, 0, tzinfo=self.timezone)

        self.assertIsNone(_captura_pendiente(now, self.scheduled_time))

    def test_resource_timestamp_is_compared_in_buenos_aires(self):
        resource = {"last_modified": "2026-10-05T11:30:00Z"}

        self.assertTrue(resource_updated_on(resource, date(2026, 10, 5)))
        self.assertFalse(resource_updated_on(resource, date(2026, 10, 6)))


if __name__ == "__main__":
    unittest.main()