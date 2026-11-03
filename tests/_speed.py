"""Speed of this machine against the development desktop, for time budget tests (post-mortem 0.28.0, P1 #11)

A budget test asserts a slot holds the UI thread less than N ms. Written on a fast desktop, the same bound failed
now and then on CI runners several times slower. budget(seconds) scales a bound by how slow this machine is:
a reference workload (a plain Python loop and empty Qt event loop rounds, best of several runs) is timed once per
test process and compared with its time on the desktop the bounds were written on. Never below the written bound
(factor 1 on a fast machine), never above MAX_FACTOR (a budget test must still catch work back on the UI thread).

NEOPEDAL_SPEED_FACTOR=<number> sets the factor instead (1: written bounds, to check them on a slow machine).
"""

from __future__ import annotations

import os
import time
from functools import cache

# Best-of time (seconds) of reference_round on the development desktop (Ryzen, Windows 11, Python 3.14)
REFERENCE_SECONDS = 0.024
MAX_FACTOR = 6.0
RUNS = 7


def reference_round() -> float:
    """Seconds of one round of the reference workload: Python loop (dict & arithmetic), then 200 rounds of an
    empty Qt event loop running a zero timer (what a page slot and its signals cost)"""
    from PySide6.QtCore import QCoreApplication, QTimer

    start = time.perf_counter()
    total = 0
    data: dict[int, str] = {}
    for index in range(100_000):
        total += index * index % 7
        data[index & 1023] = str(index)
    for _ in range(200):
        QTimer.singleShot(0, _nothing)
        QCoreApplication.processEvents()
    return time.perf_counter() - start


def _nothing():
    pass


@cache
def factor() -> float:
    """How many times slower than the development desktop this machine runs the reference (1 to MAX_FACTOR),
    measured once per process: best of RUNS rounds, so a busy moment does not count"""
    forced = os.environ.get("NEOPEDAL_SPEED_FACTOR")
    if forced:
        return max(float(forced), 0.1)
    best = min(reference_round() for _ in range(RUNS))
    return min(max(best / REFERENCE_SECONDS, 1.0), MAX_FACTOR)


def budget(seconds: float) -> float:
    """Time bound of a budget test on this machine: the bound written for the desktop, times factor()"""
    return seconds * factor()
