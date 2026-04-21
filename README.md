# CMPRSSN Signal Agent — Operator Guide

A zero-cost Telegram signal bot. Polls ~100 agentic-era thought leaders and AI-native companies across X, Bluesky, and RSS (Substack / YouTube / blogs); scores each post through a two-stage gate (engagement + Claude qualitative); routes the survivors into 5 Telegram topic channels; and posts a stats digest to a 6th admin channel after every run.

> **1-page summary**: `SUMMARY.md`
> **For an AI agent deploying this**: `AGENT.md`
> **Env template**: `.env.example` (copy to `.env`)

---

## What it does, end-to-end

```
       ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
       │ ingest/x.py    │    │ ingest/        │    │ ingest/rss.py  │
       │ (X API v2)     │    │ bluesky.py     │    │ (Substack /    │
       │                │    │ (atproto)      │    │  YouTube /     │
       │                │    │                │    │  blogs)        │
       └────────┬───────┘    └────────┬───────┘    └────────┬───────┘
                └─────────────┬───────┴─────────────────────┘
                              ▼
                    ┌──────────────────┐
                    │ store.py         │
                    │ SQLite dedup by  │
                    │ (platform, id)   │
                    └────────┬─────────┘
                             ▼
              ┌───────────────────────────┐
              │ score/quant.py            │
              │ likes/follower ratio      │
              │ + tier-aware floor        │
              │ (RSS auto-passes)         │
              └────────┬──────────────────┘
                       ▼
              ┌───────────────────────────┐
              │ score/qualitative.py      │
              │ Claude CLI subprocess     │
              │ scores 0–10, picks topic, │
              │ tags L0–L8 layers         │
              └────────┬──────────────────┘
                       ▼
              ┌───────────────────────────┐
              │ orchestrator.py           │
              │ rank by score, apply      │
              │ per-run + per-topic caps  │
              └────────┬──────────────────┘
                       ▼
              ┌───────────────────────────┐
              │ publish/telegram.py       │
              │ → 5 topic channels        │
              │ + digest → General        │
              └───────────────────────────┘
```

**Cost:** $0/mo for inference (Claude CLI uses your existing Claude subscription) + a few cents/day for X API credits + free for Bluesky/Telegram/RSS.

---

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| **macOS or Linux** | The wizard auto-installs launchd on macOS. On Linux, set up cron/systemd manually. | — |
| **Python 3.11+** | Modern type hints | `brew install python@3.11` |
| **`claude` CLI** | Free inference via your Claude.ai subscription | https://docs.claude.com/en/docs/claude-code |
| **A Telegram bot** | Publish channel | https://t.me/BotFather → `/newbot` |
| **A Telegram supergroup with topics enabled** | 5 routing channels + 1 admin (General) | Settings → Manage Group → Topics → ON |
| **An X developer account** | Bearer token for X API v2 (PAYG, ~$10 lasts months at 4 polls/day) | https://developer.x.com/ |
| **A Bluesky account** | App password for AT Protocol | https://bsky.app/settings/app-passwords |

---

## Quick start (the easy path)

```bash
git clone <this-repo>
cd csv

# Run the interactive wizard. It walks you through everything below.
python3 agent/scripts/setup_wizard.py
```

The wizard:
1. Verifies Python 3.11+
2. Creates `agent/.venv` and installs deps
3. Prompts for Telegram / X / Bluesky credentials
4. Asks about runtime tunables (score threshold, post caps, fetch limits)
5. Builds `agent/data/handles.json` from `individuals.csv` + `companies.csv`
6. Runs an optional dry-run smoke test (no Telegram writes)
7. Optionally installs the launchd schedule (macOS)

Time: ~5 minutes if you have all your tokens ready.

---

## Manual setup (the verbose path)

If you want to know exactly what's happening, do it by hand.

### 1. Python environment

```bash
cd agent
python3 -m venv .venv
.venv/bin/pip install -e .
```

### 2. Configure `.env`

```bash
cp .env.example .env
# Edit .env and fill in every REQUIRED value.
```

The agent loads `.env` from the repo root.

**Required:**
- Telegram: bot token, chat ID, 5 topic IDs
- X: bearer token
- Bluesky: email + app password

**Optional (have sensible defaults):**
- `MIN_QUAL_SCORE` — qualitative score threshold (0–10, default 6)
- `MAX_POSTS_PER_RUN` — total per-run cap (default 15)
- `MAX_POSTS_PER_TOPIC_PER_RUN` — per-topic cap (default 5)
- `MIN_LIKES_FLOOR` / `MIN_LIKES_FLOOR_TIER3` / `ENGAGEMENT_RATIO_MIN` — quant gate
- `TWEETS_PER_HANDLE` / `RSS_MAX_ENTRIES` / `RSS_MAX_AGE_DAYS` — fetch limits

### 3. Build the handle database

```bash
python agent/scripts/build_handles.py
```

