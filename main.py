import tkinter as tk
from tkinter import ttk, filedialog
import threading
import os
import sys
import json
import time
import math
import tempfile
import hashlib
import yt_dlp
from collections import defaultdict
from enum import Enum
from urllib.parse import urlparse

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".sassi_history.json")
CACHE_FILE = os.path.join(os.path.expanduser("~"), ".sassi_server_cache.json")

CACHE_TTL = 21600  # 6 hours
CONFIDENCE_DECAY = 0.85  # multiply confidence on failure
CONFIDENCE_RECOVER = 1.05  # multiply on success (capped at 1.0)
AGE_TICK = 300  # seconds before priority inflation check

# ── State Machine ───────────────────────────────────────────────
class State(Enum):
    QUEUED = "queued"
    CONNECTING = "connecting"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Priority(Enum):
    HIGH = 0
    NORMAL = 1
    LOW = 2

class ErrorClass(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AUTH = "auth"
    RANGE_MISMATCH = "range_mismatch"
    THROTTLE = "throttle"
    UNKNOWN = "unknown"

# ── Error Classification ────────────────────────────────────────
def classify_error(error_msg):
    e = error_msg.lower()
    if any(x in e for x in ['403', 'forbidden', 'unauthorized']):
        return ErrorClass.AUTH
    if any(x in e for x in ['404', 'not found', '410', 'gone']):
        return ErrorClass.PERMANENT
    if any(x in e for x in ['416', 'range', 'requested range']):
        return ErrorClass.RANGE_MISMATCH
    if any(x in e for x in ['429', 'too many', 'throttl', 'rate limit']):
        return ErrorClass.THROTTLE
    if any(x in e for x in ['timeout', 'timed out', 'connection reset',
                              'connection refused', 'network', 'eof',
                              'socket', 'broken pipe']):
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN

def should_retry(err_class):
    return err_class in (ErrorClass.TRANSIENT, ErrorClass.THROTTLE, ErrorClass.UNKNOWN)

# ── Error Cause Chain ───────────────────────────────────────────
class ErrorChain:
    def __init__(self):
        self._history = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, host, err_class):
        with self._lock:
            self._history[host].append({
                "class": err_class,
                "time": time.time()
            })
            if len(self._history[host]) > 50:
                self._history[host] = self._history[host][-50:]

    def get_pattern(self, host):
        with self._lock:
            recent = [e for e in self._history.get(host, []) if time.time() - e["time"] < 3600]
            if not recent:
                return None, 0
            counts = defaultdict(int)
            for e in recent:
                counts[e["class"]] += 1
            dominant = max(counts, key=counts.get)
            return dominant, counts[dominant]

    def should_degrade(self, host):
        pattern, count = self.get_pattern(host)
        if pattern == ErrorClass.TRANSIENT and count >= 3:
            return True, "repeated_transient"
        if pattern == ErrorClass.THROTTLE and count >= 2:
            return True, "throttled"
        if pattern == ErrorClass.RANGE_MISMATCH and count >= 2:
            return True, "unstable_server"
        return False, None

    def clear(self, host):
        with self._lock:
            self._history.pop(host, None)

