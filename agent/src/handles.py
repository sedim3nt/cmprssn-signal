"""Handle loader. Reads data/handles.json built by scripts/build_handles.py."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .config import HANDLES_PATH


@dataclass(frozen=True)
class Handle:
    slug: str  # e.g. "dan_shipper" or "T4-1"
    kind: str  # "individual" | "company"
    name: str
    tier: int  # 1/2/3 for individuals; 4 for companies
    x_handle: str | None  # without @, None if unverified
    bsky_handle: str | None  # full did/handle if known
    rss_url: str | None    # Substack /feed, blog RSS, or YouTube channel RSS
    agentic_stack: str  # e.g. "L4-L8"
    stack_type: str
    org_stack: str
    role: str
    signal_note: str
    enabled: bool = True


def load() -> list[Handle]:
    if not HANDLES_PATH.exists():
        raise FileNotFoundError(
            f"{HANDLES_PATH} missing — run `python scripts/build_handles.py` first"
        )
    data = json.loads(HANDLES_PATH.read_text())
    return [Handle(**row) for row in data]


def enabled(handles: list[Handle]) -> list[Handle]:
    return [h for h in handles if h.enabled]


def x_handles(handles: list[Handle]) -> list[Handle]:
    return [h for h in handles if h.enabled and h.x_handle]


def bsky_handles(handles: list[Handle]) -> list[Handle]:
    return [h for h in handles if h.enabled and h.bsky_handle]


def rss_handles(handles: list[Handle]) -> list[Handle]:
    return [h for h in handles if h.enabled and h.rss_url]