Reads `individuals.csv` + `companies.csv`, emits `agent/data/handles.json`. Re-run after editing the CSVs.

### 4. Smoke test

```bash
cd agent
.venv/bin/python -m src.orchestrator --dry-run
```

Fetches everything, scores everything, logs what *would* be posted. **No Telegram writes.** Confirms credentials are valid and the pipeline runs end-to-end.

### 5. First wet run

```bash
cd agent
.venv/bin/python -m src.orchestrator
```

Posts up to 15 messages (5 per topic) and a digest to General.

### 6. Schedule it

**macOS (launchd):**

```bash
cp agent/deploy/com.cmprssn.signal.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cmprssn.signal.plist
```

The provided plist runs at 6am, noon, 6pm, midnight. Edit `StartCalendarInterval` to change.

**Linux (cron):**

```bash
crontab -e
# Add:
0 6,12,18,0 * * * cd /path/to/csv/agent && .venv/bin/python -m src.orchestrator
```

---

## How posts are scored

### Stage 1 — Quantitative (engagement gate)

```
likes_per_follower = post.likes / handle.followers
pass = (likes >= floor) AND (likes_per_follower >= ratio_min)

floor = 25 by default (10 for Tier-3 handles)
ratio_min = 0.001 (1 like per 1,000 followers)
```

RSS posts skip this entirely (no engagement metrics) and go straight to Stage 2.

### Stage 2 — Qualitative (Claude CLI)

Each surviving post is sent to the local `claude` CLI with a CMPRSSN-thesis-aware prompt (`agent/src/prompts/signal_score.md`). Claude returns:

```json
{
  "relevant": true,
  "score": 0-10,
  "topic": "pulse|compression|codebook|frontier|onchain",
  "layers": ["L4", "L7"],
  "reason": "brief justification"
}
```

A post is published if `relevant=true` AND `score >= MIN_QUAL_SCORE` (default 6).

### Stage 3 — Ranking + caps

Surviving posts are sorted by score (desc, ties broken by likes), then capped:
- ≤ `MAX_POSTS_PER_RUN` total (default 15)
- ≤ `MAX_POSTS_PER_TOPIC_PER_RUN` per topic (default 5)

The bottom of the queue is dropped. This prevents one viral storm from flooding the channel.

---

## The 5 topic channels (Agentic Stack-aware)

| Emoji | Topic | What lands here |
|---|---|---|
| 📡 | `pulse` | General catch-all — agentic-era news that doesn't fit elsewhere |
| ⚡ | `compression` | Born Agentic / high-RPE stories, solo operators, $1M/employee proofs |
| 📘 | `codebook` | Org redesign, AI-first mandates, codebook revision case studies |
| 🔭 | `frontier` | L3 Cortex (memory, identity), L6 Shield (governance), L7 Interface primitives |
| ⛓ | `onchain` | DAO governance, autonomous trading, crypto-native AI |

Each post header includes the L-layer tags Claude assigned (e.g., `L: L4 · L7`).

---

## The General channel (admin / digest)

After every scheduled run the bot posts a digest:

```
🤖 Run complete · 2026-04-21 12:00 UTC

Fetched: x=45 · bsky=2 · rss=8 (total 55)
New (post-dedup): 12
Quant gate passed: 8
Qualitative gate passed: 5
Posted: 5 · capped: 0 · errors: 0

🏆 Top signals this run:
  📘 9/10 · @lennysan
     How Intercom 2x'd engineering velocity with Claude Code
     https://x.com/lennysan/status/...
  ...
```

Use this channel to:
- Confirm the bot is healthy after each run
- See top signals at a glance without scrolling 5 channels
- Spot when `posted_err > 0` and dig into logs

---

## File layout

```
<repo>/
├── README.md                  # this file
├── SUMMARY.md                 # 1-page exec overview
├── AGENT.md                   # machine-readable deploy spec
├── .env.example               # template — copy to .env
├── .env                       # ← you create (NEVER commit; .gitignore excludes it)
├── individuals.csv            # 80 thought leaders (edit to change who's monitored)
├── companies.csv              # 20 AI-native companies
├── individuals.md             # human mirror of individuals.csv
├── companies.md               # human mirror of companies.csv
└── agent/
    ├── pyproject.toml
    ├── src/
    │   ├── config.py          # loads .env, exposes runtime constants
    │   ├── handles.py         # Handle dataclass + filters
    │   ├── store.py           # SQLite schema + upsert/dedup
    │   ├── orchestrator.py    # main pipeline
    │   ├── ingest/{x,bluesky,rss,linkedin}.py
    │   ├── score/{quant,qualitative}.py
    │   ├── publish/{telegram,format,digest}.py
    │   └── prompts/signal_score.md
    ├── scripts/
    │   ├── setup_wizard.py    # interactive installer
    │   ├── build_handles.py   # CSV → handles.json
    │   ├── publish_pending.py # post anything stuck in DB queue
    │   └── push_digest_now.py # one-shot digest backfill
    ├── data/                  # GENERATED — gitignored
    │   ├── handles.json       # built from CSVs
    │   ├── agent.db           # SQLite — what was posted
    │   └── x_user_cache.json
    ├── logs/                  # GENERATED — gitignored
    └── deploy/
        └── com.cmprssn.signal.plist   # launchd 4x/day
```

