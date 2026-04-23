"""Stage 2 gate: Claude CLI subprocess. Returns JSON verdict.

Uses `claude -p` in print mode (non-interactive). No API cost.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field

from ..config import CLAUDE_CMD, CLAUDE_TIMEOUT_S, PROMPTS_DIR
from ..handles import Handle
from ..store import Post

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (PROMPTS_DIR / "signal_score.md").read_text() if (PROMPTS_DIR / "signal_score.md").exists() else ""


_TRANSIENT_ERRORS = ("Credit balance is too low", "rate limit", "overloaded")


@dataclass
class Verdict:
    relevant: bool
    score: int  # 0-10
    topic: str  # pulse | compression | codebook | frontier | onchain
    layers: list[str]  # ['L4', 'L5'] etc
    reason: str
    transient_fail: bool = False  # True = don't persist to DB, retry next run


def score(post: Post, handle: Handle | None) -> Verdict:
    prompt = _render(post, handle)
    raw = _call_claude(prompt)
    return _parse(raw, post)


def _render(post: Post, handle: Handle | None) -> str:
    ctx = {
        "author_name": handle.name if handle else post.author_handle,
        "author_role": handle.role if handle else "unknown",
        "stack_tags": (handle.agentic_stack + " · " + handle.stack_type + " · " + handle.org_stack) if handle else "n/a",
        "author_handle": post.author_handle,
        "tweet_text": post.text.strip(),
        "likes": post.likes,
        "rts": post.retweets,
        "platform": post.platform,
    }
    return _PROMPT_TEMPLATE.format(**ctx) if _PROMPT_TEMPLATE else _fallback_prompt(ctx)


def _call_claude(prompt: str) -> str:
    import time
    # Strip CLAUDECODE so we don't trip the nested-session safeguard when
    # the orchestrator is itself launched from within a Claude Code session.
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE", None)
    for attempt in range(3):
        if attempt:
            wait = 15 * attempt
            log.warning("claude cli retry %d/%d after %ds", attempt + 1, 3, wait)
            time.sleep(wait)
        try:
            proc = subprocess.run(
                [CLAUDE_CMD, "-p", prompt, "--output-format", "text", "--model", "claude-opus-4-7"],
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT_S,
                env=env,
            )
            if proc.returncode != 0:
                log.warning("claude cli nonzero exit %d: %s", proc.returncode, proc.stderr[:200])
            # Retry if transient error
            if any(e in proc.stdout for e in _TRANSIENT_ERRORS):
                continue
            return proc.stdout
        except subprocess.TimeoutExpired:
            log.error("claude cli timeout")
        except FileNotFoundError:
            log.error("claude CLI not found on PATH. Install Claude Code.")
            return ""
    return proc.stdout if 'proc' in dir() else ""


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse(raw: str, post: Post) -> Verdict:
    if not raw:
        return Verdict(False, 0, "pulse", [], "empty claude response")
    m = _JSON_RE.search(raw)
    if not m:
        reason = f"no json in response: {raw[:80]}"
        is_transient = any(e in raw for e in _TRANSIENT_ERRORS)
        return Verdict(False, 0, "pulse", [], reason, transient_fail=is_transient)
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return Verdict(False, 0, "pulse", [], f"json parse: {e}")

    topic = j.get("topic", "pulse")
    if topic not in {"pulse", "compression", "codebook", "frontier", "onchain"}:
        topic = "pulse"
    layers = j.get("layers", []) or []
    if not isinstance(layers, list):
        layers = []
    return Verdict(
        relevant=bool(j.get("relevant", False)),
        score=int(j.get("score", 0)),
        topic=topic,
        layers=[str(x) for x in layers],
        reason=str(j.get("reason", ""))[:300],
    )


def _fallback_prompt(ctx: dict) -> str:
    return f"""You evaluate tweets for CMPRSSN, a consultancy helping enterprises adapt to the agentic era.

Return only JSON: {{"relevant": bool, "score": 0-10, "topic": "pulse"|"compression"|"codebook"|"frontier"|"onchain", "layers": ["L3","L4",...], "reason": "one sentence"}}

Author: {ctx['author_name']} ({ctx['author_role']})
Context: {ctx['stack_tags']}
Tweet: {ctx['tweet_text']}
Engagement: {ctx['likes']} likes, {ctx['rts']} RTs
"""
