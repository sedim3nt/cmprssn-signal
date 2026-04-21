"""Full pipeline in dry-run mode. No Telegram posts sent."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config
from src.orchestrator import run_once, setup_logging
from src.store import init_db


def main() -> None:
    setup_logging()
    cfg = Config.from_env(dry_run=True)
    init_db()
    stats = asyncio.run(run_once(cfg))
    print("\n=== run complete ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
