"""Time checks for the workflows, so the digest data lands at 14:35 London all year.

GitHub cron schedules are in UTC. 14:35 London is 13:35 UTC in summer (BST) and 14:35 UTC in
winter (GMT), so pre-digest is scheduled at both and this decides which run goes ahead:
  python3 -m pipeline.schedule_gate predigest "<cron that fired>"     prints true or false
The intraday workflow is the backup: it commits the data itself if, between 14:30 and 14:40
London, the data repo still has no latest.json from 14:25 London today or later:
  git show HEAD:data/latest.json | python3 -m pipeline.schedule_gate backup     prints true or false
Standard library only, so it runs on the runner's own Python before any setup.
"""
import json
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
DIGEST_HOUR = 14  # the pre-digest run is for 14:35 London
BACKUP_FROM, BACKUP_TO = time(14, 30), time(14, 40)
FRESH_FROM = time(14, 25)  # a committed run_at from this London time today counts as done


def predigest_due(cron, now):
    """True if the cron that fired is the one that means 14:35 in London today.

    Decided from the scheduled hour, not the clock, so a run that starts late still goes ahead.
    No cron (a manual "Run workflow") always goes ahead.
    """
    if not cron:
        return True
    hour_utc = int(cron.split()[1])
    return hour_utc + now.astimezone(LONDON).utcoffset() // timedelta(hours=1) == DIGEST_HOUR


def backup_due(committed_run_at, now):
    """True between 14:30 and 14:40 London if the committed latest.json is from before 14:25 today."""
    local = now.astimezone(LONDON)
    if not BACKUP_FROM <= local.time() < BACKUP_TO:
        return False
    if not committed_run_at:
        return True
    cutoff = datetime.combine(local.date(), FRESH_FROM, tzinfo=LONDON)
    return datetime.fromisoformat(committed_run_at) < cutoff


def main():
    now = datetime.now(timezone.utc)
    if sys.argv[1] == "predigest":
        due = predigest_due(sys.argv[2] if len(sys.argv) > 2 else "", now)
    else:
        text = sys.stdin.read().strip()
        due = backup_due(json.loads(text).get("run_at") if text else None, now)
    print("true" if due else "false")


if __name__ == "__main__":
    main()
