import os
import json
import time
import tempfile


class AtomicHistory:
    def __init__(self, path):
        self.path = path
        self.items = self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
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
        except Exception:
            pass

    def clear(self):
        self.items = []
        self._atomic_write()
