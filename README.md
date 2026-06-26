# Sassi Downloader

A production-grade download manager with adaptive concurrency, intelligent retry logic, and a clean dark UI. Supports any video URL via yt-dlp (TikTok, YouTube, Instagram, Twitter, Facebook, Twitch, and 1000+ other sites).

## Features

- **Adaptive Concurrency** — Automatically adjusts 1–8 streams per host based on server response speed
- **Intelligent Retries** — Exponential backoff with error classification (transient vs permanent)
- **Priority Queue** — HIGH / NORMAL / LOW priority scheduling with bandwidth fairness
- **Integrity Validation** — File size verification + MD5 checksum on completion
- **Server Capability Cache** — Remembers per-host performance profiles across sessions
- **Pause / Resume / Cancel** — Thread-safe state machine with 8 explicit states
- **Download History** — Atomic writes, persists across sessions
- **Quality Selection** — Fetches available formats, lets you choose before downloading

## Architecture

```
┌─────────────────────────────────────────────┐
│                  UI Layer                    │
│  Throttled at 8 FPS · Delta-only renders    │
├─────────────────────────────────────────────┤
│              Download Engine                 │
│  AdaptiveConcurrency · HostLimiter           │
│  BandwidthScheduler · ErrorClassifier        │
├─────────────────────────────────────────────┤
│           Infrastructure Layer               │
│  ServerCache · AtomicHistory · Integrity     │
└─────────────────────────────────────────────┘
```

## Requirements

- Python 3.10+
- `yt-dlp`
- `tkinter` (included with Python)

## Usage

### From source

```bash
pip install yt-dlp
python main.py
```

### Build executable

```bash
pip install pyinstaller yt-dlp
pyinstaller --onefile --windowed --name "Sassi Downloader" --icon=icon.ico main.py
```

The `.exe` will be in `dist/`.

## How it works

1. **Paste** any video URL
2. **Fetch** — queries the server for available quality formats
3. **Choose** quality + priority (High / Normal / Low)
4. **Download** — engine handles concurrency, retries, integrity

## Error handling

| Error Type | Behavior |
|---|---|
| Transient (timeout, reset) | Retry with exponential backoff |
| Permanent (404, 410) | Stop immediately |
| Auth (403) | Stop — requires user action |
| Throttle (429) | Back off, then retry |
| Range mismatch | Fallback to single-stream |

## License

MIT
