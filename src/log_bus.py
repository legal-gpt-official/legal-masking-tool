"""LogBus: thread-safe log queue for GUI progress display.

Usage:
    bus = LogBus()
    # Worker thread:
    bus.emit("loading GiNZA model...")
    # GUI main thread (poll periodically):
    for msg in bus.drain():
        text_widget.insert("end", msg + "\n")
"""
from __future__ import annotations

import queue
import time
from typing import List


class LogBus:
    def __init__(self, maxsize: int = 500):
        self._q: queue.Queue[str] = queue.Queue(maxsize=maxsize)

    def emit(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        try:
            self._q.put_nowait(line)
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.put_nowait(line)
            except Exception:
                pass

    def drain(self) -> List[str]:
        items: List[str] = []
        while True:
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                break
        return items

    def clear(self) -> None:
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
