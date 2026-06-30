# TDM — Telegram Data Manager

A `yt-dlp`/`rclone`-style command-line tool for downloading, indexing, and
managing your own Telegram data via the official MTProto API (through
[Telethon](https://docs.telethon.dev/)).

> TDM only uses official Telegram APIs. It does not crack security, bypass
> rate limits, automate spam, or circumvent account restrictions.

## Status

Phase 1 + early Phase 2 from the roadmap: CLI, config, auth, database,
logging, chat listing, and a working (single-worker) download engine with
resume support are implemented. Forward engine, filters CLI wiring, and
the Rich live dashboard are scaffolded but not fully built — see the
"Roadmap" section below.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

### Get API credentials

1. Go to <https://my.telegram.org>, log in, open "API development tools".
2. Create an app and note your **API ID** and **API Hash**.
3. Configure TDM:

```bash
tdm config --api-id 123456 --api-hash your_api_hash_here
```

This writes `config.json` in the current directory. **Never commit this
file** if it contains real credentials — it's already in `.gitignore`.

### Log in

```bash
tdm login
```

First run will ask for your phone number, the OTP sent to Telegram, and
your 2FA password if you have one set. This creates `telegram.session` —
treat it like a password (it's chmod'd 600 automatically on Linux/macOS).

## Usage

```bash
tdm chats                      # list your chats with IDs
tdm chats --search "family"    # filter by name

tdm backup <chat_id>           # index + download all media (resumable)
tdm backup <chat_id> --limit 500

tdm retry                      # retry all failed items, any chat

tdm verify                     # check downloaded files for missing/corrupt

tdm export csv --out media.csv
tdm export json --out media.json

tdm logout                     # revoke session and remove session file
```

Interrupt a backup with Ctrl+C any time — state lives in `tdm.db` (SQLite),
so re-running `tdm backup <chat_id>` picks up where it left off and skips
anything already downloaded.

## Project layout

```
tdm/
  cli.py        Typer command definitions (entry point)
  auth.py       Telethon login/logout, session handling
  config.py     pydantic-validated config.json loader
  database.py   SQLite schema + resume engine + dedup
  download.py   Download engine: indexing, retry/backoff, FloodWait
  forward.py    Forward engine (Phase 3 — not yet implemented)
  filters.py    Date/media/size filter predicates (Phase 3)
  verify.py     File integrity verification
  exporter.py   CSV/JSON metadata export
  logger.py     backup.log / error.log / summary.log setup
  ui.py         Rich progress dashboard
  utils.py      Shared helpers
tests/
  test_database.py
```

## Roadmap

See the original planning doc for the full feature list (sections 1–28).
Suggested build order from here:

1. Concurrency: turn `download_pending` into a worker pool (respecting
   `config.workers`), keeping one queue per chat to avoid triggering
   throttling from parallel requests against the same peer.
2. Wire `filters.py` predicates into the `backup` CLI command
   (`--from`, `--to`, `--media-type`, `--min-size`, etc).
3. Expand `ui.py` into a live `Rich.Live` dashboard (current file,
   speed, ETA) once the worker pool reports richer progress events.
4. Implement `forward.py` with explicit per-run confirmation and
   conservative default pacing (`forward_delay_seconds` in config).
5. HTML report export, `tdm stats`, `tdm doctor` diagnostics command.
6. Phase 5 items: filesystem mounting, sync, plugin support, REST API,
   Docker image, optional GUI.

## Security notes

- `telegram.session` and `config.json` (if it holds real credentials)
  are gitignored by default — keep it that way.
- Forwarding messages in bulk is the feature most likely to brush up
  against Telegram's terms of service even though it's done through
  official APIs; it remains unimplemented here pending the guardrails
  described in `forward.py`.
# TDM-Telegram-Data-Manager
