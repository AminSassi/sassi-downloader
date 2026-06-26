import os
import json
import time
import tempfile
import threading
from collections import defaultdict
from .enums import ErrorClass

CACHE_TTL = 21600
CONFIDENCE_DECAY = 0.85

class ErrorChain:
    def __init__(self):
        self._history = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, host, err_class):
        with self._lock:
            self._history[host].append({"class": err_class, "time": time.time()})
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
        if not pattern or count < 2:
            return False, None
        if pattern == ErrorClass.TRANSIENT and count >= 4:
            return True, "repeated_transient"
        if pattern == ErrorClass.THROTTLE and count >= 3:
            return True, "throttled"
        if pattern == ErrorClass.RANGE_MISMATCH and count >= 2:
            return True, "unstable_server"
        if pattern == ErrorClass.PERMANENT:
            return True, "permanent_failure"
        return False, None

    def clear(self, host):
        with self._lock:
            self._history.pop(host, None)


CACHE_FILE = os.path.join(os.path.expanduser("~"), ".sassi_server_cache.json")

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
            "range_support": True, "optimal_streams": 2,
            "avg_latency_ms": 200, "avg_speed_bps": 500000,
            "samples": 0, "confidence": 1.0,
            "last_update": 0, "failures": 0
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
            gap = 1.0 - p["confidence"]
            p["confidence"] = min(1.0, p["confidence"] + gap * 0.3 + 0.02)
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
        e = p["optimal_streams"]
        if p["confidence"] < 0.5:
            e = 1
        elif p["confidence"] < 0.8:
            e = max(1, e - 1)
        return e

    def get_confidence(self, host):
        return self.get_profile(host).get("confidence", 1.0)
