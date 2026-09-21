import threading
import time
import unittest

from agent_ext.resources import Admission, AdmissionError, Capacity, Cost


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.pool = Admission(Capacity(memory_bytes=100, pids=3, active=3, queued=1))

    def acquire(self, cost=None, **kwargs):
        return self.pool.acquire(cost or Cost(10), deadline=time.monotonic() + 0.5, **kwargs)

    def wait_queued(self):
        deadline = time.monotonic() + 1
        while self.pool.snapshot()["queued"] == 0 and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertEqual(self.pool.snapshot()["queued"], 1)

    def test_invalid_budgets_are_rejected(self):
        for value in (0, -1, True, 1.5, float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Cost(value)
        with self.assertRaises(ValueError):
            Capacity(100, 2, active=1, heavy=2)
        with self.assertRaises(ValueError):
            self.pool.acquire(Cost(1), deadline=float("inf"))

    def test_context_manager_releases_even_on_failure(self):
        with self.assertRaises(RuntimeError):
            with self.acquire():
                raise RuntimeError("synthetic")
        self.assertEqual(self.pool.snapshot()["active"], 0)

    def test_double_release_is_safe(self):
        lease = self.acquire()
        lease.release()
        lease.release()
        self.assertEqual(self.pool.snapshot(), dict(active=0, heavy=0, memory_bytes=0, pids=0, queued=0))

    def test_impossible_cost_does_not_queue(self):
        for cost in (Cost(101), Cost(1, pids=4)):
            with self.assertRaisesRegex(AdmissionError, "cost_exceeds_capacity"):
                self.acquire(cost)
        self.assertEqual(self.pool.snapshot()["queued"], 0)

    def test_expired_and_cancelled_calls_do_not_acquire(self):
        with self.assertRaisesRegex(AdmissionError, "queue_timeout"):
            self.pool.acquire(Cost(1), deadline=time.monotonic() - 1)
        cancellation = threading.Event()
        cancellation.set()
        with self.assertRaisesRegex(AdmissionError, "cancelled"):
            self.acquire(cancellation=cancellation)
        self.assertEqual(self.pool.snapshot()["active"], 0)

    def test_heavy_operations_cannot_overlap(self):
        first = self.acquire(Cost(10, heavy=True))
        entered = threading.Event()

        def run():
            with self.acquire(Cost(10, heavy=True)):
                entered.set()

        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.wait_queued()
            self.assertFalse(entered.is_set())
        finally:
            first.release()
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertTrue(entered.is_set())
        self.assertEqual(self.pool.snapshot()["active"], 0)

    def test_cancelled_waiter_releases_queue_capacity(self):
        first = self.acquire(Cost(100))
        cancellation, errors = threading.Event(), []

        def wait():
            try:
                with self.acquire(cancellation=cancellation):
                    errors.append("unexpected_admission")
            except AdmissionError as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=wait)
        thread.start()
        try:
            self.wait_queued()
            with self.assertRaisesRegex(AdmissionError, "queue_full"):
                self.acquire()
            cancellation.set()
            thread.join(1)
            self.assertEqual(errors, ["cancelled"])
            self.assertEqual(self.pool.snapshot()["queued"], 0)
        finally:
            cancellation.set()
            first.release()
            thread.join(1)

    def test_memory_pid_and_active_limits_each_apply(self):
        for capacity, first_cost in ((Capacity(100, 3), Cost(100)),
                                     (Capacity(100, 1), Cost(1)),
                                     (Capacity(100, 3, active=1), Cost(1))):
            pool = Admission(capacity)
            with pool.acquire(first_cost, deadline=time.monotonic() + 1):
                with self.assertRaisesRegex(AdmissionError, "queue_timeout"):
                    pool.acquire(Cost(1), deadline=time.monotonic() + 0.01)
            self.assertEqual(pool.snapshot()["queued"], 0)


if __name__ == "__main__":
    unittest.main()
