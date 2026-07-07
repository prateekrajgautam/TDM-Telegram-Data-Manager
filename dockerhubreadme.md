# Telegram Data Manager

A self-hosted, web-based tool for backing up, browsing, and exporting your Telegram data — chats, media, and message metadata — with a FastAPI-powered UI. Built on Telethon's MTProto client, it can save downloads directly to a local (or network-mounted) directory, or stream them straight to a remote server over SFTP.

**Image:** `prateekrajgautam/telegram-data-manager`

---

## Features

- 🔐 Web login flow (phone number → code → optional 2FA password), session persisted across restarts
- 💬 Browse all your chats, groups, and channels from the dashboard
- 📥 Download media (photos, videos, documents, audio, voice notes) with per-job progress tracking
- 📄 Export message metadata to JSON, CSV, or a browsable HTML file
- 💾 Pluggable storage targets — write directly to a local/mounted directory **or** a remote server over SFTP, no intermediate copy
- ✅ SHA-256 checksums recorded per file for integrity verification
- ⚙️ Single-worker job engine by default, configurable concurrency

---

## Quick start

### 1. Get Telegram API credentials

Visit [my.telegram.org](https://my.telegram.org) → API Development Tools, and create an app to get your `api_id` and `api_hash`.

### 2. Run with Docker

```bash
docker run -d \
  --name telegram-data-manager \
  -p 8000:8000 \
  -e TELEGRAM_API_ID=123456 \
  -e TELEGRAM_API_HASH=your_api_hash \
  -e SECRET_KEY=some-random-string \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/downloads:/app/downloads \
  --restart unless-stopped \
  prateekrajgautam/telegram-data-manager:latest
```

Then open **http://localhost:8000** and sign in with your phone number.

### 3. Or run with Docker Compose

`docker-compose.yml`:

```yaml
services:
  telegram-data-manager:
    image: prateekrajgautam/telegram-data-manager:latest
    container_name: telegram-data-manager
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      TELEGRAM_API_ID: "123456"
      TELEGRAM_API_HASH: "your_api_hash"
      SECRET_KEY: "some-random-string"
    volumes:
      - ./data:/app/data
      - ./downloads:/app/downloads
```

```bash
docker compose up -d
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_API_ID` | *(required)* | From my.telegram.org |
| `TELEGRAM_API_HASH` | *(required)* | From my.telegram.org |
| `SECRET_KEY` | `change-me-in-production` | Set to a random string |
| `DATA_DIR` | `/app/data` | Session files + SQLite database |
| `DEFAULT_DOWNLOAD_DIR` | `/app/downloads` | Default local storage target |
| `MAX_CONCURRENT_DOWNLOADS` | `1` | Number of parallel download jobs |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address inside the container |

---

## Volumes

| Container path | Purpose |
|---|---|
| `/app/data` | SQLite database and Telegram session files — **keep this private**, mount to a persistent local volume |
| `/app/downloads` | Default download destination. Point it at any local directory or an already-mounted network share (NFS/SMB/etc.) to save directly there |

---

## Local and remote storage

By default, downloads and exports go to `/app/downloads` (map this to whatever local or network-mounted directory you like). You can also add **remote SFTP storage targets** from the Settings page in the web UI — files stream directly to the remote host, with no local intermediate copy.

---

## Security notes

- Session files under `/app/data` grant full access to the linked Telegram account — treat that volume like a secret and back it up carefully.
- Run behind a reverse proxy with TLS and authentication if exposing this outside your local network; the app itself does not add a login wall in front of the web UI besides the Telegram sign-in.
- Respect [Telegram's Terms of Service](https://telegram.org/tos) — this tool is for personal backups of data you already have access to.

---

## Tags

- `latest` — latest stable build
- `x.y.z` — pinned version releases

## Source

Source and issue tracker: see the project repository (not bundled in this image). This image is built from the included `Dockerfile` in the project source.
