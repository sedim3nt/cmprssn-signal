"""X/Twitter ingest via official API v2 with bearer token.

User's existing TWITTER_BEARER_TOKEN is Pro-tier (10k req / 15min), plenty of headroom.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import Config, DATA_DIR, TWEETS_PER_HANDLE
from ..handles import Handle
from ..store import Post

log = logging.getLogger(__name__)

API_BASE = "https://api.twitter.com/2"
USER_CACHE_PATH: Path = DATA_DIR / "x_user_cache.json"


def _load_user_cache() -> dict:
    if USER_CACHE_PATH.exists():
        try:
            return json.loads(USER_CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_user_cache(cache: dict) -> None:
    USER_CACHE_PATH.write_text(json.dumps(cache, indent=2))


def _client(cfg: Config) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {cfg.x_bearer_token}"},
        timeout=15.0,
    )


def _resolve_user(client: httpx.Client, username: str, cache: dict) -> tuple[str, int] | None:
    """Returns (user_id, followers_count) or None. Caches by username."""
    if username in cache:
        entry = cache[username]
        return entry["id"], entry.get("followers", 0)

    r = client.get(
        f"/users/by/username/{username}",
        params={"user.fields": "public_metrics"},
    )
    if r.status_code != 200:
        log.warning("x: user lookup failed @%s status=%d body=%s", username, r.status_code, r.text[:120])
        return None
    j = r.json()
    data = j.get("data")
    if not data:
        log.warning("x: no data for @%s: %s", username, j.get("errors"))
        return None
    uid = data["id"]
    followers = int(data.get("public_metrics", {}).get("followers_count", 0))
    cache[username] = {"id": uid, "followers": followers, "cached_at": datetime.now(timezone.utc).isoformat()}
    return uid, followers


def _fetch_tweets(client: httpx.Client, user_id: str, count: int) -> tuple[list[dict], int | None]:
    """Returns (tweets, rate_limit_remaining). remaining is None if header absent."""
    r = client.get(
        f"/users/{user_id}/tweets",
        params={
            "max_results": max(5, min(count, 100)),
            "exclude": "retweets,replies",
            "tweet.fields": "public_metrics,created_at",
        },
    )
    remaining = _int_header(r, "x-rate-limit-remaining")
    if r.status_code == 429:
        reset = r.headers.get("x-rate-limit-reset", "?")
        log.warning("x: rate limited (429), reset at %s", reset)
        return [], remaining
    if r.status_code == 402:
        log.error("x: 402 CreditsDepleted — top up at https://console.x.com/")
        return [], remaining
    if r.status_code != 200:
        log.warning("x: tweets fetch status=%d body=%s", r.status_code, r.text[:200])
        return [], remaining
    return r.json().get("data", []) or [], remaining


def _int_header(r: httpx.Response, key: str) -> int | None:
    v = r.headers.get(key)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


async def fetch_recent(cfg: Config, handles: list[Handle], per_handle: int = TWEETS_PER_HANDLE) -> list[Post]:
    """Fetch latest original tweets from each handle via official API.

    Individual handle failures are isolated — one bad handle doesn't kill the run.
    """
    now = datetime.now(timezone.utc).isoformat()
    out: list[Post] = []
    cache = _load_user_cache()
    ok_count = fail_count = 0
    last_remaining: int | None = None

    with _client(cfg) as client:
        for h in handles:
            if not h.x_handle:
                continue
            screen = h.x_handle.lstrip("@")
            try:
                resolved = _resolve_user(client, screen, cache)
                if not resolved:
                    fail_count += 1
                    continue
                user_id, followers = resolved
                tweets, remaining = _fetch_tweets(client, user_id, per_handle)
                if remaining is not None:
                    last_remaining = remaining
                ok_count += 1
                for t in tweets:
                    pm = t.get("public_metrics") or {}
                    out.append(Post(
                        platform="x",
                        platform_id=str(t["id"]),
                        author_handle=screen,
                        author_slug=h.slug,
                        author_followers=followers,
                        text=t.get("text", ""),
                        url=f"https://x.com/{screen}/status/{t['id']}",
                        likes=int(pm.get("like_count", 0)),
                        retweets=int(pm.get("retweet_count", 0)),
                        replies=int(pm.get("reply_count", 0)),
                        created_at=t.get("created_at") or now,
                        fetched_at=now,
                    ))
            except Exception as e:
                fail_count += 1
                log.warning("x: unexpected error for @%s: %s", screen, e)
                continue

    _save_user_cache(cache)
    log.info("x: fetched from %d/%d handles (failed=%d) · rate_remaining=%s · posts=%d",
             ok_count, ok_count + fail_count, fail_count, last_remaining, len(out))
    return out
