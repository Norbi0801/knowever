# knowever

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements)
[![uv managed](https://img.shields.io/badge/Deps-uv%20sync-3f6ad8.svg)](#installation)
[![Status](https://img.shields.io/badge/Status-Experimental-orange.svg)](#overview)
[![Platform](https://img.shields.io/badge/Platform-linux%20%7C%20macOS%20%7C%20WSL-0f172a.svg)](#requirements)

> RSS -> AI -> email digest pipeline as a tiny CLI.

## Contents
- Overview
- Features
- Requirements
- Installation
- Configuration
- RSS sources
- Profiles
- Usage
- Data locations
- Development
- Troubleshooting

## Overview
knowever pulls RSS feeds, filters and scores entries, optionally enriches them with Codex/OpenAI, then ships a daily digest (or individual emails) via SMTP. It is designed to be crontab/systemd friendly and to keep all state inside the repo directory.

## Features
- Parallel feed download with de-duplication and similarity filtering.
- Scoring based on recency, engagement signals, and keyword hints from profiles.
- Optional AI enrichment (Codex/OpenAI) with a safe HTML email template.
- Digest or per-entry sending modes with configurable worker counts.
- Cache for failing domains to avoid hammering broken sources.

## Requirements
- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) installed

Install `uv` (Linux/macOS example):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
On Windows/WSL follow the instructions in the `uv` repository.

## Installation
From the project root:
```bash
uv sync
```

## Configuration
Create `.env` (or copy `.env.example`) and set SMTP and pipeline knobs. Key variables:
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_smtp_login
SMTP_PASS=your_smtp_password_or_app_password
SMTP_FROM="Your Name <you@example.com>"
SMTP_TO=recipient@example.com

MAX_POSTS_PER_DAY=10
SEND_MODE=digest          # or individual
INCLUDE_AI_CONTENT=true   # false -> summary/link without AI content
CLEAR_BUFFER_AFTER_SEND=true
AUTO_SEND_DIGEST=false
FEED_DOWNLOAD_WORKERS=4
PROCESS_WORKERS=2
SEND_WORKERS=3
FAIL_TTL_SECONDS=86400    # seconds; TTL for domain error cache
PROFILE_NAME=default
ENTRY_SCORE=0.0
LOG_LEVEL=INFO
```

## RSS sources
List your feeds in `sources.yaml`:
```yaml
- name: Hacker News Frontpage
  url: https://hnrss.org/frontpage
- name: Dev.to Top
  url: https://dev.to/feed
```

## Profiles
Copy `profile.example.yaml` to `profile.yaml` and adjust:
- `min_score`: threshold to keep an entry
- `max_per_source`: per-source daily cap
- `keywords_positive` / `keywords_negative`: scoring hints
- `send_time`: used in digest metadata

## Usage
After `uv sync`, commands are available via `uv run -m knowever.cli ...` (or `./run.sh` for the full pipeline).

Common commands:
```bash
# Full pipeline with day.lock guard (once per day)
PYTHONPATH=src uv run -m knowever.cli run

# Download feeds only
PYTHONPATH=src uv run -m knowever.cli download

# Select + AI -> daily_buffer.jsonl
PYTHONPATH=src uv run -m knowever.cli process

# Send digest or individual emails
PYTHONPATH=src uv run -m knowever.cli send

# Clear domain error cache
PYTHONPATH=src uv run -m knowever.cli purge-cache

# Mark all entries in feeds/ as processed
PYTHONPATH=src uv run -m knowever.cli mark-all

# Inspect today's buffer (default limit 5)
PYTHONPATH=src uv run -m knowever.cli show-buffer --limit 5
```
If you prefer editable install: `uv pip install -e .` then call `knowever ...` directly.

## Data locations
- Feeds: `feeds/*.jsonl`
- Digest buffer: `daily_buffer.jsonl`
- Processing history: `feeds_process_history.jsonl`
- Domain error cache: `tmp/fetch_failures.json`
- AI prompt: `prompt.md`
- Logs: `logs/`

## Development
- Source lives in `src/knowever/`.
- Keep `PYTHONPATH=src` when running commands locally.
- Logging level can be tuned via `LOG_LEVEL` in `.env`.

## Troubleshooting
- Nothing sent today? Check `daily_buffer.jsonl` and `logs/knowever.log`.
- Hitting the daily cap: raise `MAX_POSTS_PER_DAY` or lower `min_score` in `profile.yaml`.
- Repeated domain failures: delete `tmp/fetch_failures.json` or run `purge-cache`.
