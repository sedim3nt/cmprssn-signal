"""Cold-start backfill. Pulls more tweets per handle on first run.

Same pipeline as orchestrator but with larger per-handle count and dry-run off by default.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config, TWEETS_PER_HANDLE
from src.orchestrator import run_once, setup_logging
from src.store import init_db
from src import config as cfg_mod


def main() -> None:
    setup_logging()
    # Override per-handle fetch count for backfill
    cfg_mod.TWEETS_PER_HANDLE = 40
    cfg = Config.from_env(dry_run="--dry-run" in sys.argv)
    init_db()
    stats = asyncio.run(run_once(cfg))
    print("\n=== backfill complete ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
