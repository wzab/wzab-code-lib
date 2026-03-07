#!/usr/bin/env python3
# This is a script for converting an iCal file exported from (heavily edited)
# Google Calendar to CSV format.
# The script was created with significant help from ChatGPT. 
# Very likely, it includes solutions imported from other sources (by ChatGPT).
# Therefore, I (Wojciech M. Zabolotny, wzab01@gmail.com) do not claim any rights
# to it and publish it as Public Domain under the Creative Commons CC0 License. 

import csv
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from dateutil.rrule import rrulestr
from icalendar import Calendar


OUTPUT_TZ = ZoneInfo("Europe/Warsaw")


@dataclass
class EventRow:
    summary: str
    uid: str
    original_start: object | None
    start: object | None
    end: object | None
    location: str
    description: str
    status: str
    url: str


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https")


def read_ics(source: str) -> bytes:
    if is_url(source):
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        return response.content
    with open(source, "rb") as f:
        return f.read()


def get_text(component, key: str, default: str = "") -> str:
    value = component.get(key)
    if value is None:
        return default
    return str(value)


def get_dt(component, key: str):
    value = component.get(key)
    if value is None:
        return None
    return getattr(value, "dt", value)


def to_output_tz(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(OUTPUT_TZ).replace(tzinfo=None)
    return value


def to_csv_datetime(value) -> str:
    value = to_output_tz(value)
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def normalize_for_key(value) -> str:
    """
    Create a canonical key for comparing recurrence-related timestamps.

    Rules:
    - timezone-aware datetimes are normalized to UTC
    - naive datetimes are treated as floating local times
    - date values are kept as dates

    Prefixes prevent collisions between DATE, floating DATETIME, and UTC DATETIME.
    """
    if value is None:
        return ""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return "FLOAT:" + value.strftime("%Y-%m-%d %H:%M:%S")
        return "UTC:" + value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, date):
        return "DATE:" + value.strftime("%Y-%m-%d")

    return str(value)


def parse_sequence(component) -> int:
    raw = get_text(component, "SEQUENCE", "0").strip()
    try:
        return int(raw)
    except ValueError:
        return 0


def build_range_start(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), time.min)


def build_range_end(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), time.max.replace(microsecond=0))


def compute_end(start_value, dtend_value, duration_value):
    if dtend_value is not None:
        return dtend_value
    if duration_value is not None and start_value is not None:
        return start_value + duration_value
    return None


def in_requested_range(value, range_start: datetime, range_end: datetime) -> bool:
    if value is None:
        return False

    if isinstance(value, datetime):
        compare_value = to_output_tz(value)
        return range_start <= compare_value <= range_end

    if isinstance(value, date):
        return range_start.date() <= value <= range_end.date()

    return False


def extract_multi_dt_values(component, key: str) -> list:
    """
    Extract values from EXDATE/RDATE.

    icalendar may return:
    - a single property object with .dts
    - a list of such objects
    """
    prop = component.get(key)
    if prop is None:
        return []

    items = prop if isinstance(prop, list) else [prop]
    values = []
    for item in items:
        for dt_value in getattr(item, "dts", []):
            values.append(dt_value.dt)
    return values


def exdate_set(component) -> set[str]:
    return {normalize_for_key(value) for value in extract_multi_dt_values(component, "EXDATE")}


def rdate_values(component) -> list:
    return extract_multi_dt_values(component, "RDATE")


def expand_master_event(component, range_start: datetime, range_end: datetime) -> list[EventRow]:
    dtstart = get_dt(component, "DTSTART")
    if dtstart is None:
        return []

    dtend = get_dt(component, "DTEND")
    duration = get_dt(component, "DURATION")

    event_duration = None
    if duration is not None:
        event_duration = duration
    elif dtend is not None:
        event_duration = dtend - dtstart

    excluded = exdate_set(component)
    occurrences_by_key: dict[str, object] = {}

    # Expand RRULE instances.
    rrule = component.get("RRULE")
    if rrule is not None:
        rule = rrulestr(rrule.to_ical().decode("utf-8"), dtstart=dtstart)
        for occurrence in rule:
            if not in_requested_range(occurrence, range_start, range_end):
                continue
            key = normalize_for_key(occurrence)
            if key in excluded:
                continue
            occurrences_by_key[key] = occurrence

    # Add explicit RDATE instances.
    for occurrence in rdate_values(component):
        if not in_requested_range(occurrence, range_start, range_end):
            continue
        key = normalize_for_key(occurrence)
        if key in excluded:
            continue
        occurrences_by_key[key] = occurrence

    # If a master event has neither RRULE nor RDATE, nothing is expanded here.
    rows = []
    for key in sorted(occurrences_by_key.keys()):
        occurrence = occurrences_by_key[key]
        rows.append(
            EventRow(
                summary=get_text(component, "SUMMARY", ""),
                uid=get_text(component, "UID", ""),
                original_start=occurrence,
                start=occurrence,
                end=compute_end(occurrence, None, event_duration),
                location=get_text(component, "LOCATION", ""),
                description=get_text(component, "DESCRIPTION", ""),
                status=get_text(component, "STATUS", ""),
                url=get_text(component, "URL", ""),
            )
        )

    return rows


