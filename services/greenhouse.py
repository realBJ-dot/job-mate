"""Greenhouse job board integration."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class JobPosting:
    id: str
    company: str
    title: str
    location: str
    url: str
    content: str
    source: str

    @property
    def stable_key(self) -> str:
        return f"{self.source}:{self.id}"


def _get_json(url: str, timeout: int = 20) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "auto-job-agent/1.0"})
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Greenhouse request failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Greenhouse request failed for {url}: {exc.reason}") from exc


def fetch_board(board_token: str, company: str | None = None) -> list[JobPosting]:
    """Fetch jobs from a public Greenhouse board token, such as 'stripe'."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    payload = _get_json(url)
    postings: list[JobPosting] = []

    for item in payload.get("jobs", []):
        offices = item.get("offices") or []
        location = item.get("location", {}).get("name") or ", ".join(
            office.get("name", "") for office in offices if office.get("name")
        )
        postings.append(
            JobPosting(
                id=str(item.get("id", "")),
                company=company or board_token,
                title=item.get("title", ""),
                location=location or "Unspecified",
                url=item.get("absolute_url", ""),
                content=item.get("content", "") or "",
                source=f"greenhouse:{board_token}",
            )
        )

    return postings


def fetch_sources(sources: list[dict[str, Any]]) -> list[JobPosting]:
    postings: list[JobPosting] = []
    for source in sources:
        if source.get("type") == "greenhouse":
            try:
                postings.extend(fetch_board(source["board"], source.get("company")))
            except RuntimeError as exc:
                print(f"Skipping source {source.get('company') or source.get('board')}: {exc}", file=sys.stderr)
        elif source.get("type") == "linkedin":
            from services.linkedin import fetch_linkedin_source

            postings.extend(fetch_linkedin_source(source))
    return postings