# ── Server Capability Cache with TTL + Confidence ───────────────
class ServerCache:
    def __init__(self):
        self._data = self._load()

    def _load(self):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save(self):
        try:
            d = os.path.dirname(CACHE_FILE)
            fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                json.dump(self._data, f, indent=2)
            if os.name == 'nt' and os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
            os.rename(tmp, CACHE_FILE)
        except:
            pass

    def _default_profile(self):
        return {
            "range_support": True,
            "optimal_streams": 2,
            "avg_latency_ms": 200,
            "avg_speed_bps": 500000,
            "samples": 0,
            "confidence": 1.0,
            "last_update": 0,
            "failures": 0
        }

    def _is_stale(self, profile):
        return time.time() - profile.get("last_update", 0) > CACHE_TTL

    def get_profile(self, host):
        p = self._data.get(host, self._default_profile())
        if self._is_stale(p):
            p["confidence"] *= 0.7
            p["samples"] = max(1, p["samples"] // 2)
            p["last_update"] = time.time()
            self._data[host] = p
        return p

    def update(self, host, speed_bps, latency_ms=None, range_ok=True, success=True):
        p = self._data.get(host, self._default_profile())
        n = p["samples"]

        if success:
            p["avg_speed_bps"] = (p["avg_speed_bps"] * n + speed_bps) / (n + 1)
            if latency_ms is not None:
                p["avg_latency_ms"] = (p["avg_latency_ms"] * n + latency_ms) / (n + 1)
            p["samples"] = min(n + 1, 100)
            p["confidence"] = min(1.0, p["confidence"] * CONFIDENCE_RECOVER)
            p["failures"] = 0

            if p["avg_speed_bps"] > 1000000:
                p["optimal_streams"] = min(p["optimal_streams"] + 1, 8)
            elif p["avg_speed_bps"] < 100000:
                p["optimal_streams"] = max(p["optimal_streams"] - 1, 1)
        else:
            p["failures"] += 1
            p["confidence"] *= CONFIDENCE_DECAY
            if p["failures"] >= 3:
                p["optimal_streams"] = max(1, p["optimal_streams"] - 1)

        p["range_support"] = range_ok
        p["last_update"] = time.time()
        self._data[host] = p
        self._save()
        return p

    def get_optimal_streams(self, host):
        p = self.get_profile(host)
        effective = p["optimal_streams"]
        if p["confidence"] < 0.5:
            effective = 1
        elif p["confidence"] < 0.8:
            effective = max(1, effective - 1)
        return effective

    def get_confidence(self, host):
        return self.get_profile(host).get("confidence", 1.0)

# ── Chunk Verification Layer ────────────────────────────────────
class ChunkVerifier:
    def __init__(self):
        self._lock = threading.Lock()
        self._chunks = {}

    def start_tracking(self, task_id, expected_size):
        with self._lock:
            self._chunks[task_id] = {
                "expected_size": expected_size,
                "last_downloaded": 0,
                "stall_count": 0,
                "size_decreases": 0,
                "start_time": time.time()
            }

    def on_progress(self, task_id, downloaded, total):
        with self._lock:
            c = self._chunks.get(task_id)
            if not c:
                return True, "ok"

            if total > 0 and c["expected_size"] > 0 and total != c["expected_size"]:
                c["size_decreases"] += 1
                if c["size_decreases"] >= 3:
                    return False, "server_returned_different_file"

            if downloaded < c["last_downloaded"] and c["last_downloaded"] > 0:
                c["size_decreases"] += 1
                if c["size_decreases"] >= 3:
                    return False, "byte_count_decreased"

            if downloaded == c["last_downloaded"] and downloaded > 0:
                c["stall_count"] += 1
                if c["stall_count"] >= 30:
                    return False, "download_stalled"
            else:
                c["stall_count"] = 0

            c["last_downloaded"] = downloaded
            return True, "ok"

    def stop_tracking(self, task_id):
        with self._lock:
            self._chunks.pop(task_id, None)

    def validate_completion(self, task_id, actual_size):
        with self._lock:
            c = self._chunks.get(task_id, {})
            expected = c.get("expected_size", 0)
            if expected > 0 and actual_size != expected:
                return False, f"size_mismatch: expected {expected}, got {actual_size}"
            return True, "ok"

# ── Integrity Validator ─────────────────────────────────────────
class IntegrityValidator:
    @staticmethod
    def validate_file(filepath, expected_size=0):
        if not os.path.exists(filepath):
            return False, "File does not exist"
        actual = os.path.getsize(filepath)
        if expected_size > 0 and actual != expected_size:
            return False, f"Size mismatch: expected {expected_size}, got {actual}"
        if actual == 0:
            return False, "File is empty"
        return True, "OK"

    @staticmethod
    def compute_checksum(filepath, algo="md5"):
        h = hashlib.new(algo)
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

# ── Adaptive Concurrency ────────────────────────────────────────
class AdaptiveConcurrency:
    def __init__(self, server_cache, error_chain):
        self._cache = server_cache
        self._chain = error_chain

    def get_streams(self, host):
        should_degrade, reason = self._chain.should_degrade(host)
        if should_degrade:
            return 1
        return self._cache.get_optimal_streams(host)

    def adjust(self, host, success, speed_bps):
        self._cache.update(host, speed_bps, success=success)
        return self._cache.get_optimal_streams(host)

# ── Per-Host Limiter ────────────────────────────────────────────
class HostLimiter:
    def __init__(self):
        self._counts = defaultdict(int)
        self._max_per_host = 4
        self._global_max = 8
        self._global_count = 0
        self._lock = threading.Lock()

    def acquire(self, host):
        while True:
            with self._lock:
                if self._global_count < self._global_max and self._counts[host] < self._max_per_host:
                    self._counts[host] += 1
                    self._global_count += 1
                    return
            time.sleep(0.05)

    def release(self, host):
        with self._lock:
            self._counts[host] = max(0, self._counts[host] - 1)
            self._global_count = max(0, self._global_count - 1)

# ── UI Throttler ────────────────────────────────────────────────
class UIUpdater:
    def __init__(self, fps=8):
        self._interval = 1.0 / fps
        self._last = {}
        self._lock = threading.Lock()

    def should_update(self, task_id):
        now = time.time()
        with self._lock:
            if now - self._last.get(task_id, 0) >= self._interval:
                self._last[task_id] = now
                return True
            return False

    def cleanup(self, task_id):
        with self._lock:
            self._last.pop(task_id, None)

# ── Bandwidth Scheduler with Priority Aging ─────────────────────
class BandwidthScheduler:
    BASE_WEIGHTS = {Priority.HIGH: 3.0, Priority.NORMAL: 1.0, Priority.LOW: 0.5}
    MIN_GUARANTEE = 0.15

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()

    def set_priority(self, task_id, priority):
        with self._lock:
            self._tasks[task_id] = {
                "base_priority": priority,
                "effective_priority": priority,
                "weight": self.BASE_WEIGHTS[priority],
                "enqueue_time": time.time(),
                "last_age_tick": time.time()
            }

    def remove(self, task_id):
        with self._lock:
            self._tasks.pop(task_id, None)

    def _age_priorities(self):
        now = time.time()
        for tid, t in self._tasks.items():
            if now - t["last_age_tick"] < AGE_TICK:
                continue
            t["last_age_tick"] = now
            wait = now - t["enqueue_time"]
            ep = t["effective_priority"]
            if ep == Priority.LOW and wait > 120:
                t["effective_priority"] = Priority.NORMAL
                t["weight"] = self.BASE_WEIGHTS[Priority.NORMAL] * 1.2
            elif ep == Priority.NORMAL and wait > 300:
                t["effective_priority"] = Priority.HIGH
                t["weight"] = self.BASE_WEIGHTS[Priority.HIGH] * 1.1

    def get_share(self, task_id):
        with self._lock:
            self._age_priorities()
            t = self._tasks.get(task_id)
            if not t:
                return 1.0
            total = sum(x["weight"] for x in self._tasks.values()) or 1.0
            raw = t["weight"] / total
            return max(raw, self.MIN_GUARANTEE)

    def get_dispatch_priority(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            return t["effective_priority"] if t else Priority.NORMAL

# ── Atomic History ──────────────────────────────────────────────
class AtomicHistory:
    def __init__(self, path):
        self.path = path
        self.items = self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def add(self, title, path, size=0, checksum=""):
        self.items.insert(0, {
            "title": title, "path": path,
            "size": size, "checksum": checksum,
            "time": time.time()
        })
        if len(self.items) > 200:
            self.items = self.items[:200]
        self._atomic_write()

    def _atomic_write(self):
        try:
            d = os.path.dirname(self.path)
            fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            if os.name == 'nt' and os.path.exists(self.path):
                os.remove(self.path)
            os.rename(tmp, self.path)
        except:
            pass

    def clear(self):
        self.items = []
        self._atomic_write()

# ── Download Task ───────────────────────────────────────────────
class DownloadTask:
    _counter = 0

    def __init__(self, url, quality, folder, priority=Priority.NORMAL):
        DownloadTask._counter += 1
        self.id = DownloadTask._counter
        self.url = url
        self.quality = quality
        self.folder = folder
        self.priority = priority
        self.state = State.QUEUED
        self.progress = 0
        self.speed = 0
        self.eta = ""
        self.title = ""
        self.filename = ""
        self.filesize = 0
        self.downloaded = 0
        self.error = ""
        self.error_class = ErrorClass.UNKNOWN
        self.retries = 0
        self.max_retries = 8
        self.checksum = ""
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._pause.set()
        self._on_update = None
        self._on_done = None
        self._on_error = None

    @property
    def host(self):
        return urlparse(self.url).hostname or "unknown"

    def pause(self):
        if self.state in (State.DOWNLOADING, State.CONNECTING):
            self.state = State.PAUSED
            self._pause.clear()

    def resume(self):
        if self.state == State.PAUSED:
            self.state = State.QUEUED
            self._pause.set()

    def cancel(self):
        self._cancel.set()
        self._pause.set()
        self.state = State.CANCELLED

    def should_cancel(self):
        return self._cancel.is_set()

    def wait_if_paused(self):
        self._pause.wait(timeout=0.5)

# ── Download Engine ─────────────────────────────────────────────
class DownloadEngine:
    def __init__(self):
        self.server_cache = ServerCache()
        self.error_chain = ErrorChain()
        self.host_limiter = HostLimiter()
        self.concurrency = AdaptiveConcurrency(self.server_cache, self.error_chain)
        self.ui_updater = UIUpdater(fps=8)
        self.bandwidth = BandwidthScheduler()
        self.integrity = IntegrityValidator()
        self.chunk_verifier = ChunkVerifier()
        self.tasks = []
        self._active = 0
        self._max_concurrent = 4
        self._lock = threading.Lock()
        self._queue = []

    def add(self, task):
        with self._lock:
            self.tasks.append(task)
            self._queue.append(task)
        self.bandwidth.set_priority(task.id, task.priority)
        self._dispatch()

    def _dispatch(self):
        with self._lock:
            queued = [t for t in self._queue if t.state == State.QUEUED]
            queued.sort(key=lambda t: self.bandwidth.get_dispatch_priority(t.id).value)
            while self._active < self._max_concurrent and queued:
                task = queued.pop(0)
                self._queue.remove(task)
                task.state = State.CONNECTING
                self._active += 1
                threading.Thread(target=self._worker, args=(task,), daemon=True).start()

    def _worker(self, task):
        try:
            self.host_limiter.acquire(task.host)
            try:
                self._download(task)
            finally:
                self.host_limiter.release(task.host)
                self.bandwidth.remove(task.id)
                self.chunk_verifier.stop_tracking(task.id)
        except Exception as e:
            if not task.should_cancel():
                task.state = State.FAILED
                task.error = str(e)
                task.error_class = classify_error(str(e))
                self.error_chain.record(task.host, task.error_class)
                self._safe_call(task._on_error, task)
        finally:
            with self._lock:
                self._active -= 1
            self._dispatch()

    def _download(self, task):
        while not task.should_cancel():
            task.wait_if_paused()
            if task.should_cancel():
                return

            try:
                task.state = State.CONNECTING
                self._safe_call(task._on_update, task)

                stream_count = self.concurrency.get_streams(task.host)

                self.chunk_verifier.start_tracking(task.id, task.filesize)

                def hook(d):
                    if task.should_cancel():
                        raise yt_dlp.utils.DownloadCancelled()
                    task.wait_if_paused()
                    if task.should_cancel():
                        raise yt_dlp.utils.DownloadCancelled()

                    if d['status'] == 'downloading':
                        task.state = State.DOWNLOADING
                        task.progress = float(d.get('_percent_str', '0').replace('%', '').strip() or 0)
                        task.speed = d.get('_speed', 0) or 0
                        task.eta = d.get('_eta_str', '').strip()
                        task.downloaded = d.get('downloaded_bytes', 0) or 0
                        new_total = d.get('total_bytes', 0) or d.get('total_bytes_expect', 0) or 0
                        if new_total > 0:
                            task.filesize = new_total

                        ok, reason = self.chunk_verifier.on_progress(task.id, task.downloaded, task.filesize)
                        if not ok:
                            raise Exception(f"Chunk verification failed: {reason}")

                        self._safe_call(task._on_update, task)
                    elif d['status'] == 'finished':
                        task.progress = 100
                        self._safe_call(task._on_update, task)

                fmt = self._build_format(task)
                opts = {
                    'format': fmt,
                    'outtmpl': os.path.join(task.folder, '%(title)s.%(ext)s'),
                    'no_playlists': True,
                    'progress_hooks': [hook],
                    'quiet': True, 'no_warnings': True,
                    'continuedl': True, 'socket_timeout': 20,
                    'merge_output_format': 'mp4',
                    'http_chunk_size': 1048576,
                }
                if stream_count > 1:
                    opts['concurrent_fragment_downloads'] = min(stream_count, 6)

                start_time = time.time()

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(task.url, download=True)
                    task.title = info.get('title', 'video')
                    task.filename = ydl.prepare_filename(info)
                    task.filesize = info.get('filesize', 0) or 0
                    task.progress = 100

                elapsed = time.time() - start_time
                speed_avg = task.downloaded / elapsed if elapsed > 0 else 0

                chunk_ok, chunk_msg = self.chunk_verifier.validate_completion(task.id, os.path.getsize(task.filename) if os.path.exists(task.filename) else 0)
                if not chunk_ok:
                    raise Exception(f"Post-download verification: {chunk_msg}")

                valid, msg = self.integrity.validate_file(task.filename, task.filesize)
                if not valid:
                    raise Exception(f"Integrity check failed: {msg}")

                self.concurrency.adjust(task.host, True, speed_avg)
                self.server_cache.update(task.host, speed_avg, range_ok=True, success=True)
                self.error_chain.clear(task.host)

                task.state = State.COMPLETED
                self._safe_call(task._on_done, task)
                return

            except yt_dlp.utils.DownloadCancelled:
                return
            except Exception as e:
                err_class = classify_error(str(e))
                self.error_chain.record(task.host, err_class)

                if err_class == ErrorClass.AUTH:
                    task.state = State.FAILED
                    task.error = str(e)
                    task.error_class = err_class
                    self._safe_call(task._on_error, task)
                    return

                if err_class == ErrorClass.PERMANENT:
                    task.state = State.FAILED
                    task.error = str(e)
                    task.error_class = err_class
                    self._safe_call(task._on_error, task)
                    return

                if err_class == ErrorClass.RANGE_MISMATCH:
                    self.server_cache.update(task.host, 0, range_ok=False, success=False)
                    task.state = State.RETRYING
                    self._safe_call(task._on_update, task)
                    time.sleep(2)
                    task.retries += 1
                    if task.retries > task.max_retries:
                        task.state = State.FAILED
                        task.error = f"Max retries: {e}"
                        self._safe_call(task._on_error, task)
                        return
                    continue

                self.concurrency.adjust(task.host, False, 0)
                task.retries += 1
                if task.retries > task.max_retries:
                    task.state = State.FAILED
                    task.error = f"Max retries exceeded: {e}"
                    task.error_class = err_class
                    self._safe_call(task._on_error, task)
                    return

                task.state = State.RETRYING
                task.error = str(e)
                task.error_class = err_class
                self._safe_call(task._on_update, task)

                backoff = min(2 ** task.retries, 60)
                for _ in range(int(backoff)):
                    if task.should_cancel():
                        return
                    time.sleep(1)

    def _build_format(self, task):
        if task.quality == "best":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        return f"{task.quality}+bestaudio/best"

    def _safe_call(self, fn, *args):
        if fn:
            try:
                fn(*args)
            except:
                pass

# ── Colors ──────────────────────────────────────────────────────
BG = "#0d1117"
BG_CARD = "#161b22"
BG_GLASS = "#1c2333"
BG_INPUT = "#21262d"
FG = "#e6edf3"
FG_DIM = "#7d8590"
FG_BRIGHT = "#f0f6fc"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"
BORDER = "#30363d"

# ── UI ──────────────────────────────────────────────────────────
class SassiDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Sassi Downloader")
        self.root.geometry("740x750")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.engine = DownloadEngine()
        self.history = AtomicHistory(HISTORY_FILE)
        self.formats = []
        self.cards = {}
        self._build()

    def _build(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill=tk.X, padx=20, pady=(12, 2))
        tk.Label(hdr, text="Sassi", font=("Segoe UI", 22, "bold"),
                 fg=FG_BRIGHT, bg=BG).pack(side=tk.LEFT)
        tk.Label(hdr, text="Downloader", font=("Segoe UI", 22),
                 fg=FG_DIM, bg=BG).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(hdr, text="v4.1", font=("Segoe UI", 9),
                 fg=FG_DIM, bg=BG).pack(side=tk.LEFT, padx=(8, 0), pady=(6, 0))

        card = tk.Frame(self.root, bg=BG_GLASS, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.X, padx=20, pady=(8, 4))
        tk.Label(card, text="URL", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG_GLASS).pack(anchor=tk.W, padx=12, pady=(10, 2))
        row = tk.Frame(card, bg=BG_GLASS)
        row.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.url_entry = tk.Entry(row, font=("Consolas", 10), bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief=tk.FLAT,
                                   highlightbackground=BORDER, highlightthickness=1)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)
        self.url_entry.bind("<Return>", lambda e: self.fetch())
        self.fetch_btn = tk.Button(row, text="Fetch", font=("Segoe UI", 9, "bold"),
                                    bg=ACCENT, fg=BG, relief=tk.FLAT, cursor="hand2",
                                    activebackground="#79c0ff", command=self.fetch)
        self.fetch_btn.pack(side=tk.RIGHT, padx=(6, 0), ipadx=10, ipady=5)

        opts = tk.Frame(self.root, bg=BG_GLASS, highlightbackground=BORDER, highlightthickness=1)
        opts.pack(fill=tk.X, padx=20, pady=4)
        orow = tk.Frame(opts, bg=BG_GLASS)
        orow.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(orow, text="Quality", font=("Segoe UI", 9), fg=FG_DIM, bg=BG_GLASS).pack(side=tk.LEFT)
        self.quality_var = tk.StringVar(value="Best")
        self.q_menu = ttk.Combobox(orow, textvariable=self.quality_var, state="readonly",
                                    width=20, font=("Segoe UI", 9))
        self.q_menu.pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(orow, text="Priority", font=("Segoe UI", 9), fg=FG_DIM, bg=BG_GLASS).pack(side=tk.LEFT, padx=(12, 0))
        self.priority_var = tk.StringVar(value="Normal")
        self.p_menu = ttk.Combobox(orow, textvariable=self.priority_var, state="readonly",
                                    width=8, font=("Segoe UI", 9),
                                    values=["High", "Normal", "Low"])
        self.p_menu.pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(orow, text="Save to", font=("Segoe UI", 9), fg=FG_DIM, bg=BG_GLASS).pack(side=tk.LEFT, padx=(12, 0))
        self.dl_path = self._default_path()
        self.folder_btn = tk.Button(orow, text=os.path.basename(self.dl_path),
                                     font=("Segoe UI", 9), bg=BG_INPUT, fg=ACCENT,
                                     relief=tk.FLAT, cursor="hand2", command=self.pick_folder)
        self.folder_btn.pack(side=tk.LEFT, padx=(4, 0), ipadx=4, ipady=1)

        self.dl_btn = tk.Button(orow, text="Download", font=("Segoe UI", 9, "bold"),
                                 bg=GREEN, fg=BG, relief=tk.FLAT, cursor="hand2",
                                 activebackground="#56d364", command=self.download)
        self.dl_btn.pack(side=tk.RIGHT, ipadx=12, ipady=3)

        tk.Label(self.root, text="Active Downloads", font=("Segoe UI", 10, "bold"),
                 fg=FG, bg=BG).pack(anchor=tk.W, padx=20, pady=(8, 2))

        dl_outer = tk.Frame(self.root, bg=BG)
        dl_outer.pack(fill=tk.BOTH, expand=True, padx=(20, 20))
        self.dl_canvas = tk.Canvas(dl_outer, bg=BG, highlightthickness=0)
        self.dl_scroll = tk.Scrollbar(dl_outer, orient=tk.VERTICAL, command=self.dl_canvas.yview)
        self.dl_frame = tk.Frame(self.dl_canvas, bg=BG)
        self.dl_frame.bind("<Configure>", lambda e: self.dl_canvas.configure(scrollregion=self.dl_canvas.bbox("all")))
        self.dl_canvas.create_window((0, 0), window=self.dl_frame, anchor=tk.NW)
        self.dl_canvas.configure(yscrollcommand=self.dl_scroll.set)
        self.dl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.dl_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        hh = tk.Frame(self.root, bg=BG)
        hh.pack(fill=tk.X, padx=20, pady=(6, 0))
        tk.Label(hh, text="History", font=("Segoe UI", 10, "bold"), fg=FG, bg=BG).pack(side=tk.LEFT)
        tk.Button(hh, text="Clear", font=("Segoe UI", 8), fg=RED, bg=BG,
                  relief=tk.FLAT, cursor="hand2", command=self.clear_hist).pack(side=tk.RIGHT)

        hist_card = tk.Frame(self.root, bg=BG_GLASS, highlightbackground=BORDER, highlightthickness=1)
        hist_card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(2, 12))
        self.hist_list = tk.Listbox(hist_card, bg=BG_GLASS, fg=FG_DIM,
                                     font=("Consolas", 8), highlightthickness=0,
                                     selectbackground=BORDER, selectforeground=FG,
                                     relief=tk.FLAT, bd=0)
        self.hist_list.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.hist_list.bind("<Double-1>", self.open_hist)
        self._refresh_hist()

    def _default_path(self):
        if sys.platform == "win32":
            import winreg
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
                p = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
                winreg.CloseKey(k)
                return p
            except: pass
        return os.path.join(os.path.expanduser("~"), "Downloads")

    def pick_folder(self):
        f = filedialog.askdirectory(initialdir=self.dl_path)
        if f:
            self.dl_path = f
            self.folder_btn.config(text=os.path.basename(f))

    def _refresh_hist(self):
        self.hist_list.delete(0, tk.END)
        for i in self.history.items[:40]:
            self.hist_list.insert(tk.END, f"  {i['title'][:55]}")

    def open_hist(self, e):
        s = self.hist_list.curselection()
        if s:
            p = self.history.items[s[0]]['path']
            if os.path.exists(p):
                os.startfile(os.path.dirname(p))

    def clear_hist(self):
        self.history.clear()
        self._refresh_hist()

    def fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.fetch_btn.config(text="...", state=tk.DISABLED)
        def work():
            try:
                o = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                with yt_dlp.YoutubeDL(o) as y:
                    info = y.extract_info(url, download=False)
                fmts = [("Best (auto)", "best")]
                seen = {"best"}
                for f in info.get('formats', []):
                    h = f.get('height')
                    ext = f.get('ext', '')
                    vc = f.get('vcodec', 'none')
                    if vc != 'none' and h and h >= 360:
                        l = f"{h}p ({ext.upper()})"
                        if l not in seen:
                            seen.add(l)
                            fmts.append((l, f['format_id']))
                fmts.sort(key=lambda x: int(x[0].split('p')[0]) if x[1] != "best" else 99999, reverse=True)
                self.formats = fmts
                self.root.after(0, self._fetch_ok)
            except Exception:
                self.root.after(0, self._fetch_err)
        threading.Thread(target=work, daemon=True).start()

    def _fetch_ok(self):
        self.fetch_btn.config(text="Fetch", state=tk.NORMAL)
        self.q_menu['values'] = [f[0] for f in self.formats]
        self.q_menu.current(0)

    def _fetch_err(self):
        self.fetch_btn.config(text="Fetch", state=tk.NORMAL)

    def download(self):
        url = self.url_entry.get().strip()
        if not url or not self.formats:
            return
        i = self.q_menu.current()
        q = self.formats[i][1] if i >= 0 else "best"

        p = self.priority_var.get().lower()
        pri = Priority.HIGH if p == "high" else Priority.LOW if p == "low" else Priority.NORMAL

        task = DownloadTask(url, q, self.dl_path, pri)
        card = self._make_card(task)
        self.cards[task.id] = card
        self.engine.add(task)
        task._on_update = lambda t: self.root.after(0, self._upd_card, t)
        task._on_done = lambda t: self.root.after(0, self._done_card, t)
        task._on_error = lambda t: self.root.after(0, self._err_card, t)
        self.url_entry.delete(0, tk.END)

    def _make_card(self, task):
        pri_colors = {Priority.HIGH: RED, Priority.NORMAL: FG_DIM, Priority.LOW: FG_DIM}
        pri_labels = {Priority.HIGH: "HIGH", Priority.NORMAL: "", Priority.LOW: "LOW"}

        c = tk.Frame(self.dl_frame, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        c.pack(fill=tk.X, padx=2, pady=2, ipady=4)

        top = tk.Frame(c, bg=BG_CARD)
        top.pack(fill=tk.X, padx=8, pady=(4, 0))

        pri_text = pri_labels.get(task.priority, "")
        title_text = f"[{pri_text}] Queued..." if pri_text else "Queued..."
        title = tk.Label(top, text=title_text, font=("Segoe UI", 9),
                          fg=FG, bg=BG_CARD, anchor=tk.W)
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctrl = tk.Frame(top, bg=BG_CARD)
        ctrl.pack(side=tk.RIGHT)

        pause = tk.Button(ctrl, text="\u23f8", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM,
                           relief=tk.FLAT, cursor="hand2", width=3,
                           command=lambda: self._toggle_pause(task))
        pause.pack(side=tk.LEFT)

        cancel = tk.Button(ctrl, text="\u2715", font=("Segoe UI", 9), bg=BG_CARD, fg=RED,
                            relief=tk.FLAT, cursor="hand2", width=3,
                            command=lambda: self._cancel_task(task))
        cancel.pack(side=tk.LEFT)

        prog = tk.Canvas(c, bg=BORDER, height=3, highlightthickness=0)
        prog.pack(fill=tk.X, padx=8, ipady=0)
        bar = prog.create_rectangle(0, 0, 0, 3, fill=ACCENT, width=0)

        info = tk.Label(c, text="Waiting...", font=("Consolas", 8),
                         fg=FG_DIM, bg=BG_CARD, anchor=tk.W)
        info.pack(fill=tk.X, padx=8, pady=(3, 0))

        return {"frame": c, "title": title, "pause": pause, "cancel": cancel,
                "prog": prog, "bar": bar, "info": info}

    def _upd_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return

        if task.state == State.PAUSED:
            card["title"].config(text=f"\u23f8 {task.title[:44] or 'Paused'}")
            card["info"].config(text="Paused", fg=YELLOW)
            return

        if task.state == State.RETRYING:
            ecls = task.error_class.value if task.error_class else ""
            card["title"].config(text=f"\u21bb Retry {task.retries}/{task.max_retries}")
            card["info"].config(text=f"{ecls}: {task.error[:40]}", fg=YELLOW)
            return

        if task.state == State.CONNECTING:
            card["title"].config(text=f"Connecting... ({task.host})")
            card["info"].config(text="Detecting server capabilities", fg=FG_DIM)
            return

        pct = task.progress / 100
        w = card["prog"].winfo_width()
        card["prog"].coords(card["bar"], 0, 0, max(w * pct, 2), 3)

        if task.title:
            card["title"].config(text=task.title[:48])

        parts = [f"{task.progress:.1f}%"]
        if task.speed > 0:
            parts.append(f"{task.speed / 1024:.0f} KB/s")
        if task.eta:
            parts.append(task.eta)
        share = self.engine.bandwidth.get_share(task.id)
        if share < 0.9:
            parts.append(f"share:{share:.0%}")
        conf = self.engine.server_cache.get_confidence(task.host)
        if conf < 0.8:
            parts.append(f"conf:{conf:.0%}")
        card["info"].config(text="  ·  ".join(parts), fg=FG_DIM)

    def _done_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        w = card["prog"].winfo_width()
        card["prog"].coords(card["bar"], 0, 0, w, 3)
        card["prog"].itemconfig(card["bar"], fill=GREEN)
        valid, msg = self.engine.integrity.validate_file(task.filename, task.filesize)
        status = f"Complete · {msg}" if valid else f"Complete · {msg}"
        card["info"].config(text=status, fg=GREEN)
        card["title"].config(text=f"\u2713 {task.title[:46]}")
        card["pause"].config(state=tk.DISABLED)
        card["cancel"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)
        cs = self.engine.integrity.compute_checksum(task.filename)[:12] if os.path.exists(task.filename) else ""
        self.history.add(task.title, task.filename, task.filesize, cs)
        self._refresh_hist()

    def _err_card(self, task):
        card = self.cards.get(task.id)
        if not card:
            return
        card["prog"].itemconfig(card["bar"], fill=RED)
        ecls = task.error_class.value if task.error_class else ""
        card["info"].config(text=f"Failed ({ecls}): {task.error[:50]}", fg=RED)
        card["title"].config(text=f"\u2717 {task.title[:46] or 'Error'}")
        card["pause"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)

    def _toggle_pause(self, task):
        if task.state == State.PAUSED:
            task.resume()
        elif task.state in (State.DOWNLOADING, State.CONNECTING):
            task.pause()

    def _cancel_task(self, task):
        task.cancel()
        card = self.cards.get(task.id)
        if card:
            card["prog"].itemconfig(card["bar"], fill=RED)
            card["info"].config(text="Cancelled", fg=RED)
            card["title"].config(text="\u2717 Cancelled")
            card["pause"].config(state=tk.DISABLED)
            card["cancel"].config(state=tk.DISABLED)
        self.engine.ui_updater.cleanup(task.id)

if __name__ == "__main__":
    root = tk.Tk()
    app = SassiDownloader(root)
    root.mainloop()
