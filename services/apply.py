"""Playwright application runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.tracker import load_tracker, mark_application


def find_tracked_job(tracker_path: str | Path, job_key: str) -> dict[str, str]:
    for row in load_tracker(tracker_path):
        if row.get("job_key") == job_key:
            return row
    raise KeyError(f"No tracked job found for key: {job_key}")


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
        job["job_url"],
        "--packet",
        packet_path,
        "--profile",
        str(profile_path),
        "--answers",
        str(answers_path),
        "--result",
        str(result_path),
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
