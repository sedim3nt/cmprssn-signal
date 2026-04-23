"""Main pipeline. Fetch → dedup → quant gate → qualitative gate → publish."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from .config import (
    Config, LOGS_DIR, MAX_POSTS_PER_RUN, MAX_POSTS_PER_TOPIC_PER_RUN, MIN_QUAL_SCORE,
)
from . import handles as handles_mod
from . import store as store_mod
from .ingest import bluesky as bluesky_ingest
from .ingest import rss as rss_ingest
from .ingest import x as x_ingest
from .publish import digest as digest_mod
from .publish import format as fmt
from .publish import telegram as tg
from .score import qualitative, quant


def setup_logging() -> None:
    logfile = LOGS_DIR / f"run-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(logfile),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # httpx is chatty — keep only warnings
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def run_once(cfg: Config) -> dict:
    log = logging.getLogger("orchestrator")
    handles = handles_mod.load()
    enabled = handles_mod.enabled(handles)
    slug_to_handle = {h.slug: h for h in enabled}
    screen_to_handle = {
        (h.x_handle.lstrip("@").lower() if h.x_handle else None): h
        for h in enabled if h.x_handle
    }

    stats = {"fetched_x": 0, "fetched_bsky": 0, "fetched_rss": 0, "new": 0,
             "quant_pass": 0, "qual_pass": 0, "posted": 0, "posted_err": 0, "capped": 0}

    # --- X ---
    try:
        x_posts = await x_ingest.fetch_recent(cfg, handles_mod.x_handles(enabled))
        stats["fetched_x"] = len(x_posts)
    except Exception as e:
        log.error("x ingest failed: %s", e)
        x_posts = []

    # --- Bluesky ---
    try:
        bsky_posts = bluesky_ingest.fetch_recent(cfg, handles_mod.bsky_handles(enabled))
        stats["fetched_bsky"] = len(bsky_posts)
    except Exception as e:
        log.error("bsky ingest failed: %s", e)
        bsky_posts = []

    # --- RSS / Substack / YouTube ---
    try:
        rss_posts = rss_ingest.fetch_recent(cfg, handles_mod.rss_handles(enabled))
        stats["fetched_rss"] = len(rss_posts)
    except Exception as e:
        log.error("rss ingest failed: %s", e)
        rss_posts = []

    log.info("ingest complete: x=%d bsky=%d rss=%d",
             stats["fetched_x"], stats["fetched_bsky"], stats["fetched_rss"])

    # --- Dedup + store ---
    all_posts = x_posts + bsky_posts + rss_posts
    fresh = []
    for p in all_posts:
        if store_mod.exists(p.platform, p.platform_id):
            continue
        rid = store_mod.upsert_post(p)
        p.id = rid
        fresh.append(p)
    stats["new"] = len(fresh)
    log.info("%d fresh posts after dedup", len(fresh))

    # --- Quant gate ---
    passed_quant = []
    for p in fresh:
        h = slug_to_handle.get(p.author_slug) or screen_to_handle.get(p.author_handle.lower())
        ok, ratio = quant.passes(p, h)
        store_mod.mark_quant(p.id, ok, ratio)
        if ok:
            passed_quant.append((p, h))
    stats["quant_pass"] = len(passed_quant)
    log.info("%d posts passed quant gate", len(passed_quant))

    # --- Rescore posts that previously failed due to Claude CLI session limit ---
    for row in store_mod.failed_qualitative(limit=50):
        p = store_mod.row_to_post(row)
        h = slug_to_handle.get(p.author_slug) or screen_to_handle.get((p.author_handle or "").lower())
        v = qualitative.score(p, h)
        store_mod.mark_qualitative(p.id, v.relevant, v.score, v.topic, v.layers, v.reason)
        log.info("rescore @%s score=%d rel=%s", p.author_handle, v.score, v.relevant)

    # --- Qualitative gate (Claude CLI) ---
    passed_qual: list[tuple] = []
    for p, h in passed_quant:
        v = qualitative.score(p, h)
        store_mod.mark_qualitative(p.id, v.relevant, v.score, v.topic, v.layers, v.reason)
        log.info(
            "qual @%s score=%d rel=%s topic=%s :: %s",
            p.author_handle, v.score, v.relevant, v.topic, v.reason[:80],
        )
        if v.relevant and v.score >= MIN_QUAL_SCORE:
            passed_qual.append((p, h, v))
    stats["qual_pass"] = len(passed_qual)
    log.info("%d posts passed qualitative gate (threshold=%d)", len(passed_qual), MIN_QUAL_SCORE)

    # --- Rank + apply per-run caps ---
    passed_qual.sort(key=lambda t: (t[2].score, t[0].likes), reverse=True)
    per_topic: dict[str, int] = {}
    selected: list[tuple] = []
    capped: list[tuple] = []
    for p, h, v in passed_qual:
        if len(selected) >= MAX_POSTS_PER_RUN:
            capped.append((p, h, v))
            continue
        if per_topic.get(v.topic, 0) >= MAX_POSTS_PER_TOPIC_PER_RUN:
            capped.append((p, h, v))
            continue
        per_topic[v.topic] = per_topic.get(v.topic, 0) + 1
        selected.append((p, h, v))
    stats["capped"] = len(capped)
    log.info("cap: selecting %d / %d (capped=%d) · per_topic=%s",
             len(selected), len(passed_qual), len(capped), per_topic)

    # --- Publish ---
    if cfg.dry_run:
        for p, h, v in selected:
            text = fmt.render(p, v.topic, v.layers)
            log.info("[DRY] would post to %s:\n%s\n---", v.topic, text)
        return stats

    for p, h, v in selected:
        text = fmt.render(p, v.topic, v.layers)
        ok, mid, err = tg.send(cfg, v.topic, text)
        if ok:
            store_mod.mark_posted(p.id, v.topic, mid, tg.now_iso())
            stats["posted"] += 1
            log.info("posted %s → %s (msg_id=%s)", p.author_handle, v.topic, mid)
        else:
            stats["posted_err"] += 1
            log.error("post failed for @%s → %s: %s", p.author_handle, v.topic, err)
        await asyncio.sleep(1.0)

    # --- Admin digest → General topic ---
    try:
        digest_text = digest_mod.build_run_digest(stats, selected)
        ok, mid, err = tg.send(cfg, "general", digest_text)
        if ok:
            log.info("digest posted to general (msg_id=%s)", mid)
        else:
            log.warning("digest post failed: %s", err)
    except Exception as e:
        log.warning("digest build/post failed: %s", e)

    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="score and log, no publish")
    args = ap.parse_args()

    setup_logging()
    cfg = Config.from_env(dry_run=args.dry_run)
    store_mod.init_db()

    stats = asyncio.run(run_once(cfg))
    logging.getLogger("orchestrator").info("run complete: %s", stats)


if __name__ == "__main__":
    main()
