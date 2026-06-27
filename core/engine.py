import os
import time
import threading
import yt_dlp
from .enums import State, ErrorClass, classify_error
from .cache import ServerCache, ErrorChain
from .verifier import ChunkVerifier, IntegrityValidator
from .scheduler import AdaptiveConcurrency, HostLimiter, UIUpdater, BandwidthScheduler
from .task import DownloadTask

COOKIE_FILE = os.path.join(os.path.expanduser("~"), ".sassi_cookies.txt")


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
                outtmpl = os.path.join(task.folder, '%(title)s.%(ext)s')
                if task.rename:
                    base, ext = os.path.splitext(task.rename)
                    if ext:
                        outtmpl = os.path.join(task.folder, task.rename)
                    else:
                        outtmpl = os.path.join(task.folder, task.rename + '.%(ext)s')
                opts = {
                    'format': fmt,
                    'outtmpl': outtmpl,
                    'no_playlists': True, 'progress_hooks': [hook],
                    'quiet': True, 'no_warnings': True,
                    'continuedl': True, 'socket_timeout': 20,
                    'merge_output_format': 'mp4', 'http_chunk_size': 1048576,
                    'extractor_retries': 3,
                    'retries': 3,
                    'fragment_retries': 3,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                    },
                }
                if os.path.exists(COOKIE_FILE):
                    opts['cookiefile'] = COOKIE_FILE
                splits = getattr(task, 'splits', 32)
                if stream_count > 1:
                    opts['concurrent_fragment_downloads'] = min(stream_count, max(1, splits // 8))

                start_time = time.time()
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(task.url, download=True)
                    task.title = info.get('title', 'video')
                    task.filename = ydl.prepare_filename(info)
                    task.filesize = info.get('filesize', 0) or 0
                    task.progress = 100

                elapsed = time.time() - start_time
                speed_avg = task.downloaded / elapsed if elapsed > 0 else 0

                chunk_ok, chunk_msg = self.chunk_verifier.validate_completion(
                    task.id, os.path.getsize(task.filename) if os.path.exists(task.filename) else 0)
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
                if err_class in (ErrorClass.AUTH, ErrorClass.PERMANENT):
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
