"""Publish any posts in the DB that passed both gates but haven't been sent to Telegram.

Useful when a run scored posts but publishing was deferred (dry-run, credits depleted,
rate limit, etc.). Idempotent — won't double-post.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config
from src import store as store_mod
from src.publish import format as fmt
from src.publish import telegram as tg
from src.store import Post


def row_to_post(row) -> tuple[Post, str, list[str]]:
    layers = json.loads(row["qualitative_layers"]) if row["qualitative_layers"] else []
    p = Post(
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
        id=row["id"],
    )
    return p, row["qualitative_topic"] or "pulse", layers


async def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=15, help="Max posts to send this run")
    ap.add_argument("--max-per-topic", type=int, default=5, help="Max posts per topic")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
    log = logging.getLogger("publish_pending")

    cfg = Config.from_env(dry_run=False)
    rows = store_mod.pending_to_publish()
    log.info("pending: %d · cap: max=%d per_topic=%d", len(rows), args.max, args.max_per_topic)

    if not rows:
        return

    per_topic: dict[str, int] = {}
    sent = 0
    for row in rows:
        if sent >= args.max:
            break
        topic = row["qualitative_topic"] or "pulse"
        if per_topic.get(topic, 0) >= args.max_per_topic:
            continue
        p, topic, layers = row_to_post(row)
        text = fmt.render(p, topic, layers)
        ok, mid, err = tg.send(cfg, topic, text)
        if ok:
            store_mod.mark_posted(p.id, topic, mid, tg.now_iso())
            per_topic[topic] = per_topic.get(topic, 0) + 1
            sent += 1
            log.info("posted %s → %s (msg_id=%d)", p.author_handle, topic, mid)
        else:
            log.error("FAILED %s → %s: %s", p.author_handle, topic, err)
        await asyncio.sleep(1.0)

    log.info("done: sent=%d remaining=%d · per_topic=%s", sent, len(rows) - sent, per_topic)


if __name__ == "__main__":
    asyncio.run(main())
