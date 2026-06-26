import os
import time
import hashlib
import threading


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
            elapsed = time.time() - c["start_time"]
            if downloaded == c["last_downloaded"] and downloaded > 0:
                c["stall_count"] += 1
                stall_limit = 60 if elapsed < 10 else 45 if elapsed < 60 else 30
                if c["stall_count"] >= stall_limit:
                    return False, "download_stalled"
            else:
                c["stall_count"] = max(0, c["stall_count"] - 2)
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