def build_rows(calendar: Calendar, range_start: datetime, range_end: datetime) -> list[EventRow]:
    masters = []
    overrides = []
    standalone = []

    for component in calendar.walk():
        if getattr(component, "name", None) != "VEVENT":
            continue

        status = get_text(component, "STATUS", "").upper()
        if status == "CANCELLED":
            continue

        has_rrule = component.get("RRULE") is not None
        has_rdate = component.get("RDATE") is not None
        has_recurrence_id = component.get("RECURRENCE-ID") is not None

        if has_recurrence_id:
            overrides.append(component)
        elif has_rrule or has_rdate:
            masters.append(component)
        else:
            standalone.append(component)

    rows_by_key: dict[tuple[str, str], tuple[EventRow, int]] = {}

    # Expand recurring master events (RRULE and/or RDATE).
    for component in masters:
        sequence = parse_sequence(component)
        for row in expand_master_event(component, range_start, range_end):
            key = (row.uid, normalize_for_key(row.original_start))
            rows_by_key[key] = (row, sequence)

    # Apply RECURRENCE-ID overrides.
    for component in overrides:
        uid = get_text(component, "UID", "")
        recurrence_id = get_dt(component, "RECURRENCE-ID")
        if recurrence_id is None:
            continue

        start = get_dt(component, "DTSTART")
        if start is None:
            continue

        if not in_requested_range(start, range_start, range_end):
            continue

        row = EventRow(
            summary=get_text(component, "SUMMARY", ""),
            uid=uid,
            original_start=recurrence_id,
            start=start,
            end=compute_end(start, get_dt(component, "DTEND"), get_dt(component, "DURATION")),
            location=get_text(component, "LOCATION", ""),
            description=get_text(component, "DESCRIPTION", ""),
            status=get_text(component, "STATUS", ""),
            url=get_text(component, "URL", ""),
        )

        key = (uid, normalize_for_key(recurrence_id))
        rows_by_key[key] = (row, parse_sequence(component))

    # Add standalone events.
    for component in standalone:
        start = get_dt(component, "DTSTART")
        if start is None:
            continue

        if not in_requested_range(start, range_start, range_end):
            continue

        row = EventRow(
            summary=get_text(component, "SUMMARY", ""),
            uid=get_text(component, "UID", ""),
            original_start=None,
            start=start,
            end=compute_end(start, get_dt(component, "DTEND"), get_dt(component, "DURATION")),
            location=get_text(component, "LOCATION", ""),
            description=get_text(component, "DESCRIPTION", ""),
            status=get_text(component, "STATUS", ""),
            url=get_text(component, "URL", ""),
        )

        key = (row.uid, normalize_for_key(row.start))
        previous = rows_by_key.get(key)
        current_sequence = parse_sequence(component)
        if previous is None or current_sequence >= previous[1]:
            rows_by_key[key] = (row, current_sequence)

    rows = [item[0] for item in rows_by_key.values()]
    rows.sort(key=lambda row: (to_csv_datetime(row.start), row.summary, row.uid))
    return rows


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 gc_ical2csv.py <ics_file_or_url> <output_csv> [start_date] [end_date]")
        print("")
        print("Examples:")
        print("  python3 gc_ical2csv.py basic.ics events.csv")
        print('  python3 gc_ical2csv.py "https://example.com/calendar.ics" events.csv 2026-01-01 2026-12-31')
        sys.exit(1)

    source = sys.argv[1]
    output_csv = sys.argv[2]
    start_date = sys.argv[3] if len(sys.argv) >= 4 else "2026-01-01"
    end_date = sys.argv[4] if len(sys.argv) >= 5 else "2026-12-31"

    range_start = build_range_start(start_date)
    range_end = build_range_end(end_date)

    calendar = Calendar.from_ical(read_ics(source))
    rows = build_rows(calendar, range_start, range_end)

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "summary",
            "uid",
            "original_start",
            "start",
            "end",
            "location",
            "description",
            "status",
            "url",
        ])
        for row in rows:
            writer.writerow([
                row.summary,
                row.uid,
                to_csv_datetime(row.original_start),
                to_csv_datetime(row.start),
                to_csv_datetime(row.end),
                row.location,
                row.description,
                row.status,
                row.url,
            ])

    print(f"Wrote {len(rows)} events to {output_csv}")


if __name__ == "__main__":
    main()
