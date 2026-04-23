"""Telegram post formatter."""
from __future__ import annotations

from datetime import datetime, timezone

from ..store import Post


def _signature() -> str:
    now = datetime.now(timezone.utc)
    ts = now.strftime("%b %-d %-I:%M") + now.strftime("%p").lower() + " UTC"
    return f"— SignalCl · {ts}"

THREAD_EMOJI = {
    "pulse": "📡",
    "compression": "⚡",
    "codebook": "📘",
    "frontier": "🔭",
    "onchain": "⛓",
}


def render(post: Post, topic: str, layers: list[str]) -> str:
    emoji = THREAD_EMOJI.get(topic, "📡")
    engagement_bits = []
    if post.likes:
        engagement_bits.append(f"{_k(post.likes)} likes")
    if post.retweets:
        engagement_bits.append(f"{_k(post.retweets)} RTs")
    if post.replies:
        engagement_bits.append(f"{_k(post.replies)} replies")
    engagement = " · ".join(engagement_bits) if engagement_bits else ""
    header = f"{emoji} @{post.author_handle} · {engagement}" if engagement else f"{emoji} @{post.author_handle}"

    body = post.text.strip()
    if len(body) > 800:
        body = body[:797] + "…"

    l_tag = " · ".join(layers) if layers else ""
    footer = f"🔗 {post.url}"
    if l_tag:
        footer += f"\nL: {l_tag}"

    return f"{header}\n\n{body}\n\n{footer}\n\n{_signature()}"


def _k(n: int) -> str:
    if n < 1000:
        return str(n)
    return f"{n / 1000:.1f}k".rstrip("0").rstrip(".")
