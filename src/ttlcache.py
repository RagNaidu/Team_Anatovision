"""A tiny time-limited cache for identical helper calls (rewrite a follow-up, rerank the same passages). OFF by default (0 seconds), so nothing
changes unless a server turns it on: the JSON API does at start-up (HELPER_CACHE_SECONDS, default 120; 0 turns it off again).
An identical request inside the window gets the answer the first call produced; nothing is stored for longer, nothing is written to disk."""
import hashlib
import json
import threading
import time

settings = {"seconds": 0}
MAX_ENTRIES = 256


_all = []


def configure(seconds):
    """Turn the caches on (seconds > 0) or off (0). Either way they start empty."""
    settings["seconds"] = max(0, int(seconds))
    for c in _all:
        c.clear()


def key_of(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class TTLCache:
    def __init__(self):
        self.items, self.lock = {}, threading.Lock()
        _all.append(self)

    def get(self, key):
        if not settings["seconds"]:
            return None
        with self.lock:
            hit = self.items.get(key)
            if hit and time.time() - hit[0] <= settings["seconds"]:
                return hit[1]
            self.items.pop(key, None)
        return None

    def put(self, key, value):
        if not settings["seconds"]:
            return
        with self.lock:
            if len(self.items) >= MAX_ENTRIES:
                self.items.pop(min(self.items, key=lambda k: self.items[k][0]))
            self.items[key] = (time.time(), value)

    def clear(self):
        with self.lock:
            self.items.clear()
