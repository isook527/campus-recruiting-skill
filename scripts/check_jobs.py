#!/usr/bin/env python3
"""Validate user-observed evidence records and separate current candidates."""

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


CHINA = timezone(timedelta(hours=8))
MAX_AGE = timedelta(hours=8)
DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
STATUSES = {"verified_open", "campaign_open", "not_started", "closed", "unverified"}
TYPES = {"campus", "internship", "public_hiring"}
OFFICIAL_SOURCES = {"employer", "authorized_ats", "public_authority"}
SOURCE_TYPES = OFFICIAL_SOURCES | {"third_party", "unknown"}
WARNINGS = {
    "unverified", "stale", "deadline_time_unconfirmed", "duplicate_requires_resolution",
    "source_not_confirmed", "official_conflict",
}
FIELDS = {
    "id", "employer", "title", "batch", "scope", "employment_type", "city",
    "eligibility", "salary", "announcement_url", "application_url", "checked_at",
    "opens_at", "deadline", "status", "announcement_evidence", "application_evidence",
}
OPTIONAL_TEXT = {
    "city", "eligibility", "salary", "announcement_evidence", "application_evidence",
}
PRIVATE_PARAMETERS = {
    "access_token", "api_key", "apikey", "auth", "authorization", "code", "cookie",
    "external_referral_code", "invite_code", "invitation_code", "password", "recomid",
    "referral", "referral_code", "session", "sessionid", "signature", "token",
}


def parse_datetime(value):
    if not isinstance(value, str):
        raise ValueError("expected a timezone-aware ISO 8601 timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include a time zone")
    return result.astimezone(CHINA)


def parse_boundary(value, end=False):
    if value is None:
        return None, False
    if isinstance(value, str) and DATE_ONLY.fullmatch(value):
        day = date.fromisoformat(value)
        return datetime(day.year, day.month, day.day, tzinfo=CHINA), end
    return parse_datetime(value), False


def check_url(value, key):
    if value is None:
        return
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError(f"{key} must be a public HTTPS URL")
    url = urlsplit(value)
    if (
        url.scheme != "https" or not url.hostname or "." not in url.hostname
        or url.username or url.password
    ):
        raise ValueError(f"{key} must be a public HTTPS URL")
    parameters = parse_qsl(url.query) + parse_qsl(url.fragment.partition("?")[2])
    if any(
        name.lower() in PRIVATE_PARAMETERS or name.lower().startswith("utm_")
        for name, _ in parameters
    ):
        raise ValueError(f"{key} has personal, referral, or tracking parameters")


def identity(row):
    return tuple(
        " ".join(str(row[k] or "").casefold().split())
        for k in ("employer", "title", "scope", "batch", "city")
    )


def deadline_clock(value, now):
    deadline, date_only = parse_boundary(value, end=True)
    if deadline is None:
        return {"precision": "unknown"}
    if date_only:
        return {"precision": "date", "calendar_days": (deadline.date() - now.date()).days}
    return {"precision": "time", "seconds": int((deadline - now).total_seconds())}


