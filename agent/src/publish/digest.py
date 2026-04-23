"""Post-run digest for the General admin channel.

Summarizes each scheduled run: fetched/passed/posted counts and top headlines
by qualitative score, so you can glance at General and see the bot's health +
the highest-signal items without scrolling 5 topic channels.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..store import Post
from .format import _signature

TOPIC_EMOJI = {
    "pulse": "📡",
    "compression": "⚡",
    "codebook": "📘",
    "frontier": "🔭",
    "onchain": "⛓",
}


def _truncate(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def build_run_digest(stats: dict, selected: list[tuple]) -> str:
    """Digest for a freshly completed orchestrator run.

    `selected` is the list of (post, handle, verdict) tuples actually posted.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fetched_total = stats.get("fetched_x", 0) + stats.get("fetched_bsky", 0) + stats.get("fetched_rss", 0)

    lines = [
        f"🤖 Run complete · {ts}",
        "",
        f"Fetched: x={stats.get('fetched_x',0)} · bsky={stats.get('fetched_bsky',0)} · rss={stats.get('fetched_rss',0)} (total {fetched_total})",
        f"New (post-dedup): {stats.get('new',0)}",
        f"Quant gate passed: {stats.get('quant_pass',0)}",
        f"Qualitative gate passed: {stats.get('qual_pass',0)}",
        f"Posted: {stats.get('posted',0)} · capped: {stats.get('capped',0)} · errors: {stats.get('posted_err',0)}",
    ]

    if selected:
        ranked = sorted(selected, key=lambda t: t[2].score, reverse=True)[:3]
        lines.append("")
        lines.append("🏆 Top signals this run:")
        for p, _h, v in ranked:
            emoji = TOPIC_EMOJI.get(v.topic, "📡")
            lines.append(f"  {emoji} {v.score}/10 · @{p.author_handle}")
            lines.append(f"     {_truncate(p.text, 120)}")
            lines.append(f"     {p.url}")

    lines.append("")
    lines.append(_signature())
    return "\n".join(lines)


def build_window_digest(rows: list, label: str) -> str:
    """Digest for a time window (used by push_digest_now.py backfill).

    `rows` is a list of sqlite Row objects with posted=1. Buckets by topic and
    surfaces top 3 by score.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_topic: dict[str, int] = {}
    for r in rows:
        t = r["posted_topic"] or "pulse"
        by_topic[t] = by_topic.get(t, 0) + 1
    topic_str = " · ".join(f"{TOPIC_EMOJI.get(k,'')}{k}={v}" for k, v in by_topic.items()) or "none"

    lines = [
        f"🤖 {label} · {ts}",
        "",
        f"Posted: {len(rows)} ({topic_str})",
    ]

    if rows:
        ranked = sorted(rows, key=lambda r: (r["qualitative_score"] or 0), reverse=True)[:3]
        lines.append("")
        lines.append("🏆 Top signals:")
        for r in ranked:
            emoji = TOPIC_EMOJI.get(r["posted_topic"] or "pulse", "📡")
            lines.append(f"  {emoji} {r['qualitative_score']}/10 · @{r['author_handle']}")
            lines.append(f"     {_truncate(r['text'], 120)}")
            lines.append(f"     {r['url']}")

    lines.append("")
    lines.append(_signature())
    return "\n".join(lines)
