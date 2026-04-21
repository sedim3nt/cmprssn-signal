"""Interactive setup wizard for the CMPRSSN Signal Agent.

Walks a new operator through:
  1. Python venv + dependencies
  2. .env credential collection (Telegram, X, Bluesky)
  3. Runtime tunables (poll cadence, score threshold, per-run caps)
  4. Build handles.json from CSVs
  5. Optional dry-run smoke test
  6. Optional launchd install (macOS)

Idempotent — safe to re-run. Writes <repo_root>/.env, never overwrites a value
unless explicitly confirmed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
ENV_PATH = REPO_ROOT / ".env"
PLIST_SRC = AGENT_DIR / "deploy" / "com.cmprssn.signal.plist"
PLIST_DST = Path.home() / "Library" / "LaunchAgents" / "com.cmprssn.signal.plist"


# ---------- IO helpers ----------

def banner(s: str) -> None:
    bar = "═" * (len(s) + 2)
    print(f"\n╔{bar}╗\n║ {s} ║\n╚{bar}╝\n")


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        if secret:
            import getpass
            v = getpass.getpass(f"  {prompt}{suffix}: ").strip()
        else:
            v = input(f"  {prompt}{suffix}: ").strip()
    except EOFError:
        v = ""
    return v or default


def yesno(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    v = ask(f"{prompt} [{d}]").lower()
    if not v:
        return default
    return v.startswith("y")


# ---------- .env handling ----------

def load_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def write_env(env: dict[str, str]) -> None:
    """Write .env preserving comments + ordering when possible."""
    lines: list[str] = []
    seen: set[str] = set()

    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text().splitlines():
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in env:
                    lines.append(f"{k}={env[k]}")
                    seen.add(k)
                    continue
            lines.append(raw)

    for k, v in env.items():
        if k not in seen:
            lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(lines) + "\n")
    print(f"  ✓ wrote {ENV_PATH}")


# ---------- Steps ----------

def step_python() -> Path:
    banner("Step 1 / 6 — Python environment")
    if sys.version_info < (3, 11):
        print(f"  ✗ Python 3.11+ required (found {sys.version.split()[0]})")
        sys.exit(1)
    print(f"  ✓ Python {sys.version.split()[0]}")

    venv = AGENT_DIR / ".venv"
    if not venv.exists():
        if yesno("Create virtualenv at agent/.venv?"):
            subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
            print(f"  ✓ created {venv}")
    else:
        print(f"  ✓ venv exists at {venv}")

    pip = venv / "bin" / "pip"
    if pip.exists() and yesno("Install dependencies into venv?"):
        subprocess.check_call([str(pip), "install", "-q", "-e", str(AGENT_DIR)])
        print("  ✓ deps installed")
    return venv


def step_telegram(env: dict[str, str]) -> None:
    banner("Step 2 / 6 — Telegram credentials")
    print("  Need a bot token (from @BotFather), the chat ID of your group,")
    print("  and one topic/thread ID per channel.\n")
    env["TELEGRAM_CMPRSSN_BOT_TOKEN"] = ask("Bot token", env.get("TELEGRAM_CMPRSSN_BOT_TOKEN", ""), secret=True)
    env["TELEGRAM_CMPRSSN_CHAT_ID"] = ask("Chat ID (-100…)", env.get("TELEGRAM_CMPRSSN_CHAT_ID", ""))
    print("\n  Topic IDs — get from t.me/c/<chat>/<TOPIC>/<msg> URLs:")
    for topic in ("PULSE", "COMPRESSION", "CODEBOOK", "FRONTIER", "ONCHAIN"):
        key = f"TELEGRAM_CMPRSSN_TOPIC_{topic}"
        env[key] = ask(f"  {topic.lower()}", env.get(key, ""))
    env.setdefault("TELEGRAM_CMPRSSN_TOPIC_GENERAL", "0")


def step_apis(env: dict[str, str]) -> None:
    banner("Step 3 / 6 — X + Bluesky credentials")
    print("  X: bearer token from https://developer.x.com/ (credits-based PAYG).")
    env["TWITTER_BEARER_TOKEN"] = ask("X bearer token", env.get("TWITTER_BEARER_TOKEN", ""), secret=True)
    print("\n  Bluesky: account email + APP PASSWORD (not account password).")
    print("  Generate at https://bsky.app/settings/app-passwords")
    env["BLUESKY_EMAIL"] = ask("Bluesky email", env.get("BLUESKY_EMAIL", ""))
    env["BLUESKY_APP_PASSWORD"] = ask("Bluesky app password", env.get("BLUESKY_APP_PASSWORD", ""), secret=True)


def step_tunables(env: dict[str, str]) -> None:
    banner("Step 4 / 6 — Runtime tunables")
    print("  Defaults are sane; press Enter to accept.\n")

    print("  Qualitative score threshold (0–10).")
    print("    6 = balanced (default) · 7–8 = strict · 4–5 = more volume")
    env["MIN_QUAL_SCORE"] = ask("Min qualitative score", env.get("MIN_QUAL_SCORE", "6"))

    print("\n  Per-run publishing caps (prevents burst spam).")
    env["MAX_POSTS_PER_RUN"] = ask("Max posts per run", env.get("MAX_POSTS_PER_RUN", "15"))
    env["MAX_POSTS_PER_TOPIC_PER_RUN"] = ask("Max posts per topic per run", env.get("MAX_POSTS_PER_TOPIC_PER_RUN", "5"))

    print("\n  Per-handle fetch limits (per scheduled run).")
    env["TWEETS_PER_HANDLE"] = ask("Tweets per handle", env.get("TWEETS_PER_HANDLE", "10"))
    env["RSS_MAX_ENTRIES"] = ask("RSS entries per feed", env.get("RSS_MAX_ENTRIES", "5"))
    env["RSS_MAX_AGE_DAYS"] = ask("Ignore RSS items older than N days", env.get("RSS_MAX_AGE_DAYS", "3"))


def step_handles(venv: Path) -> None:
    banner("Step 5 / 6 — Build handles.json from CSVs")
    py = venv / "bin" / "python"
    script = AGENT_DIR / "scripts" / "build_handles.py"
    subprocess.check_call([str(py), str(script)])


def step_finalize(venv: Path, env: dict[str, str]) -> None:
    banner("Step 6 / 6 — Finalize")

    if yesno("Run a dry-run smoke test now? (fetches + scores, no Telegram writes)"):
        py = venv / "bin" / "python"
        subprocess.call([str(py), "-m", "src.orchestrator", "--dry-run"], cwd=str(AGENT_DIR))

    if sys.platform == "darwin" and PLIST_SRC.exists():
        if yesno("Install launchd schedule (4x/day on macOS)?"):
            shutil.copy(PLIST_SRC, PLIST_DST)
            subprocess.run(["launchctl", "unload", str(PLIST_DST)], stderr=subprocess.DEVNULL)
            subprocess.check_call(["launchctl", "load", str(PLIST_DST)])
            print(f"  ✓ launchd loaded → next runs at 6am, noon, 6pm, midnight")
            print(f"  uninstall:   launchctl unload {PLIST_DST}")
    elif sys.platform != "darwin":
        print("  ⓘ Non-macOS — set up cron / systemd to call:")
        py = venv / "bin" / "python"
        print(f"    cd {AGENT_DIR} && {py} -m src.orchestrator")


def main() -> None:
    banner("CMPRSSN Signal Agent — Setup Wizard")
    print("  This will walk you through a fresh install (~5 min).\n")
    print(f"  Repo root: {REPO_ROOT}")
    print(f"  .env path: {ENV_PATH}")

    env = load_env()
    if env:
        print(f"\n  Existing .env detected ({len(env)} keys). Values shown as defaults.")

    venv = step_python()
    step_telegram(env)
    step_apis(env)
    step_tunables(env)
    write_env(env)
    step_handles(venv)
    step_finalize(venv, env)

    banner("✓ Setup complete")
    print("  Manual run:    cd agent && .venv/bin/python -m src.orchestrator")
    print("  Dry-run:       cd agent && .venv/bin/python -m src.orchestrator --dry-run")
    print("  Push digest:   cd agent && .venv/bin/python scripts/push_digest_now.py")
    print()


if __name__ == "__main__":
    main()
