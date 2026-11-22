"""Which pre-digest run goes ahead, and when the intraday backup commits. Offline."""
import unittest
from datetime import datetime, timezone

from pipeline.schedule_gate import backup_due, predigest_due

WINTER = "2026-11-23T{}+00:00"  # Monday; London = UTC (GMT)
SUMMER = "2027-06-14T{}+00:00"  # Monday; London = UTC+1 (BST)


def utc(s):
    return datetime.fromisoformat(s).astimezone(timezone.utc)


class Predigest(unittest.TestCase):
    def test_winter_runs_the_1435_utc_cron(self):
        self.assertTrue(predigest_due("35 14 * * *", utc(WINTER.format("14:35:00"))))
        self.assertFalse(predigest_due("35 13 * * *", utc(WINTER.format("13:35:00"))))

    def test_summer_runs_the_1335_utc_cron(self):
        self.assertTrue(predigest_due("35 13 * * *", utc(SUMMER.format("13:35:00"))))
        self.assertFalse(predigest_due("35 14 * * *", utc(SUMMER.format("14:35:00"))))

    def test_a_late_start_still_goes_ahead(self):
        # The 14:35 UTC run starting 3 hours late in winter is still the right run.
        self.assertTrue(predigest_due("35 14 * * *", utc(WINTER.format("17:40:00"))))

    def test_manual_run_always_goes_ahead(self):
        self.assertTrue(predigest_due("", utc(WINTER.format("09:00:00"))))


class Backup(unittest.TestCase):
    def test_only_inside_1430_to_1440_london(self):
        old = "2026-11-20T14:36:00+00:00"
        self.assertFalse(backup_due(old, utc(WINTER.format("14:29:00"))))
        self.assertTrue(backup_due(old, utc(WINTER.format("14:32:00"))))
        self.assertFalse(backup_due(old, utc(WINTER.format("14:40:00"))))
        # Summer: 14:32 London is 13:32 UTC.
        self.assertTrue(backup_due("2027-06-11T13:36:00+00:00", utc(SUMMER.format("13:32:00"))))
        self.assertFalse(backup_due("2027-06-11T13:36:00+00:00", utc(SUMMER.format("14:32:00"))))

    def test_skips_once_todays_data_is_committed(self):
        now = utc(WINTER.format("14:37:00"))
        self.assertFalse(backup_due("2026-11-23T14:32:10+00:00", now))  # the 14:32 backup, or pre-digest
        self.assertTrue(backup_due("2026-11-23T11:02:00+00:00", now))   # this morning: not good enough
        self.assertTrue(backup_due(None, now))                          # no latest.json at all

    def test_summer_cutoff_is_london_time(self):
        # 13:26 UTC = 14:26 London in June: after the 14:25 London cut-off, so it counts as done.
        self.assertFalse(backup_due("2027-06-14T13:26:00+00:00", utc(SUMMER.format("13:37:00"))))
        self.assertTrue(backup_due("2027-06-14T13:24:00+00:00", utc(SUMMER.format("13:37:00"))))


if __name__ == "__main__":
    unittest.main()
