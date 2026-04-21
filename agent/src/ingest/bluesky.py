"""Bluesky ingest via atproto SDK."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from atproto import Client

from ..config import Config
from ..handles import Handle
from ..store import Post

log = logging.getLogger(__name__)


def _client(cfg: Config) -> Client:
    c = Client()
    c.login(cfg.bsky_email, cfg.bsky_password)
    return c


def fetch_recent(cfg: Config, handles: list[Handle], per_handle: int = 10) -> list[Post]:
    client = _client(cfg)
    now = datetime.now(timezone.utc).isoformat()
    out: list[Post] = []

    for h in handles:
        if not h.bsky_handle:
            continue
        try:
            res = client.get_author_feed(actor=h.bsky_handle, limit=per_handle)
            profile = client.get_profile(actor=h.bsky_handle)
            followers = int(getattr(profile, "followers_count", 0) or 0)
            for item in res.feed:
                post_rec = item.post
                record = post_rec.record
                # skip reposts & replies
                if getattr(item, "reason", None) is not None:
                    continue
                if getattr(record, "reply", None) is not None:
                    continue
                text = getattr(record, "text", "") or ""
                uri = post_rec.uri
                rkey = uri.split("/")[-1]
                url = f"https://bsky.app/profile/{h.bsky_handle}/post/{rkey}"
                created = _iso(getattr(record, "created_at", None))
                out.append(Post(
                    platform="bluesky",
                    platform_id=uri,
                    author_handle=h.bsky_handle,
                    author_slug=h.slug,
                    author_followers=followers,
                    text=text,
                    url=url,
                    likes=int(getattr(post_rec, "like_count", 0) or 0),
                    retweets=int(getattr(post_rec, "repost_count", 0) or 0),
                    replies=int(getattr(post_rec, "reply_count", 0) or 0),
                    created_at=created,
                    fetched_at=now,
                ))
        except Exception as e:
            log.warning("bluesky: fetch failed for %s: %s", h.bsky_handle, e)
            continue

    return out


def _iso(v) -> str:
    if v is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat()
    return str(v)
