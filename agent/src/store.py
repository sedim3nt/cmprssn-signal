"""SQLite-backed tweet store. Dedup by platform_id, tracks publish state."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,              -- 'x' | 'bluesky'
    platform_id TEXT NOT NULL,           -- tweet_id / post_uri
    author_handle TEXT NOT NULL,
    author_slug TEXT,                    -- our internal slug
    author_followers INTEGER,
    text TEXT NOT NULL,
    url TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    retweets INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,            -- ISO
    fetched_at TEXT NOT NULL,

    -- scoring
    passed_quant INTEGER DEFAULT 0,
    quant_ratio REAL,
    qualitative_score INTEGER,
    qualitative_topic TEXT,
    qualitative_layers TEXT,             -- JSON array
    qualitative_reason TEXT,
    qualitative_relevant INTEGER,

    -- publish state
    posted_to_tg INTEGER DEFAULT 0,
    posted_topic TEXT,
    posted_at TEXT,
    tg_message_id INTEGER,

    UNIQUE(platform, platform_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_unposted
    ON posts(passed_quant, qualitative_relevant, posted_to_tg);
CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_handle);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at);
"""


@dataclass
class Post:
    platform: str
    platform_id: str
    author_handle: str
    author_slug: str | None
    author_followers: int | None
    text: str
    url: str
    likes: int
    retweets: int
    replies: int
    created_at: str
    fetched_at: str
    id: int | None = None
    passed_quant: bool = False
    quant_ratio: float | None = None
    qualitative_score: int | None = None
    qualitative_topic: str | None = None
    qualitative_layers: list[str] = field(default_factory=list)
    qualitative_reason: str | None = None
    qualitative_relevant: bool | None = None
    posted_to_tg: bool = False
    posted_topic: str | None = None
    posted_at: str | None = None
    tg_message_id: int | None = None


def init_db(path: Path = DB_PATH) -> None:
    with sqlite3.connect(path) as c:
        c.executescript(SCHEMA)


@contextmanager
def conn():
    init_db()
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def upsert_post(p: Post) -> int:
    """Insert new, or no-op if exists. Returns row id."""
    with conn() as c:
        cur = c.execute(
            """
            INSERT OR IGNORE INTO posts (
                platform, platform_id, author_handle, author_slug, author_followers,
                text, url, likes, retweets, replies, created_at, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p.platform, p.platform_id, p.author_handle, p.author_slug, p.author_followers,
                p.text, p.url, p.likes, p.retweets, p.replies, p.created_at, p.fetched_at,
            ),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = c.execute(
            "SELECT id FROM posts WHERE platform=? AND platform_id=?",
            (p.platform, p.platform_id),
        ).fetchone()
        return row["id"]


def exists(platform: str, platform_id: str) -> bool:
    with conn() as c:
        row = c.execute(
            "SELECT 1 FROM posts WHERE platform=? AND platform_id=?",
            (platform, platform_id),
        ).fetchone()
    return row is not None


def mark_quant(post_id: int, passed: bool, ratio: float) -> None:
    with conn() as c:
        c.execute(
            "UPDATE posts SET passed_quant=?, quant_ratio=? WHERE id=?",
            (1 if passed else 0, ratio, post_id),
        )


def mark_qualitative(
    post_id: int,
    relevant: bool,
    score: int,
    topic: str,
    layers: list[str],
    reason: str,
) -> None:
    import json as _j
    with conn() as c:
        c.execute(
            """
            UPDATE posts
            SET qualitative_relevant=?, qualitative_score=?,
                qualitative_topic=?, qualitative_layers=?, qualitative_reason=?
            WHERE id=?
            """,
            (1 if relevant else 0, score, topic, _j.dumps(layers), reason, post_id),
        )


def mark_posted(post_id: int, topic: str, tg_message_id: int, at_iso: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE posts SET posted_to_tg=1, posted_topic=?, posted_at=?, tg_message_id=? WHERE id=?",
            (topic, at_iso, tg_message_id, post_id),
        )


def pending_to_publish() -> list[sqlite3.Row]:
    """Posts that passed both gates and haven't been sent to Telegram."""
    with conn() as c:
        return list(c.execute(
            """
            SELECT * FROM posts
            WHERE passed_quant=1 AND qualitative_relevant=1 AND posted_to_tg=0
            ORDER BY qualitative_score DESC, created_at DESC
            """
        ))


def recent_fetched(platform: str, since_iso: str) -> list[sqlite3.Row]:
    with conn() as c:
        return list(c.execute(
            "SELECT * FROM posts WHERE platform=? AND fetched_at>=? ORDER BY fetched_at DESC",
            (platform, since_iso),
        ))
