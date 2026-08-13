#!/usr/bin/env python3
"""Generate schemas/holidays.csv — the federal holiday list business-day math uses.

CLAUDE.md requires business-day calculations to exclude weekends and "the federal
holiday list in schemas/holidays.csv". The build package referenced that file but
did not ship it, so it is generated here from the statutory rules rather than
transcribed, which keeps it correct for future years without hand-editing.

Rules: 5 U.S.C. 6103 — 11 legal public holidays. When a holiday falls on Saturday
it is observed the preceding Friday; on Sunday, the following Monday. Business-day
math must use the *observed* date, which is why both are emitted.

Usage: python3 tools/build_holidays.py [start_year] [end_year]
"""

import csv
import sys
from datetime import date, timedelta

MON, THU, SAT, SUN = 0, 3, 5, 6


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th `weekday` of the month (n=1 is first). n=-1 gives the last one."""
    if n < 0:
        d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(weeks=n - 1)


def statutory(year: int):
    """(name, actual date) for each of the 11 federal holidays, in calendar order."""
    return [
        ("New Year's Day", date(year, 1, 1)),
        ("Birthday of Martin Luther King, Jr.", nth_weekday(year, 1, MON, 3)),
        ("Washington's Birthday", nth_weekday(year, 2, MON, 3)),
        ("Memorial Day", nth_weekday(year, 5, MON, -1)),
        ("Juneteenth National Independence Day", date(year, 6, 19)),
        ("Independence Day", date(year, 7, 4)),
        ("Labor Day", nth_weekday(year, 9, MON, 1)),
        ("Columbus Day", nth_weekday(year, 10, MON, 2)),
        ("Veterans Day", date(year, 11, 11)),
        ("Thanksgiving Day", nth_weekday(year, 11, THU, 4)),
        ("Christmas Day", date(year, 12, 25)),
    ]


def observed(d: date) -> date:
    if d.weekday() == SAT:
        return d - timedelta(days=1)
    if d.weekday() == SUN:
        return d + timedelta(days=1)
    return d


def build(start_year: int, end_year: int):
    rows = []
    for year in range(start_year, end_year + 1):
        for name, actual in statutory(year):
            obs = observed(actual)
            rows.append(
                {
                    "Title": f"{name} {year}",
                    "HolidayDate": obs.isoformat(),
                    "HolidayName": name,
                    "StatutoryDate": actual.isoformat(),
                    "Observed": "Y" if obs != actual else "N",
                }
            )
    # A holiday observed on 31 Dec belongs to the *previous* calendar year's file
    # position but the following year's name (New Year's Day 2028 -> Fri 31 Dec 2027).
    # Sorting by the observed date keeps the list chronological for the app.
    rows.sort(key=lambda r: r["HolidayDate"])
    return rows


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 2030
    rows = build(start, end)
    out = "schemas/holidays.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["Title", "HolidayDate", "HolidayName", "StatutoryDate", "Observed"]
        )
        w.writeheader()
        w.writerows(rows)
    shifted = sum(1 for r in rows if r["Observed"] == "Y")
    print(f"{out}: {len(rows)} holidays {start}-{end} ({shifted} shifted for weekend observance)")


if __name__ == "__main__":
    main()
