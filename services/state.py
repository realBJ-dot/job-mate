"""Persistent local state for seen and drafted jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STATE = {"seen": {}, "drafted": {}, "submitted": {}}


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return DEFAULT_STATE.copy()
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    for key, value in DEFAULT_STATE.items():
        state.setdefault(key, value.copy())
    return state


def save_state(state: dict[str, Any], path: str | Path) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
