import asyncio
import unittest

from agent_ext.retry_policy import (
    Failure,
    FailureKind,
    Operation,
    RetryAction,
    RetryLimits,
    WaitOutcome,
    retry_decision,
    wait_for_retry,
)


class RetryPolicyTests(unittest.TestCase):
    def decide(self, kind, operation=Operation.READ, **kwargs):
        return retry_decision(Failure(kind, operation, **kwargs), remaining_seconds=100)

    def test_authentication_and_configuration_block_unchanged_subsystem(self):
        for kind in (FailureKind.AUTHENTICATION, FailureKind.CONFIGURATION):
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.decide(
                        kind, subsystem="model", configuration_revision="v1"
                    ).action,
                    RetryAction.BLOCK_SUBSYSTEM,
                )

    def test_transience_requires_documented_safe_operation(self):
        self.assertEqual(self.decide(FailureKind.TRANSIENT).action, RetryAction.DEFER)
        self.assertEqual(
            self.decide(
                FailureKind.TRANSIENT, Operation.TOOL, documented_transient=True
            ).action,
            RetryAction.DEFER,
        )
        self.assertEqual(
            self.decide(FailureKind.TRANSIENT, documented_transient=True).action,
            RetryAction.RETRY,
        )

    def test_rate_limits_have_finite_backoff_and_respect_retry_after(self):
        failure = Failure(
            FailureKind.RATE_LIMIT,
            Operation.MODEL,
            documented_transient=True,
            retry_after=6,
        )
        first = retry_decision(failure, remaining_seconds=30)
        self.assertEqual(first.delay_seconds, 6)
        second = retry_decision(failure, transient_retries=1, remaining_seconds=30)
        self.assertEqual(second.delay_seconds, 6)
        self.assertEqual(
            retry_decision(failure, transient_retries=2, remaining_seconds=30).action,
            RetryAction.DEFER,
        )

    def test_actual_retry_after_is_never_truncated_to_retry_earlier(self):
        failure = Failure(
            FailureKind.RATE_LIMIT,
            Operation.MODEL,
            documented_transient=True,
            retry_after=50,
        )
        self.assertEqual(
            retry_decision(failure, remaining_seconds=100).delay_seconds, 50
        )
        for remaining in (0, 49, 50):
            self.assertEqual(
                retry_decision(failure, remaining_seconds=remaining).action,
                RetryAction.DEFER,
            )

    def test_adapter_owned_retries_are_not_nested(self):
        decision = self.decide(
            FailureKind.TRANSIENT, documented_transient=True, adapter_retried=True
        )
        self.assertEqual(
            (decision.action, decision.reason),
            (RetryAction.DEFER, "adapter_already_owns_retries"),
        )

    def test_repair_allowance_is_small_and_finite(self):
        failure = Failure(FailureKind.MALFORMED_REQUEST, Operation.TOOL)
        self.assertEqual(
            retry_decision(failure, remaining_seconds=10).action, RetryAction.REPAIR
        )
        self.assertEqual(
            retry_decision(failure, repairs=1, remaining_seconds=10).action,
            RetryAction.CHANGE_APPROACH,
        )

    def test_expensive_failures_require_a_different_experiment(self):
        for kind in (
            FailureKind.TOOL_TIMEOUT,
            FailureKind.TOOL_OOM,
            FailureKind.NO_PROGRESS,
        ):
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.decide(kind, Operation.TOOL).action,
                    RetryAction.CHANGE_APPROACH,
                )

    def test_submission_and_instance_mutations_never_use_generic_retry(self):
        for operation in (Operation.SUBMISSION, Operation.INSTANCE_MUTATION):
            for kind in FailureKind:
                with self.subTest(operation=operation, kind=kind):
                    failure = Failure(
                        kind,
                        operation,
                        documented_transient=True,
                        retry_after=1,
                        subsystem="board",
                        configuration_revision="v1",
                    )
                    self.assertNotIn(
                        retry_decision(failure, remaining_seconds=100).action,
                        {RetryAction.RETRY, RetryAction.REPAIR},
                    )

    def test_ambiguous_submission_requires_reconciliation_even_without_budget(self):
        failure = Failure(FailureKind.AMBIGUOUS_SUBMISSION, Operation.SUBMISSION)
        self.assertEqual(
            retry_decision(failure, remaining_seconds=0).action, RetryAction.RECONCILE
        )

    def test_stale_instance_wrong_candidate_and_refusal_have_distinct_routes(self):
        self.assertEqual(
            self.decide(FailureKind.STALE_INSTANCE).action, RetryAction.REQUALIFY
        )
        self.assertEqual(
            self.decide(FailureKind.WRONG_CANDIDATE, Operation.SUBMISSION).action,
            RetryAction.RECORD_WRONG,
        )
        self.assertEqual(
            self.decide(FailureKind.SAFETY_REFUSAL, Operation.MODEL).action,
            RetryAction.STOP_OPERATION,
        )

    def test_unknown_failure_defers_instead_of_guessing(self):
        self.assertEqual(self.decide(FailureKind.UNKNOWN).action, RetryAction.DEFER)

    def test_invalid_guidance_and_limits_fail_before_a_retry(self):
        for value in (True, -1, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Failure(FailureKind.RATE_LIMIT, Operation.MODEL, retry_after=value)
        with self.assertRaises(ValueError):
            Failure(FailureKind.AUTHENTICATION, Operation.MODEL)
        with self.assertRaises(ValueError):
            RetryLimits(max_transient_retries=-1)
        with self.assertRaises(ValueError):
            retry_decision(
                Failure(FailureKind.TRANSIENT, Operation.READ),
                transient_retries=-1,
                remaining_seconds=10,
            )


class RetryWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_without_transport_work(self):
        outcome = await wait_for_retry(
            0, cancellation=asyncio.Event(), remaining_seconds=1
        )
        self.assertEqual(outcome, WaitOutcome.READY)

    async def test_preexisting_cancellation_wins(self):
        cancellation = asyncio.Event()
        cancellation.set()
        self.assertEqual(
            await wait_for_retry(100, cancellation=cancellation, remaining_seconds=0),
            WaitOutcome.CANCELLED,
        )

    async def test_cancellation_during_wait_drains_children(self):
        cancellation = asyncio.Event()
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(
            wait_for_retry(100, cancellation=cancellation, remaining_seconds=200)
        )
        await asyncio.sleep(0)
        cancellation.set()
        self.assertEqual(await asyncio.wait_for(task, 1), WaitOutcome.CANCELLED)
        self.assertEqual(set(asyncio.all_tasks()), before)

    async def test_deadline_during_wait_is_not_a_retry(self):
        self.assertEqual(
            await wait_for_retry(
                100, cancellation=asyncio.Event(), remaining_seconds=0.001
            ),
            WaitOutcome.DEADLINE,
        )

    async def test_caller_task_cancellation_propagates_and_drains_children(self):
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(
            wait_for_retry(100, cancellation=asyncio.Event(), remaining_seconds=200)
        )
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(set(asyncio.all_tasks()), before)


if __name__ == "__main__":
    unittest.main()
