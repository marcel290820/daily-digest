# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Two Telegram digests sent every morning (Europe/Berlin): Tech & ML at 08:00, World News at 08:10. Delivered to a single Telegram bot/chat. No LLM, no ranking — native source order only. A third command, `feargreed`, runs hourly and alerts when the CNN (stocks) or alternative.me (crypto) Fear & Greed index enters an extreme zone.

## Stack

- **Python 3.11+** package, `src/` layout, `hatchling` build backend (`pyproject.toml`).
- **Dependencies:** `httpx` (async HTTP for HN + Telegram + RSS + Fear & Greed), `feedparser` (RSS parsing). Nothing else. SQLite is stdlib `sqlite3`.
- **Delivery:** Telegram Bot API `sendMessage` with `parse_mode=MarkdownV2`. 4096-char chunking in `telegram.py`.
- **Scheduling:** systemd `.timer` units with `OnCalendar=... Europe/Berlin` (DST-safe). One templated `daily-digest@.service` oneshot that takes the command name as `%i`.
- **State:** one SQLite file of Fear & Greed readings at `DIGEST_DB_PATH` (`/var/lib/daily-digest/feargreed.db` on the VM, via `StateDirectory=`). Nothing else is persisted.
- **Secrets:** `/etc/daily-digest/env` on the VM (mode 0600), loaded via `EnvironmentFile=`. Never committed. `.env.example` documents the shape.
- **Tests:** stdlib `unittest`, `python -m unittest discover`. Source parsers are tested against saved API payloads in `tests/fixtures/`; no test touches the network.
- **No Docker, no CI/CD, no OAuth, no paid APIs.**

## Layout

```
src/daily_digest/
├── __main__.py         # CLI: python -m daily_digest {tech,news,feargreed} [--dry-run] [--backfill]
├── __init__.py         # Item dataclass (title, url, source, score)
├── config.py           # env vars + RSS list + per-source limits + F&G thresholds
├── feargreed.py        # Reading dataclass, zone(), alert_needed() — pure, no I/O
├── format.py           # MarkdownV2 render
├── store.py            # sqlite3 reading history, idempotent writes
├── telegram.py         # Bot API sender (4096-char chunking)
└── sources/
    ├── feargreed.py    # CNN graphdata + alternative.me /fng/, unauth; parse split from fetch
    ├── hackernews.py   # Firebase REST (/v0/topstories.json + /v0/item/{id}.json), unauth
    └── rss.py          # httpx fetch + asyncio.to_thread(feedparser.parse, ...)
tests/
├── fixtures/           # real API payloads, captured once
└── test_feargreed_*.py
deploy/
├── daily-digest@.service
├── daily-digest-{tech,news}.timer
├── daily-digest-feargreed.timer
└── install.sh
```

Every item source returns `list[Item]`; the Fear & Greed sources return `Reading`. `__main__.py:_gather_*` uses `asyncio.gather(..., return_exceptions=True)` so one failing source does not block the others.

## Fear & Greed rules

- **The checker is the only writer.** The news digest renders a section from the live API responses and never touches the database. If it wrote readings, the hourly checker would compare against its own row and miss the crossing.
- **Read the previous reading before recording the new one.** That ordering is what makes an alert fire once per crossing instead of never.
- **Values are rounded to `int` at the source boundary**, so the number displayed, stored and compared to a threshold is always the same one.
- **Timestamps are UTC epoch seconds** in SQLite, `(idx, ts)` primary key, upsert that only writes when the value actually differs. Backfill and re-runs are therefore idempotent, and a source revising a published value overwrites the stored one instead of leaving the checker comparing against a zone the index has already left.
- **The CNN endpoint is unofficial** and needs a browser `User-Agent` plus a `cnn.com` `Referer` or it returns 418.

## Running

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m daily_digest tech      --dry-run    # stdout, no Telegram
.venv/bin/python -m daily_digest news      --dry-run
.venv/bin/python -m daily_digest feargreed --dry-run    # also skips the DB write
.venv/bin/python -m unittest discover
```

Real send: set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, drop `--dry-run`. See `README.md` for Hetzner deploy.

## Conventions

- **Keep dependencies minimal.** Two third-party packages is the current ceiling. Prefer stdlib (`asyncio`, `argparse`, `datetime`, `logging`, `json`) before adding anything.
- **Source adapters are dumb.** Fetch → map to `Item` → return. No ranking, no dedupe, no LLM. Limits live in `config.py`, not in the adapter.
- **Failures are logged and skipped**, not raised. The digest still sends whatever other sources returned.
- **Secrets live only in `/etc/daily-digest/env` on the VM.** Do not inline tokens into code, tests, or commit messages.
- **Never hardcode UTC offsets** for scheduling; `OnCalendar=... Europe/Berlin` handles DST.

## Entire Harness Integration

The only pre-wired system is the [Entire](https://entire.dev) CLI, which tracks checkpoints and transcripts across Claude Code and OpenCode sessions. Relevant pieces:

- `.claude/settings.json` — wires `entire hooks claude-code ...` into `SessionStart`, `SessionEnd`, `Stop`, `UserPromptSubmit`, `PreToolUse`/`PostToolUse` (Task), `PostToolUse` (TodoWrite). Do not remove these hooks without explicit user approval; they are how Entire records this session.
- `.claude/agents/entire-search.md` — `entire-search` subagent. Use it (or call `entire search --json` directly) for any historical question about prior sessions, prompts, commits, or checkpoints. Never invoke `entire search` without `--json`; the plain form opens an interactive TUI and will hang.
- `.opencode/plugins/entire.ts` — same hook surface for OpenCode. Header says "Auto-generated by `entire enable --agent opencode` — Do not edit manually".
- `.entire/` — local Entire state. `metadata/`, `logs/`, `tmp/`, and `settings.local.json` are gitignored. `.claude/settings.json` also denies Read on `./.entire/metadata/**`; respect that rather than working around it.

## Historical Context

For "what did we do before / last session / recent commits in a related project", prefer the `entire-search` subagent over `git log` or ad hoc grep — the Entire index covers checkpoints and transcripts that git does not. Git history is currently one commit (`init`), so git-based history is not yet useful here.
