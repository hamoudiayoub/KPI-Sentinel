"""Moroccan business calendar (semantic/calendar/morocco.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

DEFAULT_CALENDAR = Path(__file__).resolve().parents[4] / "semantic" / "calendar" / "morocco.yaml"
EIDS = ("eid_al_fitr", "eid_al_adha")


@dataclass(frozen=True)
class Calendar:
    utc_offset_hours: int
    holidays: dict[date, str]
    ramadan: tuple[tuple[date, date], ...]
    eid_days: dict[date, int]  # date -> 1 for the first day of an Eid, 2 for the following days
    first_year: int
    last_year: int

    def is_holiday(self, day: date) -> bool:
        return day in self.holidays

    def is_ramadan(self, day: date) -> bool:
        return any(start <= day <= end for start, end in self.ramadan)

    def ramadan_day(self, day: date) -> int | None:
        """1 on the first day of Ramadan, None outside Ramadan."""
        for start, end in self.ramadan:
            if start <= day <= end:
                return (day - start).days + 1
        return None

    def days_before_eid(self, day: date) -> int | None:
        """Days until the next first day of an Eid, if it is within a week."""
        for offset in range(1, 8):
            if self.eid_days.get(day + timedelta(days=offset)) == 1:
                return offset
        return None

    def utc_offset(self, day: date) -> int:
        """Local UTC offset in hours: Moroccan clocks move back one hour during Ramadan."""
        return 0 if self.is_ramadan(day) else self.utc_offset_hours

    def covers(self, start: date, end: date) -> bool:
        return self.first_year <= start.year and end.year <= self.last_year


def calendar_path() -> Path:
    return Path(os.environ.get("SENTINEL_GEN_CALENDAR", DEFAULT_CALENDAR))


def load_calendar(path: Path | None = None) -> Calendar:
    document = yaml.safe_load((path or calendar_path()).read_text(encoding="utf-8"))
    years = sorted(int(year) for year in document["years"])
    holidays: dict[date, str] = {}
    eid_days: dict[date, int] = {}
    ramadan: list[tuple[date, date]] = []
    for year in years:
        for entry in document["fixed_holidays"]:
            if year >= entry.get("since", year):
                holidays[date(year, entry["month"], entry["day"])] = entry["name"]
        spec = document["years"][year]
        ramadan.append((spec["ramadan"]["start"], spec["ramadan"]["end"]))
        for name, days in spec["holidays"].items():
            for index, day in enumerate(days):
                holidays[day] = name
                if name in EIDS:
                    eid_days[day] = 1 if index == 0 else 2
    return Calendar(
        utc_offset_hours=int(document["utc_offset_hours"]),
        holidays=holidays,
        ramadan=tuple(ramadan),
        eid_days=eid_days,
        first_year=years[0],
        last_year=years[-1],
    )
