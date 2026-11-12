"""python scripts/test_session.py — checks last_completed_session()."""
from datetime import date, datetime, timezone

from build_market_json import last_completed_session as lcs

utc = lambda *a: datetime(*a, tzinfo=timezone.utc)
assert lcs(utc(2026, 11, 11, 1, 28)) == date(2026, 11, 10)   # late cron, after Mon close
assert lcs(utc(2026, 11, 10, 20, 0)) == date(2026, 11, 9)  # Tue 15:00 ET -> Mon 9th
assert lcs(utc(2026, 11, 11, 21, 45)) == date(2026, 11, 11)  # Veterans Day: stocks open
assert lcs(utc(2026, 11, 14, 0, 15)) == date(2026, 11, 13)   # Sat backup cron -> Fri
assert lcs(utc(2026, 11, 16, 12, 0)) == date(2026, 11, 13)   # Mon morning -> Fri
assert lcs(utc(2026, 11, 27, 0, 15)) == date(2026, 11, 25)   # Thanksgiving skipped
assert lcs(utc(2026, 7, 6, 0, 15)) == date(2026, 7, 2)       # Jul 3 observed + weekend
print("ok")