def check_record(row, now):
    if not isinstance(row, dict):
        raise ValueError("expected a JSON object for this record")
    if FIELDS - row.keys() or row.keys() - (FIELDS | {"source_type", "official_conflict"}):
        problems = []
        missing = sorted(FIELDS - row.keys())
        unexpected = sorted(row.keys() - (FIELDS | {"source_type", "official_conflict"}))
        if missing:
            problems.append("missing fields " + ", ".join(missing))
        if unexpected:
            problems.append("unexpected fields " + ", ".join(unexpected))
        raise ValueError(". ".join(problems) + ". See references/job-verification.md.")
    for key in ("id", "employer", "title", "batch"):
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError(f"{key} is required")
    for key in OPTIONAL_TEXT:
        if row[key] is not None and (not isinstance(row[key], str) or not row[key].strip()):
            raise ValueError(f"{key} must be null or nonblank text")
    if row["scope"] not in ("position", "campaign"):
        raise ValueError("invalid scope")
    for key, allowed in (("status", STATUSES), ("employment_type", TYPES)):
        if not isinstance(row[key], str) or row[key] not in allowed:
            raise ValueError(f"invalid {key}. Use one of {', '.join(sorted(allowed))}.")

    if "source_type" in row and (
        not isinstance(row["source_type"], str) or row["source_type"] not in SOURCE_TYPES
    ):
        raise ValueError("invalid source_type. Use one of " + ", ".join(sorted(SOURCE_TYPES)) + ".")
    if "official_conflict" in row and type(row["official_conflict"]) is not bool:
        raise ValueError("official_conflict must be a boolean")

    for key in ("announcement_url", "application_url"):
        check_url(row[key], key)
    checked = parse_datetime(row["checked_at"])
    opens, _ = parse_boundary(row["opens_at"])
    closes, close_time_unknown = parse_boundary(row["deadline"], end=True)
    if checked > now:
        raise ValueError("checked_at is in the future")
    if opens and closes and (
        opens.date() > closes.date() if close_time_unknown else opens >= closes
    ):
        raise ValueError("opening is not before the deadline")
    if row.get("official_conflict"):
        return "official_conflict"
    if "source_type" in row and row["source_type"] not in OFFICIAL_SOURCES:
        return "source_not_confirmed"
    if row["status"] in {"verified_open", "campaign_open"}:
        expected = "position" if row["status"] == "verified_open" else "campaign"
        if row["scope"] != expected:
            raise ValueError("status and scope disagree")
        for key in (
            "announcement_url", "application_url", "announcement_evidence",
            "application_evidence", "eligibility",
        ):
            if not row[key]:
                raise ValueError(f"open records need {key}")
        if opens and now < opens:
            return "not_started"
        if closes and now >= closes:
            if close_time_unknown and now.date() == closes.date():
                return "deadline_time_unconfirmed"
            return "closed"
        if (opens and checked < opens) or checked.date() != now.date() or now - checked > MAX_AGE:
            return "stale"
        return row["status"]
    if row["status"] == "not_started" and (not opens or now >= opens):
        return "unverified"
    return row["status"]


def audit(records, now):
    if not isinstance(records, list):
        raise ValueError("expected a JSON array")
    eligible, excluded = [], []
    groups = {}
    record_ids = set()
    for index, row in enumerate(records, 1):
        record_id = row.get("id") if isinstance(row, dict) else None
        location = f"record {index}"
        if isinstance(record_id, str) and record_id:
            location += f" ({record_id!r})"
        try:
            result = check_record(row, now)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{location}. {error}") from error
        if row["id"] in record_ids:
            raise ValueError(f"duplicate id: {row['id']}")
        record_ids.add(row["id"])
        groups.setdefault(identity(row), []).append((row, result))
    for group in groups.values():
        if len(group) > 1:
            for row, _ in group:
                excluded.append({"id": row["id"], "reason": "duplicate_requires_resolution"})
            continue
        row, result = group[0]
        if result in {"verified_open", "campaign_open"}:
            eligible.append({"id": row["id"], "scope": row["scope"], "status": result})
        else:
            excluded.append({"id": row["id"], "reason": result})
    deadlines = {row["id"]: deadline_clock(row["deadline"], now) for row in records}
    expiry = {}
    eligible_ids = {row["id"] for row in eligible}
    for row in records:
        if row["id"] in eligible_ids:
            checked = parse_datetime(row["checked_at"])
            next_day = (checked + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            expiry[row["id"]] = min(checked + MAX_AGE, next_day).isoformat()
    return {
        "as_of": now.isoformat(), "eligible_by_record": eligible, "excluded": excluded,
        "deadline_countdown": deadlines, "verification_window_ends_at": expiry,
        "warnings": [row for row in excluded if row["reason"] in WARNINGS],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="JSON records from a recent evidence check")
    parser.add_argument("--as-of", help="Replay historical rules at a timezone-aware ISO timestamp")
    parser.add_argument("--warn-exit", action="store_true", help="Return exit code 1 on warnings")
    args = parser.parse_args()
    try:
        now = parse_datetime(args.as_of) if args.as_of else datetime.now(CHINA)
        records = json.loads(args.records.read_text(encoding="utf-8"))
        result = audit(records, now)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Invalid records: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.warn_exit and result["warnings"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
