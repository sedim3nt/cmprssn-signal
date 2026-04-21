"""Config + env loading. Only loads vars the agent actually needs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]  # /Users/.../csv
ENV_PATH = REPO_ROOT / ".env"
load_dotenv(ENV_PATH)

AGENT_DIR = Path(__file__).resolve().parents[1]  # /Users/.../csv/agent
DATA_DIR = AGENT_DIR / "data"
LOGS_DIR = AGENT_DIR / "logs"
PROMPTS_DIR = AGENT_DIR / "src" / "prompts"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

HANDLES_PATH = DATA_DIR / "handles.json"
DB_PATH = DATA_DIR / "agent.db"
X_COOKIES_PATH = DATA_DIR / "x_cookies.json"


def _env(key: str, required: bool = True) -> str:
    v = os.environ.get(key, "").strip()
    if required and not v:
        raise RuntimeError(f"Missing required env var: {key}")
    return v


@dataclass(frozen=True)
class Config:
    # Telegram
    tg_bot_token: str
    tg_chat_id: str
    tg_topic_pulse: int
    tg_topic_compression: int
    tg_topic_codebook: int
    tg_topic_frontier: int
    tg_topic_onchain: int
    tg_topic_general: int  # admin/digest channel
    # X — official API (preferred)
    x_bearer_token: str
    # Bluesky
    bsky_email: str
    bsky_password: str
    # Runtime
    dry_run: bool = False

    @classmethod
    def from_env(cls, dry_run: bool = False) -> Config:
        return cls(
            tg_bot_token=_env("TELEGRAM_CMPRSSN_BOT_TOKEN"),
            tg_chat_id=_env("TELEGRAM_CMPRSSN_CHAT_ID"),
            tg_topic_pulse=int(_env("TELEGRAM_CMPRSSN_TOPIC_PULSE")),
            tg_topic_compression=int(_env("TELEGRAM_CMPRSSN_TOPIC_COMPRESSION")),
            tg_topic_codebook=int(_env("TELEGRAM_CMPRSSN_TOPIC_CODEBOOK")),
            tg_topic_frontier=int(_env("TELEGRAM_CMPRSSN_TOPIC_FRONTIER")),
            tg_topic_onchain=int(_env("TELEGRAM_CMPRSSN_TOPIC_ONCHAIN")),
            tg_topic_general=int(os.environ.get("TELEGRAM_CMPRSSN_TOPIC_GENERAL", "0")),
            x_bearer_token=_env("TWITTER_BEARER_TOKEN"),
            bsky_email=_env("BLUESKY_EMAIL"),
            bsky_password=_env("BLUESKY_APP_PASSWORD"),
            dry_run=dry_run,
        )

    def topic_for(self, name: str) -> int:
        m = {
            "pulse": self.tg_topic_pulse,
            "compression": self.tg_topic_compression,
            "codebook": self.tg_topic_codebook,
            "frontier": self.tg_topic_frontier,
            "onchain": self.tg_topic_onchain,
            "general": self.tg_topic_general,
        }
        return m[name]


def _ienv(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip() or default)
    except ValueError:
        return default


def _fenv(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "").strip() or default)
    except ValueError:
        return default


# Signal gate thresholds — env-overridable via .env (set by setup wizard)
MIN_LIKES_FLOOR = _ienv("MIN_LIKES_FLOOR", 25)
MIN_LIKES_FLOOR_TIER3 = _ienv("MIN_LIKES_FLOOR_TIER3", 10)
ENGAGEMENT_RATIO_MIN = _fenv("ENGAGEMENT_RATIO_MIN", 0.001)  # 1 like per 1000 followers

# Qualitative gate — only publish posts scoring >= this
MIN_QUAL_SCORE = _ienv("MIN_QUAL_SCORE", 6)

# Per-run publish caps — prevents burst spam in a single cycle
MAX_POSTS_PER_RUN = _ienv("MAX_POSTS_PER_RUN", 15)
MAX_POSTS_PER_TOPIC_PER_RUN = _ienv("MAX_POSTS_PER_TOPIC_PER_RUN", 5)

# Poll cadence (informational — actual schedule lives in launchd plist)
POLL_INTERVAL_MIN = _ienv("POLL_INTERVAL_MIN", 360)  # default 6h = 4x/day
TWEETS_PER_HANDLE = _ienv("TWEETS_PER_HANDLE", 10)

# RSS / Substack / YouTube feeds
RSS_MAX_ENTRIES = _ienv("RSS_MAX_ENTRIES", 5)
RSS_MAX_AGE_DAYS = _ienv("RSS_MAX_AGE_DAYS", 3)

# Claude CLI
CLAUDE_CMD = os.environ.get("CLAUDE_CMD", "claude")
CLAUDE_TIMEOUT_S = _ienv("CLAUDE_TIMEOUT_S", 60)
