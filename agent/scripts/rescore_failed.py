"""Re-score posts that failed qualitative scoring (score=0, reason contains 'Credit balance').

Usage:
    python scripts/rescore_failed.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_DIR))

from src import store as store_mod
from src.score import qualitative as qual_mod
from src.store import Post


def _row_to_post(row: sqlite3.Row) -> Post:
    import json
    layers = []
    if row["qualitative_layers"]:
        try:
            layers = json.loads(row["qualitative_layers"])
        except Exception:
            pass
    return Post(
        id=row["id"],
        platform=row["platform"],
        platform_id=row["platform_id"],
        author_handle=row["author_handle"],
        author_slug=row["author_slug"],
        author_followers=row["author_followers"],
        text=row["text"],
        url=row["url"],
        likes=row["likes"],
        retweets=row["retweets"],
        replies=row["replies"],
        created_at=row["created_at"],
        fetched_at=row["fetched_at"],
        passed_quant=bool(row["passed_quant"]),
        quant_ratio=row["quant_ratio"],
        qualitative_score=row["qualitative_score"],
        qualitative_topic=row["qualitative_topic"],
        qualitative_layers=layers,
        qualitative_reason=row["qualitative_reason"],
        qualitative_relevant=bool(row["qualitative_relevant"]) if row["qualitative_relevant"] is not None else None,
        posted_to_tg=bool(row["posted_to_tg"]),
        posted_topic=row["posted_topic"],
        posted_at=row["posted_at"],
        tg_message_id=row["tg_message_id"],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    store_mod.init_db()

    with store_mod.conn() as c:
        rows = list(c.execute("""
            SELECT * FROM posts
            WHERE passed_quant=1
              AND posted_to_tg=0
              AND (qualitative_score=0 OR qualitative_score IS NULL)
              AND (qualitative_reason LIKE '%Credit balance%'
                   OR qualitative_reason LIKE '%no json%'
                   OR qualitative_score IS NULL)
            ORDER BY quant_ratio DESC
            LIMIT ?
        """, (args.limit,)))

    print(f"Found {len(rows)} posts to rescore")
    if not rows:
        print("Nothing to do.")
        return

    rescored = 0
    newly_relevant = 0

    for row in rows:
        post = _row_to_post(row)
        print(f"  scoring id={post.id} @{post.author_handle} ... ", end="", flush=True)

        if args.dry_run:
            print("(dry-run skip)")
            continue

        try:
            verdict = qual_mod.score(post, None)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        store_mod.mark_qualitative(post.id, verdict.relevant, verdict.score, verdict.topic, verdict.layers, verdict.reason)
        rescored += 1
        if verdict.relevant:
            newly_relevant += 1
            print(f"score={verdict.score} topic={verdict.topic} RELEVANT")
        else:
            print(f"score={verdict.score} topic={verdict.topic}")

        time.sleep(1)  # avoid hammering claude CLI

    print(f"\nRescored: {rescored}  Newly relevant: {newly_relevant}")
    if newly_relevant and not args.dry_run:
        print("Run: python scripts/publish_pending.py  to post them to Telegram")


if __name__ == "__main__":
    main()
