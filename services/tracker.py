"""Spreadsheet-friendly application tracker."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from services.greenhouse import JobPosting
from services.matcher import MatchResult


TRACKER_FIELDS = [
    "job_key",
    "company",
    "title",
    "location",
    "focus",
    "score",
    "fit_decision",
    "application_status",
    "date_found",
    "date_drafted",
    "date_applied",
    "job_url",
    "packet_path",
    "matched_skills",
    "reasons",
    "notes",
]

ACTIVE_STATUSES = {"found", "drafted", "review", "applied", "interview", "offer"}
VALID_STATUSES = ACTIVE_STATUSES | {"skip", "rejected", "rejected_by_company", "withdrawn"}


def _today() -> str:
    return date.today().isoformat()


def load_tracker(path: str | Path) -> list[dict[str, str]]:
    tracker_path = Path(path)
    if not tracker_path.exists():
        return []
    with tracker_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save_tracker(rows: list[dict[str, str]], path: str | Path) -> None:
    tracker_path = Path(path)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    with tracker_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACKER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in TRACKER_FIELDS})


def _initial_status(decision: str, packet_path: str | None) -> str:
    if packet_path:
        return "drafted"
    if decision == "review":
        return "review"
    if decision == "reject":
        return "rejected"
    if decision == "skip":
        return "skip"
    return "found"


def upsert_job(
    *,
    tracker_path: str | Path,
    job: JobPosting,
    match: MatchResult,
    packet_path: str | None,
) -> None:
    rows = load_tracker(tracker_path)
    by_key = {row.get("job_key", ""): row for row in rows}
    existing = by_key.get(job.stable_key, {})
    current_status = existing.get("application_status", "")
    status = current_status if current_status in ACTIVE_STATUSES else _initial_status(match.decision, packet_path)

    row = {
        **existing,
        "job_key": job.stable_key,
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "focus": match.focus,
        "score": str(match.score),
        "fit_decision": match.decision,
        "application_status": status,
        "date_found": existing.get("date_found") or _today(),
        "date_drafted": existing.get("date_drafted") or (_today() if packet_path else ""),
        "date_applied": existing.get("date_applied", ""),
        "job_url": job.url,
        "packet_path": packet_path or existing.get("packet_path", ""),
        "matched_skills": "; ".join(match.matched_skills),
        "reasons": "; ".join(match.reasons),
        "notes": existing.get("notes", ""),
    }

    by_key[job.stable_key] = row
    save_tracker(list(by_key.values()), tracker_path)


def mark_application(
    *,
    tracker_path: str | Path,
    job_key: str,
    status: str,
    notes: str | None = None,
    applied_date: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status '{status}'. Use one of: {', '.join(sorted(VALID_STATUSES))}")

    rows = load_tracker(tracker_path)
    for row in rows:
        if row.get("job_key") != job_key:
            continue
        row["application_status"] = status
        if status == "applied":
            row["date_applied"] = applied_date or row.get("date_applied") or _today()
        elif applied_date:
            row["date_applied"] = applied_date
        if notes is not None:
            prior = row.get("notes", "")
            row["notes"] = notes if not prior else f"{prior} | {notes}"
        save_tracker(rows, tracker_path)
        return row

    raise KeyError(f"No tracked job found for key: {job_key}")
