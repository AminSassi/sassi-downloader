import threading
from urllib.parse import urlparse
from .enums import State, Priority, ErrorClass


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
        self.tag = ""
        self.rename = ""
        self.splits = 32
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
