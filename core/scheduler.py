import time
import threading
from collections import defaultdict
from .enums import Priority

AGE_TICK = 300


class AdaptiveConcurrency:
    def __init__(self, server_cache, error_chain):
        self._cache = server_cache
        self._chain = error_chain

    def get_streams(self, host):
        should_degrade, _ = self._chain.should_degrade(host)
        if should_degrade:
            return 1
        return self._cache.get_optimal_streams(host)

    def adjust(self, host, success, speed_bps):
        self._cache.update(host, speed_bps, success=success)
        return self._cache.get_optimal_streams(host)


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


class BandwidthScheduler:
    BASE_WEIGHTS = {Priority.HIGH: 3.0, Priority.NORMAL: 1.0, Priority.LOW: 0.5}
    MIN_GUARANTEE = 0.15

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()

    def set_priority(self, task_id, priority):
        with self._lock:
            self._tasks[task_id] = {
                "base_priority": priority, "effective_priority": priority,
                "weight": self.BASE_WEIGHTS[priority],
                "enqueue_time": time.time(), "last_age_tick": time.time()
            }

    def remove(self, task_id):
        with self._lock:
            self._tasks.pop(task_id, None)

    def _age_priorities(self):
        now = time.time()
        for t in self._tasks.values():
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
            return max(t["weight"] / total, self.MIN_GUARANTEE)

    def get_dispatch_priority(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            return t["effective_priority"] if t else Priority.NORMAL
