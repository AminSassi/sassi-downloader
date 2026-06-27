[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/AminSassi/sassi-downloader?label=Latest%20Release)](https://github.com/AminSassi/sassi-downloader/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/AminSassi/sassi-downloader/ci.yml?branch=main&label=Build)](https://github.com/AminSassi/sassi-downloader/actions)

# Sassi Downloader

A modern desktop download manager built with Python and CustomTkinter featuring adaptive concurrency and intelligent retry logic.

Supports any video URL via yt-dlp — YouTube, TikTok, Instagram, Twitter/X, Facebook, Reddit, Vimeo, and 1000+ other sites.

![Screenshot](screenshot.png)

## Quick Start

**Windows (no install needed):**

1. Download [`Sassi Downloader.exe`](https://github.com/AminSassi/sassi-downloader/releases/latest) from Releases
2. Double-click to run

No Python, no dependencies, no installation.

## Features

- **Quality Selection** — Fetch all available formats, pick the one you want
- **Adaptive Concurrency** — 1–8 parallel streams per host, adjusted by server speed
- **Intelligent Retries** — Exponential backoff with error classification (transient, throttle, auth, permanent)
- **Priority Queue** — HIGH / NORMAL / LOW with bandwidth fairness and aging
- **Integrity Validation** — File size + SHA-256 checksum on completion
- **Server Cache** — Remembers per-host performance across sessions (6h TTL)
- **Pause / Resume / Cancel** — Thread-safe state machine
- **Cookie Support** — Import from Chrome/Edge/Firefox or load a cookies.txt file
- **Download History** — Atomic writes, persists across sessions
- **Tag Filtering** — Organize downloads by category (Movie, Music, Application, etc.)
- **Search** — Real-time debounced search across all downloads
- **Audit Logging** — Structured logs of all download events to `~/.sassi_audit.log`

## Architecture

```
sassi-downloader/
├── main.py                 # Entry point, build info, icon loading
├── icon.ico                # Custom icon (256/128/64/48/32/16px)
├── requirements.txt        # Python dependencies
├── ui/
│   └── main_window.py      # CustomTkinter UI (sidebar, table, dialogs)
└── core/
    ├── enums.py            # State machine (8 states), priority, error classification
    ├── task.py             # DownloadTask — thread-safe with pause/resume events
    ├── engine.py           # DownloadEngine — yt-dlp orchestration
    ├── scheduler.py        # Adaptive concurrency, host limiter, bandwidth scheduler
    ├── cache.py            # ServerCache (thread-safe), ErrorChain
    ├── verifier.py         # ChunkVerifier (stall/size detection), IntegrityValidator
    └── history.py          # AtomicHistory — crash-safe file writes
```

## Build from Source

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --noconsole --name "Sassi Downloader" --icon=icon.ico --collect-data customtkinter --hidden-import customtkinter --hidden-import yt_dlp main.py
```

The executable will be in `dist/Sassi Downloader.exe`.

## Running Tests

```bash
python -m pytest tests/ -v
```

The test suite covers:
- Security (path traversal, URL validation, no dangerous calls)
- Edge cases (corrupted files, negative values, empty inputs)
- Task lifecycle (pause, resume, cancel, state transitions)
- Format helpers (size/speed formatting across all magnitudes)

## Security

- No `os.system`, `shell=True`, `eval`, or `exec` anywhere in the codebase
- Path traversal prevention on download rename
- URL validation using `urllib.parse`
- `restrictfilenames` + `windowsfilenames` for safe output filenames
- Thread-safe shared state with `threading.Lock`
- All bare `except:` clauses replaced with `except Exception:`

## License

MIT
