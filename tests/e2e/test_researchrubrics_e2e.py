"""
tests/e2e/test_researchrubrics_e2e.py

End-to-end tests for ResearchRubrics benchmark.

Uses session-scoped dispatch - all runs are triggered at session start.
This test just waits for ResearchRubrics runs to complete and asserts on results.
"""

import asyncio
import pytest

from sqlmodel import Session

from h_arcane.core._internal.db.models import Experiment
from tests.conftest import wait_for_run_completion, AllDispatchedRuns
from tests.utils.assertions import assert_run_completed_and_print_failures


@pytest.mark.e2e
class TestResearchRubricsE2E:
    """
    Wait for ResearchRubrics runs (already dispatched) and assert on results.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    async def test_researchrubrics_batch(
        self, all_dispatched_runs: AllDispatchedRuns, db_session: Session
    ):
        """
        Wait for all ResearchRubrics runs to complete and assert.

        Runs were already dispatched by session fixture.
        """
        dispatched = all_dispatched_runs.researchrubrics

        if not dispatched:
            pytest.skip("No ResearchRubrics experiments dispatched")

        print(f"\n⏳ Waiting for {len(dispatched)} ResearchRubrics runs...")

        # Wait for all completions in parallel
        wait_tasks = [
            wait_for_run_completion(d.experiment.id, timeout_seconds=300) for d in dispatched
        ]
        runs = await asyncio.gather(*wait_tasks, return_exceptions=True)

        # Assert on all results
        print(f"\n📊 Results for {len(runs)} ResearchRubrics runs:")
        failures: list[tuple[Experiment, Exception]] = []
        for i, (d, run_result) in enumerate(zip(dispatched, runs)):
            exp = d.experiment
            if isinstance(run_result, BaseException):
                print(f"  ❌ Task {i} ({exp.task_id}): {run_result}")
                failures.append(
                    (
                        exp,
                        run_result
                        if isinstance(run_result, Exception)
                        else Exception(str(run_result)),
                    )
                )
            else:
                try:
                    assert_run_completed_and_print_failures(run_result, db_session)
                    print(f"  ✅ Task {i} ({exp.task_id}): PASSED")
                except AssertionError as e:
                    print(f"  ❌ Task {i} ({exp.task_id}): {e}")
                    failures.append((exp, e))

        assert len(failures) == 0, f"{len(failures)}/{len(runs)} ResearchRubrics tasks failed"
