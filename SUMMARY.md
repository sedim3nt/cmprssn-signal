# CMPRSSN Signal Agent — Executive Summary

## What it is

A self-hosted Telegram bot that surfaces high-signal posts from ~100 agentic-era thought leaders and AI-native companies into a CMPRSSN practitioner community.

## What it does

Every 6 hours, the agent:

1. **Pulls** new posts from X (Twitter), Bluesky, and 47 RSS feeds (Substack, YouTube, blogs) for ~100 curated handles.
2. **Filters** for engagement signal — likes-per-follower ratio with tier-aware floors.
3. **Scores** each survivor with the local `claude` CLI against the CMPRSSN thesis ("AI is only as capable as the organization around it") and the Agentic Stack framework (L0–L8). Returns a 0–10 relevance score, a routing topic, and L-layer tags.
4. **Routes** the top 15 (capped at 5/topic) into 5 themed Telegram channels: `pulse`, `compression`, `codebook`, `frontier`, `onchain`.
5. **Reports** to a 6th admin channel (`General`) with a stats digest + the top 3 signals from that run.

## Why it matters for CMPRSSN

- **Fills the practitioner channel with thesis-aligned signal**, not Twitter noise. Each post arrives pre-tagged with the Agentic Stack layer it touches.
- **Operationalizes the framework**. The bot proves the L0–L8 model is concrete enough to sort posts in real time, not just present in slides.
- **Demo of agent capabilities** for prospective clients: an LLM-in-the-loop pipeline with deterministic gates, observable state, and zero ongoing inference cost.

## Why it costs $0/mo

| Layer | Choice | Why free |
|---|---|---|
| Inference | Local `claude` CLI subprocess | Covered by an existing Claude subscription |
| X ingest | Official API v2 with bearer token | Pay-as-you-go credits (~$10 lasts months at 4 polls/day) |
| Bluesky | AT Protocol via app password | Free |
| RSS / YouTube / Substack | `feedparser` over HTTP | Free, public feeds |
| Telegram | Bot API | Free |
| Storage | SQLite (single file) | Free |
| Hosting | Mac mini + macOS `launchd` | Free (existing hardware) |

The only ongoing variable cost is X API credits, which scale with poll frequency — currently 4x/day across 100 handles.

## What's in the box

- ~1500 lines of Python (typed, modular, no test gaps in the critical path)
- An interactive setup wizard that walks a new operator from `git clone` to scheduled deploy in ~5 minutes
- Two CSVs (`individuals.csv`, `companies.csv`) defining who's monitored — fully editable
- A `launchd` plist for macOS auto-scheduling
- Full operator documentation (`README.md`) and machine-readable deploy spec (`AGENT.md`)

## Operating envelope

- ~50–60 posts/day published across 5 channels (with caps active)
- One digest/run posted to General (4/day)
- ~95% pipeline success rate per handle (degrades gracefully on individual failures)
- Database is a single SQLite file; backup = `cp agent/data/agent.db /backup/`
- Schedule lives in one launchd plist; trivial to change cadence

## What it is not

- Not a real-time bot. 6-hour cadence by design.
- Not multi-tenant. One install = one Telegram group.
- Not interactive (yet). The bot writes; it does not yet listen for `@mentions` or commands. That's a Phase-2 add-on.
- Not LinkedIn-aware. LinkedIn requires Proxycurl ($) and is stubbed off.

## Time-to-deploy for a new operator

| Phase | Time |
|---|---|
| Get Telegram bot + group + topic IDs | 10 min |
| Get X bearer token + add credits | 10 min |
| Create Bluesky app password | 2 min |
| Run `setup_wizard.py` (it does the rest) | 5 min |
| **Total** | **~30 min** |

## Maintenance

- Top up X credits when notified (every few months)
- Edit CSVs to add/remove handles → re-run `build_handles.py`
- Tune the qualitative score threshold in `.env` if signal volume drifts
- That's it. No daily ops.
