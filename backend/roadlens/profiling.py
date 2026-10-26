"""Bounded HTTP setup timings; source timestamps never use this clock."""

from collections import deque
from statistics import fmean
from threading import Lock


class ResponseProfiler:
    def __init__(self, window_size: int = 120):
        self.window_size = window_size
        self._lock = Lock()
        self._samples = {}

    def record(self, route: str, milliseconds: float):
        with self._lock:
            if route not in self._samples:
                if len(self._samples) >= 64:
                    return
                self._samples[route] = deque(maxlen=self.window_size)
            self._samples[route].append(milliseconds)

    def snapshot(self):
        with self._lock:
            records = {route: list(values) for route, values in self._samples.items()}
        routes = []
        for route, values in sorted(records.items()):
            ordered = sorted(values)
            position = .95 * (len(values) - 1)
            low = int(position)
            high = min(low + 1, len(values) - 1)
            routes.append({"route": route, "window_samples": len(values),
                           "mean_ms": fmean(values),
                           "p95_ms": ordered[low] + (ordered[high] - ordered[low]) * (position - low),
                           "latest_ms": values[-1]})
        return {"window_size": self.window_size, "routes": routes,
                "scope": "Request dispatch through response headers; excludes streaming body transfer, browser rendering and network transit."}
