"""One-shot: push a digest summarizing posts published today to the General topic.

Useful for backfilling the admin channel after a manual batch run.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config
from src import store as store_mod
from src.publish import digest as digest_mod
from src.publish import telegram as tg


def posted_since(since_iso: str) -> list[sqlite3.Row]:
    with store_mod.conn() as c:
        return list(c.execute(
            """
            SELECT * FROM posts
            WHERE posted_to_tg=1 AND posted_at >= ?
            ORDER BY qualitative_score DESC, posted_at DESC
            """,
            (since_iso,),
        ))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
    log = logging.getLogger("push_digest")

    cfg = Config.from_env(dry_run=False)
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = posted_since(since)
    log.info("posts published today: %d", len(rows))

    text = digest_mod.build_window_digest(rows, label="Backfill digest · today")
    ok, mid, err = tg.send(cfg, "general", text)
    if ok:
        log.info("digest posted to general (msg_id=%d)", mid)
    else:
        log.error("digest post failed: %s", err)


if __name__ == "__main__":
    main()
