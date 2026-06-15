"""LinkedIn Playwright source integration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from services.greenhouse import JobPosting


def _run_node(args: list[str]) -> None:
    command = ["node", "automation/linkedin_jobs.js", *args]
    exit_code = os.spawnvp(os.P_WAIT, "node", command)
    if exit_code != 0:
        raise RuntimeError(f"LinkedIn Playwright source failed with exit code {exit_code}")


def login(storage_state: str | Path = "state/linkedin_storage_state.json") -> None:
    _run_node(["--mode", "login", "--storage-state", str(storage_state)])


def fetch_linkedin_source(source: dict[str, Any]) -> list[JobPosting]:
    output_path = Path(source.get("output", "state/linkedin_jobs.json"))
    args = [
        "--mode",
        "search",
        "--output",
        str(output_path),
        "--storage-state",
        str(source.get("storage_state", "state/linkedin_storage_state.json")),
        "--keywords",
        str(source.get("keywords", "software engineer")),
        "--location",
        str(source.get("location", "United States")),
        "--recent-days",
        str(source.get("recent_days", 7)),
        "--max",
        str(source.get("max_jobs", 25)),
    ]
    if source.get("url"):
        args.extend(["--url", str(source["url"])])
    if source.get("easy_apply") is False:
        args.extend(["--easy-apply", "false"])
    if source.get("headless", True):
        args.append("--headless")

    try:
        _run_node(args)
    except RuntimeError as exc:
        print(f"Skipping LinkedIn source: {exc}", file=sys.stderr)
        return []

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    postings = []
    for item in payload.get("jobs", []):
        job_id = str(item.get("id") or item.get("url") or item.get("title"))
        postings.append(
            JobPosting(
                id=job_id,
                company=item.get("company") or "LinkedIn",
                title=item.get("title") or "LinkedIn Job",
                location=item.get("location") or "Unspecified",
                url=item.get("url") or "",
                content=item.get("content") or "",
                source="linkedin",
            )
        )
    return postings
