"""Build data/handles.json from the individuals.csv + companies.csv in the repo root.

Run once after creating the agent/, and re-run any time the CSVs change.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
INDIVIDUALS = REPO_ROOT / "individuals.csv"
COMPANIES = REPO_ROOT / "companies.csv"
OUT = AGENT_DIR / "data" / "handles.json"

# Only these people have a known Bluesky handle today; extend as verified.
BSKY_MAP = {
    "maggie_appleton": "maggieappleton.com",
    "erin_mikail_staples": "erinmikail.bsky.social",
}

# Unverified handles — mark disabled until user confirms (see plan.md data flags).
DISABLED_SLUGS = {
    "lior_ben_david",       # #65 — name mismatch
    "roei_ganzarski",       # #66 — LinkedIn-only
    "paulina_xu",           # #67 — proxy via @agenticfabriq instead
    "priya_nair",           # #79 — title + handle unclear
    "fiona_cicconi",        # #80 — no public X
    # Invisible to X API v2 (protected/restricted accounts returning 404):
    "evan_you",             # #61 — @youyuxi (exists on web, API 404)
    "sherry_ruan",          # #68 — @sherrysruan (exists on web, API 404)
}


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def clean_x(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw or raw.lower().startswith("unverified"):
        return None
    if raw.lower().startswith("x primary"):
        return None
    # take first @handle token
    m = re.search(r"@([A-Za-z0-9_]+)", raw)
    if not m:
        return None
    return m.group(1)


def clean_rss(raw: str) -> str | None:
    raw = (raw or "").strip()
    return raw if raw else None


def load_individuals() -> list[dict]:
    rows = []
    with open(INDIVIDUALS, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = row["Name"].strip()
            slug = slugify(name)
            x_handle = clean_x(row.get("X Handle", ""))
            bsky = BSKY_MAP.get(slug)
            rss_url = clean_rss(row.get("RSS Feed", ""))
            enabled = slug not in DISABLED_SLUGS and (
                x_handle is not None or bsky is not None or rss_url is not None
            )
            rows.append({
                "slug": slug,
                "kind": "individual",
                "name": name,
                "tier": int(row["Tier"]),
                "x_handle": x_handle,
                "bsky_handle": bsky,
                "rss_url": rss_url,
                "agentic_stack": row.get("Agentic Stack", "").strip(),
                "stack_type": row.get("Stack Type", "").strip(),
                "org_stack": row.get("Org Stack", "").strip(),
                "role": row.get("Role", "").strip(),
                "signal_note": row.get("Signal", "").strip(),
                "enabled": enabled,
            })
    return rows


def load_companies() -> list[dict]:
    rows = []
    with open(COMPANIES, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = row["Company"].strip()
            slug = slugify(name)
            x_handle = clean_x(row.get("X Handle", ""))
            rss_url = clean_rss(row.get("RSS Feed", ""))
            enabled = x_handle is not None or rss_url is not None
            rows.append({
                "slug": slug,
                "kind": "company",
                "name": name,
                "tier": 4,
                "x_handle": x_handle,
                "bsky_handle": None,
                "rss_url": rss_url,
                "agentic_stack": row.get("Agentic Stack", "").strip(),
                "stack_type": row.get("Stack Type", "").strip(),
                "org_stack": "",
                "role": "company",
                "signal_note": row.get("Case Study Value", "").strip(),
                "enabled": enabled,
            })
    return rows


def main() -> None:
    if not INDIVIDUALS.exists() or not COMPANIES.exists():
        print(f"ERROR: expected {INDIVIDUALS} and {COMPANIES}", file=sys.stderr)
        sys.exit(1)

    rows = load_individuals() + load_companies()
    OUT.parent.mkdir(exist_ok=True, parents=True)
    OUT.write_text(json.dumps(rows, indent=2))

    x_count = sum(1 for r in rows if r["enabled"] and r["x_handle"])
    bsky_count = sum(1 for r in rows if r["enabled"] and r["bsky_handle"])
    rss_count = sum(1 for r in rows if r["enabled"] and r["rss_url"])
    disabled = sum(1 for r in rows if not r["enabled"])
    print(f"wrote {OUT} · {len(rows)} total · {x_count} x-enabled · {bsky_count} bsky-enabled · {rss_count} rss-enabled · {disabled} disabled")


if __name__ == "__main__":
    main()
