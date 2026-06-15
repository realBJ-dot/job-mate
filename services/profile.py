"""Candidate profile loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_profile(path: str | Path = "profile.json") -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def profile_summary(profile: dict[str, Any]) -> str:
    lines = [profile.get("name", "Candidate")]
    for item in profile.get("education", []):
        lines.append(f"{item.get('degree', '')}, {item.get('school', '')}".strip(", "))
    lines.append("Skills: " + ", ".join(profile.get("skills", [])))
    return "\n".join(line for line in lines if line)