---

## Editing the monitored list

The CSVs are the source of truth. After any edit:

```bash
python agent/scripts/build_handles.py
```

The next scheduled run picks up the new `handles.json` automatically.

**To add someone:**
1. Append a row to `individuals.csv` (or `companies.csv`)
2. Fill in: `Name`, `X Handle` (with `@`), optional `RSS Feed`
3. Add a Bluesky handle in `BSKY_MAP` inside `agent/scripts/build_handles.py` if applicable
4. Rebuild

**To temporarily disable someone** (e.g., spammy account, broken handle):

Add their slug to `DISABLED_SLUGS` in `agent/scripts/build_handles.py`, then rebuild.

---

## Operations

### Manual run

```bash
cd agent && .venv/bin/python -m src.orchestrator
```

### Force-publish backlog

If posts are stuck in the DB queue (passed gates but not sent — e.g., from a dry-run or rate limit):

```bash
cd agent && .venv/bin/python scripts/publish_pending.py
# Apply the same per-run caps; re-run to drain in batches.
```

### Push a digest right now

```bash
cd agent && .venv/bin/python scripts/push_digest_now.py
```

### Inspect the database

```bash
sqlite3 agent/data/agent.db
> SELECT COUNT(*) FROM posts WHERE posted_to_tg=1;
> SELECT author_handle, qualitative_score, qualitative_topic
  FROM posts WHERE posted_to_tg=1
  ORDER BY posted_at DESC LIMIT 20;
```

### View logs

```bash
tail -f agent/logs/run-$(date +%Y-%m-%d).log
tail -f agent/logs/launchd.err.log
```

### Stop the schedule

```bash
launchctl unload ~/Library/LaunchAgents/com.cmprssn.signal.plist
```

### Tune signal volume

Edit `.env`:
- Too few posts? Lower `MIN_QUAL_SCORE` to 5 or 4.
- Too many posts? Raise to 7 or 8, or drop `MAX_POSTS_PER_RUN` to 10.

No restart needed — env is read at the start of each scheduled run.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `402 CreditsDepleted` | X API credits ran out | Top up at https://console.x.com/ — $10 lasts a long time |
| `429 Too Many Requests` (Telegram) | Sending too fast | Pipeline already sleeps 1s between sends; if it persists, the digest's per-topic cap is too high |
| `Claude CLI refused to run` | Running inside a Claude Code session | The wrapper strips `CLAUDECODE`/`CLAUDE_CODE` env vars — but if you forced a custom env, restore those |
| `bsky login failed` | Used account password instead of app password | Generate an app password at https://bsky.app/settings/app-passwords |
| `rss: malformed feed` | Site serves non-standard XML (Beehiiv is a common offender) | Logged as warning; that feed is skipped, others continue |
| Digest not appearing in General | Wrong topic ID | `TELEGRAM_CMPRSSN_TOPIC_GENERAL=0` routes to the default General topic — only set non-zero if you created a custom thread |
| `handles.json missing` | Forgot to build | `python agent/scripts/build_handles.py` |

---

## Security notes

- `.env` lives in repo root and contains every API key. **Never commit it.** A `.gitignore` rule should already exclude it.
- The agent only opens outbound connections to: `api.twitter.com`, `bsky.social`, `api.telegram.org`, RSS feed hosts, and the local `claude` CLI process.
- No inbound listener — the bot is push-only. There's no attack surface from the network.
- Telegram bot token grants full posting rights to your group. Treat it like any other secret.

---

## Architectural decisions

- **Why Claude CLI not the API?** $0 inference. The user's existing Claude subscription covers it. Subprocess overhead is ~1s per post; we score ~50 posts per run, so ~50s of CPU per scheduled run.
- **Why SQLite not Postgres?** Single Mac mini deploy. Zero ops. Backup = copy a file.
- **Why per-run caps?** Without them, a viral storm (e.g., a major model release) would dump 200+ posts into one channel in 60 seconds.
- **Why 4x/day not every 10min?** Conserves X API credits; thought leaders don't post that often; the digest aggregates well at 6h granularity.
- **Why YouTube via RSS?** No API key needed. Channel feeds at `youtube.com/feeds/videos.xml?channel_id=…` are public and free.
- **Why bypass quant gate for RSS?** Substack/YouTube/blog feeds have no engagement metrics. The Claude qualitative gate alone is sufficient signal.

---

## License

Internal CMPRSSN tooling. Not for redistribution.
