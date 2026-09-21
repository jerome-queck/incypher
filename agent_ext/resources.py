"""Shared, bounded local-tool admission; independent of model request admission."""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass


class AdmissionError(RuntimeError):
    """A sanitised reason for refusing or cancelling admission."""


def positive_int(value: int) -> bool:
    return type(value) is int and value > 0


@dataclass(frozen=True)
class Cost:
    memory_bytes: int
    pids: int = 1
    heavy: bool = False

    def __post_init__(self):
        if not positive_int(self.memory_bytes) or not positive_int(self.pids):
            raise ValueError("cost must contain positive integer estimates")
        if type(self.heavy) is not bool:
            raise ValueError("heavy must be boolean")


@dataclass(frozen=True)
class Capacity:
    # These are tool-pool budgets AFTER reserving controller/container headroom.
    memory_bytes: int
    pids: int
    active: int = 2
    heavy: int = 1
    queued: int = 8

    def __post_init__(self):
        if not all(positive_int(v) for v in vars(self).values()):
            raise ValueError("capacity values must be positive integers")
        if self.heavy > self.active:
            raise ValueError("heavy capacity exceeds total active capacity")


class Lease:
    def __init__(self, pool: "Admission", cost: Cost):
        self._pool, self._cost = pool, cost
        self._released = False

    def release(self):
        with self._pool._condition:
            if not self._released:
                self._released = True
                self._pool._active -= 1
                self._pool._heavy -= int(self._cost.heavy)
                self._pool._memory -= self._cost.memory_bytes
                self._pool._pids -= self._cost.pids
                self._pool._condition.notify_all()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.release()


class Admission:
    """FIFO reservations, with finite queue waits and cancellation polling.

    Estimates are not kernel enforcement or measurements. All tools must share
    this instance; callers must not reserve once outside and again inside dispatch.
    """

    def __init__(self, capacity: Capacity):
        self.capacity = capacity
        self._condition = threading.Condition()
        self._queue = deque()
        self._active = self._heavy = self._memory = self._pids = 0

    def snapshot(self):
        with self._condition:
            return dict(active=self._active, heavy=self._heavy,
                        memory_bytes=self._memory, pids=self._pids,
                        queued=len(self._queue))

    def acquire(self, cost: Cost, *, deadline: float,
                cancellation: threading.Event | None = None) -> Lease:
        if (type(deadline) not in (int, float) or not math.isfinite(deadline)):
            raise ValueError("a finite monotonic deadline is required")
        cap = self.capacity
        if cost.memory_bytes > cap.memory_bytes or cost.pids > cap.pids:
            raise AdmissionError("cost_exceeds_capacity")
        ticket = object()
        with self._condition:
            if cancellation is not None and cancellation.is_set():
                raise AdmissionError("cancelled")
            if time.monotonic() >= deadline:
                raise AdmissionError("queue_timeout")
            if len(self._queue) >= cap.queued:
                raise AdmissionError("queue_full")
            self._queue.append(ticket)
            try:
                while True:
                    if cancellation is not None and cancellation.is_set():
                        raise AdmissionError("cancelled")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise AdmissionError("queue_timeout")
                    fits = (self._active < cap.active
                            and self._heavy + int(cost.heavy) <= cap.heavy
                            and self._memory + cost.memory_bytes <= cap.memory_bytes
                            and self._pids + cost.pids <= cap.pids)
                    if self._queue[0] is ticket and fits:
                        self._active += 1
                        self._heavy += int(cost.heavy)
                        self._memory += cost.memory_bytes
                        self._pids += cost.pids
                        return Lease(self, cost)
                    self._condition.wait(min(remaining, 0.02))
            finally:
                self._queue.remove(ticket)
                self._condition.notify_all()
