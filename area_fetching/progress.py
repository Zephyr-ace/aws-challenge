"""Progress tracking for the find_areas pipeline."""

from __future__ import annotations

import sys
import threading
import time


class ProgressTracker:
    """Thread-safe progress tracker with percentage display.

    Prints a single updating line to stderr showing the current phase,
    completed count, total count, percentage, and elapsed time.
    """

    def __init__(self, phase: str, total: int) -> None:
        self.phase = phase
        self.total = max(total, 1)
        self._completed = 0
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._print()

    def advance(self, n: int = 1) -> None:
        """Mark *n* items as completed and refresh the display."""
        with self._lock:
            self._completed = min(self._completed + n, self.total)
            self._print()

    def finish(self) -> None:
        """Mark the phase as 100 % complete and print a final newline."""
        with self._lock:
            self._completed = self.total
            self._print()
            sys.stderr.write("\n")
            sys.stderr.flush()

    def _print(self) -> None:
        pct = self._completed / self.total * 100
        elapsed = time.monotonic() - self._start
        bar_len = 30
        filled = int(bar_len * self._completed / self.total)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stderr.write(
            f"\r  {self.phase}: {bar} {pct:5.1f}%  "
            f"({self._completed}/{self.total})  "
            f"[{elapsed:.0f}s]   "
        )
        sys.stderr.flush()
