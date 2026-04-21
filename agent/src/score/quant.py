"""Stage 1 gate: engagement-based filter. Tier-aware."""
from __future__ import annotations

from ..config import ENGAGEMENT_RATIO_MIN, MIN_LIKES_FLOOR, MIN_LIKES_FLOOR_TIER3
from ..handles import Handle
from ..store import Post


def passes(post: Post, handle: Handle | None) -> tuple[bool, float]:
    """Returns (passed, engagement_ratio).

    RSS/blog posts have no engagement metrics — they auto-pass and go straight
    to the qualitative gate.
    """
    if post.platform == "rss":
        return True, 1.0

    likes = max(post.likes, 0)
    followers = max(post.author_followers or 0, 1000)  # guard against zero-div

    # Absolute floor (tier-adjusted)
    floor = MIN_LIKES_FLOOR_TIER3 if (handle and handle.tier == 3) else MIN_LIKES_FLOOR
    if likes < floor:
        return False, 0.0

    ratio = likes / followers
    if ratio < ENGAGEMENT_RATIO_MIN:
        return False, ratio

    return True, ratio
