"""LinkedIn ingest — stubbed. Requires Proxycurl or similar paid API.

To enable: set PROXYCURL_API_KEY in .env and implement fetch_recent().
"""
from __future__ import annotations

import logging

from ..config import Config
from ..handles import Handle
from ..store import Post

log = logging.getLogger(__name__)


def fetch_recent(_cfg: Config, _handles: list[Handle]) -> list[Post]:
    log.debug("linkedin: ingest not implemented (stub)")
    return []
