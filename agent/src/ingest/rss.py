"""RSS/Atom ingest for Substack, personal blogs, and YouTube channel feeds.

Engagement metrics are unavailable for RSS — all posts pass the quant gate
(handled in score/quant.py) and rely entirely on the qualitative gate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ..config import Config, RSS_MAX_ENTRIES, RSS_MAX_AGE_DAYS
from ..handles import Handle
from ..store import Post

log = logging.getLogger(__name__)

_CUTOFF_SECS = RSS_MAX_AGE_DAYS * 86400


def _parse_dt(entry) -> str:
    """Best-effort published timestamp → ISO string."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def _too_old(iso: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > _CUTOFF_SECS
    except Exception:
        return False


def fetch_recent(_cfg: Config, handles: list[Handle], max_entries: int = RSS_MAX_ENTRIES) -> list[Post]:
    """Fetch recent entries from each handle's rss_url."""
    now = datetime.now(timezone.utc).isoformat()
    out: list[Post] = []
    ok_count = fail_count = 0

    for h in handles:
        if not h.rss_url:
            continue
        try:
            feed = feedparser.parse(h.rss_url)
            if feed.bozo and not feed.entries:
                log.warning("rss: malformed feed for %s (%s): %s", h.slug, h.rss_url, feed.bozo_exception)
                fail_count += 1
                continue

            entries = feed.entries[:max_entries]
            ok_count += 1
            for entry in entries:
                created = _parse_dt(entry)
                if _too_old(created):
                    continue

                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                # prefer full content when available
                content_list = getattr(entry, "content", None)
                body = content_list[0].value if content_list else summary
                # strip HTML tags crudely — Claude will see the text
                import re
                body_text = re.sub(r"<[^>]+>", " ", body).strip()
                text = f"{title}\n\n{body_text}"[:2000] if body_text else title

                link = getattr(entry, "link", "") or h.rss_url
                uid = getattr(entry, "id", None) or link

                out.append(Post(
                    platform="rss",
                    platform_id=uid,
                    author_handle=h.slug,
                    author_slug=h.slug,
                    author_followers=None,
                    text=text,
                    url=link,
                    likes=0,
                    retweets=0,
                    replies=0,
                    created_at=created,
                    fetched_at=now,
                ))
        except Exception as e:
            fail_count += 1
            log.warning("rss: fetch failed for %s (%s): %s", h.slug, h.rss_url, e)
            continue

    log.info("rss: fetched from %d/%d handles (failed=%d) · posts=%d",
             ok_count, ok_count + fail_count, fail_count, len(out))
    return out


def rss_handles(handles: list[Handle]) -> list[Handle]:
    return [h for h in handles if h.enabled and h.rss_url]
