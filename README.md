# Sassi Downloader

A production-grade download manager with adaptive concurrency, intelligent retry logic, and a clean dark UI.

Supports any video URL via yt-dlp — TikTok, YouTube, Instagram, Twitter, Facebook, Twitch, and 1000+ other sites.

## Quick Start

**Windows (no install needed):**

1. Download the `Sassi Downloader/` folder
2. Open it
3. Double-click `Sassi Downloader.exe`

That's it. No Python, no dependencies, no installation.

## Features

- **Adaptive Concurrency** — Adjusts 1–8 streams per host based on server speed
- **Intelligent Retries** — Exponential backoff with error classification
- **Priority Queue** — HIGH / NORMAL / LOW with bandwidth fairness
- **Integrity Validation** — File size + MD5 checksum on completion
- **Server Cache** — Remembers per-host performance across sessions
- **Pause / Resume / Cancel** — Thread-safe state machine
- **Download History** — Atomic writes, persists across sessions
- **Quality Selection** — Fetches available formats, lets you choose

## Architecture

```
core/
├── enums.py        # State machine, error classification
├── cache.py        # Server cache + error chain tracking
├── verifier.py     # Chunk verification + integrity
├── scheduler.py    # Adaptive concurrency + bandwidth fairness
├── task.py         # Download task with state machine
└── engine.py       # Download engine orchestration

ui/
└── main_window.py  # Glass UI with state color coding

main.py             # Entry point
```

## Build from Source

```bash
pip install yt-dlp pyinstaller
pyinstaller --onedir --noconsole --name "Sassi Downloader" --icon=icon.ico main.py
```

## License

MIT
