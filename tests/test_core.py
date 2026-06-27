import os
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.enums import State, Priority, ErrorClass, classify_error
from core.task import DownloadTask
from core.engine import DownloadEngine
from core.cache import ServerCache, ErrorChain
from core.verifier import ChunkVerifier, IntegrityValidator
from core.history import AtomicHistory


class TestErrorClassification:
    @pytest.mark.parametrize("msg,expected", [
        ('403 Forbidden', ErrorClass.AUTH),
        ('404 Not Found', ErrorClass.PERMANENT),
        ('416 Range Not Satisfiable', ErrorClass.RANGE_MISMATCH),
        ('429 Too Many Requests', ErrorClass.THROTTLE),
        ('Connection timed out', ErrorClass.TRANSIENT),
        ('Something weird', ErrorClass.UNKNOWN),
    ])
    def test_classify(self, msg, expected):
        assert classify_error(msg) == expected


class TestTaskLifecycle:
    def test_pause_resume(self):
        t = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        t.state = State.DOWNLOADING
        t.pause()
        assert t.state == State.PAUSED
        t.resume()
        assert t.state == State.QUEUED

    def test_cancel(self):
        t = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        t.cancel()
        assert t.state == State.CANCELLED
        assert t.should_cancel()

    def test_pause_when_not_downloading(self):
        t = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        t.pause()
        assert t.state == State.QUEUED

    def test_unique_ids(self):
        t1 = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        t2 = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        assert t1.id != t2.id

    def test_tag_and_rename(self):
        t = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        t.tag = 'Movie'
        t.rename = 'custom_name'
        t.splits = 16
        assert t.tag == 'Movie'
        assert t.rename == 'custom_name'
        assert t.splits == 16


class TestFormatHelpers:
    def test_fmt_size(self):
        from ui.main_window import fmt_size
        assert fmt_size(0) == '0 B'
        assert fmt_size(-100) == '0 B'
        assert fmt_size(1023) == '1023 B'
        assert fmt_size(1048576) == '1.0 MB'
        assert fmt_size(1073741824) == '1.00 GB'
        assert fmt_size(1099511627776) == '1.00 TB'

    def test_fmt_speed(self):
        from ui.main_window import fmt_speed
        assert fmt_speed(0) == '0 B/s'
        assert fmt_speed(-50) == '0 B/s'
        assert fmt_speed(1024) == '1 KB/s'
        assert fmt_speed(1048576) == '1.0 MB/s'


class TestCorruptedData:
    def test_corrupted_history(self):
        tmp = tempfile.mktemp(suffix='.json')
        with open(tmp, 'w') as f:
            f.write('not valid json!!!')
        h = AtomicHistory(tmp)
        assert h.items == []
        os.remove(tmp)

    def test_corrupted_cache(self):
        import core.cache
        tmp = tempfile.mktemp(suffix='.json')
        with open(tmp, 'w') as f:
            f.write('bad data')
        old = core.cache.CACHE_FILE
        core.cache.CACHE_FILE = tmp
        sc = ServerCache()
        assert sc._data == {}
        core.cache.CACHE_FILE = old
        os.remove(tmp)

    def test_empty_file_rejected(self):
        valid, msg = IntegrityValidator.validate_file('', 0)
        assert not valid


class TestEngine:
    def test_cache_has_lock(self):
        import threading
        sc = ServerCache()
        assert isinstance(sc._lock, type(threading.Lock()))

    def test_add_and_cancel(self):
        e = DownloadEngine()
        t = DownloadTask('http://t', 'b', '/tmp', Priority.NORMAL)
        e.add(t)
        assert t in e.tasks
        t.cancel()
