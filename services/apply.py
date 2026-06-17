"""Playwright application runner."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from services.tracker import load_tracker, mark_application


TERMINAL_STATUSES = {"applied", "interview", "offer", "rejected_by_company", "withdrawn"}
DEFAULT_BATCH_STATUSES = {"drafted", "review", "ready_to_submit"}


def find_tracked_job(tracker_path: str | Path, job_key: str) -> dict[str, str]:
    for row in load_tracker(tracker_path):
        if row.get("job_key") == job_key:
            return row
    raise KeyError(f"No tracked job found for key: {job_key}")


def application_url_for(row: dict[str, str]) -> str:
    job_key = row.get("job_key", "")
    parts = job_key.split(":")
    if len(parts) == 3 and parts[0] == "greenhouse":
        return f"https://job-boards.greenhouse.io/{parts[1]}/jobs/{parts[2]}"
    return row["job_url"]


def review_status_for(result: dict[str, Any]) -> str:
    if result.get("submitted"):
        return "applied"
    if result.get("ready_to_submit"):
        return "ready_to_submit"
    return "needs_manual_answers"


def run_application(
    *,
    job_key: str,
    tracker_path: str | Path = "state/applications.csv",
    profile_path: str | Path = "profile.json",
    answers_path: str | Path = "config/application_answers.json",
    submit: bool = False,
    headless: bool = False,
) -> dict[str, Any]:
    job = find_tracked_job(tracker_path, job_key)
    packet_path = job.get("packet_path")
    if not packet_path:
        raise ValueError(f"Job {job_key} does not have a generated application packet.")

    result_path = Path(packet_path) / "application_result.json"
    command = [
        "node",
        "automation/greenhouse.js",
        "--job-url",
        application_url_for(job),
        "--packet",
        packet_path,
        "--profile",
        str(profile_path),
        "--answers",
        str(answers_path),
        "--result",
        str(result_path),
        "--company",
        job.get("company", ""),
        "--title",
        job.get("title", ""),
        "--focus",
        job.get("focus", ""),
    ]
    if submit:
        command.append("--submit")
    if headless:
        command.append("--headless")

    exit_code = os.spawnvp(os.P_WAIT, "node", command)
    if exit_code != 0:
        raise RuntimeError(f"Playwright application runner failed with exit code {exit_code}.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("submitted"):
        mark_application(
            tracker_path=tracker_path,
            job_key=job_key,
            status="applied",
            notes="Submitted by Playwright automation.",
        )
    return result


def eligible_jobs(
    *,
    tracker_path: str | Path = "state/applications.csv",
    min_score: int = 75,
    statuses: set[str] | None = None,
    limit: int = 10,
) -> list[dict[str, str]]:
    statuses = statuses or DEFAULT_BATCH_STATUSES
    rows = load_tracker(tracker_path)
    eligible = []
    for row in rows:
        status = row.get("application_status", "")
        if status in TERMINAL_STATUSES:
            continue
        if status not in statuses:
            continue
        if row.get("fit_decision") not in {"draft", "review"}:
            continue
        if not row.get("packet_path"):
            continue
        if int(row.get("score") or 0) < min_score:
            continue
        reasons = row.get("reasons", "").lower()
        title = row.get("title", "").lower()
        if "clearance_required" in reasons or "clearance" in title:
            continue
        eligible.append(row)

    eligible.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    return eligible[:limit]


def run_application_batch(
    *,
    tracker_path: str | Path = "state/applications.csv",
    profile_path: str | Path = "profile.json",
    answers_path: str | Path = "config/application_answers.json",
    min_score: int = 75,
    limit: int = 10,
    statuses: set[str] | None = None,
    submit: bool = False,
    headless: bool = True,
) -> list[dict[str, Any]]:
    batch = eligible_jobs(tracker_path=tracker_path, min_score=min_score, statuses=statuses, limit=limit)
    results: list[dict[str, Any]] = []

    for row in batch:
        job_key = row["job_key"]
        item: dict[str, Any] = {
            "job_key": job_key,
            "company": row.get("company"),
            "title": row.get("title"),
            "score": row.get("score"),
        }
        try:
            result = run_application(
                job_key=job_key,
                tracker_path=tracker_path,
                profile_path=profile_path,
                answers_path=answers_path,
                submit=submit,
                headless=headless,
            )
            item.update(result)
            if result.get("submitted"):
                item["status"] = "applied"
            elif result.get("ready_to_submit"):
                mark_application(
                    tracker_path=tracker_path,
                    job_key=job_key,
                    status="ready_to_submit",
                    notes="Batch automation filled the application; final review is pending.",
                )
                item["status"] = "ready_to_submit"
            else:
                missing = ", ".join(result.get("required_unanswered", []))
                mark_application(
                    tracker_path=tracker_path,
                    job_key=job_key,
                    status="needs_manual_answers",
                    notes=f"Batch automation stopped for required fields: {missing}",
                )
                item["status"] = "needs_manual_answers"
        except Exception as exc:
            mark_application(
                tracker_path=tracker_path,
                job_key=job_key,
                status="apply_failed",
                notes=str(exc),
            )
            item["status"] = "apply_failed"
            item["error"] = str(exc)
        results.append(item)

    return results


def run_review_batch(
    *,
    tracker_path: str | Path = "state/applications.csv",
    profile_path: str | Path = "profile.json",
    answers_path: str | Path = "config/application_answers.json",
    min_score: int = 75,
    limit: int = 10,
    statuses: set[str] | None = None,
    job_key: str | None = None,
) -> list[dict[str, Any]]:
    statuses = statuses or {"drafted", "review", "ready_to_submit", "needs_manual_answers"}
    if job_key:
        job = find_tracked_job(tracker_path, job_key)
        if job.get("application_status") in TERMINAL_STATUSES or not job.get("packet_path"):
            return []
        batch = [job]
    else:
        batch = eligible_jobs(tracker_path=tracker_path, min_score=min_score, statuses=statuses, limit=limit)
    jobs = [
        {
            **row,
            "application_url": application_url_for(row),
        }
        for row in batch
    ]
    if not jobs:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        jobs_path = Path(tmp) / "review_jobs.json"
        result_path = Path(tmp) / "review_results.json"
        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        command = [
            "node",
            "automation/review_batch.js",
            "--jobs",
            str(jobs_path),
            "--profile",
            str(profile_path),
            "--answers",
            str(answers_path),
            "--result",
            str(result_path),
        ]
        exit_code = os.spawnvp(os.P_WAIT, "node", command)
        if exit_code != 0:
            raise RuntimeError(f"Playwright review batch failed with exit code {exit_code}.")
        results = json.loads(result_path.read_text(encoding="utf-8"))

    for result in results:
        submitted = bool(result.get("submitted"))
        mark_application(
            tracker_path=tracker_path,
            job_key=result["job_key"],
            status=review_status_for(result),
            notes="Submitted from review-batch session." if submitted else "Opened in review-batch session for manual completion.",
        )
    return results
