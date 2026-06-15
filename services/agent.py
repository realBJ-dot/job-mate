"""Application agent orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.cv_generator import write_application_packet
from services.greenhouse import fetch_sources
from services.matcher import match_job
from services.profile import load_profile
from services.state import load_state, save_state


def load_sources(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)["sources"]


def scan(
    *,
    profile_path: str | Path = "profile.json",
    sources_path: str | Path = "config/sources.json",
    state_path: str | Path = "state/jobs.json",
    output_root: str | Path = "output/applications",
    include_seen: bool = False,
    write_packets: bool = True,
    persist_state: bool = True,
) -> list[dict[str, Any]]:
    profile = load_profile(profile_path)
    state = load_state(state_path)
    sources = load_sources(sources_path)
    jobs = fetch_sources(sources)
    results: list[dict[str, Any]] = []

    for job in jobs:
        if not include_seen and job.stable_key in state["seen"]:
            continue

        match = match_job(job, profile)
        packet = None
        if write_packets and match.should_draft:
            packet = write_application_packet(output_root, profile, job, match)
            state["drafted"][job.stable_key] = {
                "packet": str(packet),
                "score": match.score,
                "focus": match.focus,
                "drafted_at": datetime.now(timezone.utc).isoformat(),
            }

        if persist_state:
            state["seen"][job.stable_key] = {
                "company": job.company,
                "title": job.title,
                "url": job.url,
                "score": match.score,
                "decision": match.decision,
                "focus": match.focus,
                "seen_at": datetime.now(timezone.utc).isoformat(),
            }
        results.append(
            {
                "key": job.stable_key,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "url": job.url,
                "score": match.score,
                "decision": match.decision,
                "focus": match.focus,
                "reasons": match.reasons,
                "packet": str(packet) if packet else None,
            }
        )

    if persist_state:
        save_state(state, state_path)
    return sorted(results, key=lambda item: item["score"], reverse=True)
