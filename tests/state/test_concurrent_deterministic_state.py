"""Concurrent deterministic benchmark state execution tests."""

import asyncio

import pytest

from h_arcane.core.settings import settings
from tests.deterministic.cases import (
    minif2f_two_pass_proof_case,
    researchrubrics_search_synthesize_report_case,
)
from tests.deterministic.runtime import run_deterministic_cases_concurrently
from tests.utils.assertions import (
    assert_minif2f_two_pass_case,
    assert_researchrubrics_search_synthesize_case,
    load_run_state_snapshot,
)


@pytest.mark.e2e
@pytest.mark.timeout(2400)
def test_distinct_deterministic_cases_can_run_concurrently(clean_db):
    if not settings.e2b_api_key:
        pytest.skip("E2B_API_KEY is required for deterministic concurrent state tests")

    minif2f_case = minif2f_two_pass_proof_case()
    research_case = researchrubrics_search_synthesize_report_case()

    results = asyncio.run(
        run_deterministic_cases_concurrently([minif2f_case, research_case])
    )

    assert len(results) == 2
    assert len({result.run_id for result in results}) == 2

    snapshots = {snapshot.run.id: snapshot for snapshot in map(lambda r: load_run_state_snapshot(r.run_id), results)}

    minif2f_snapshot = next(
        snapshot
        for snapshot in snapshots.values()
        if snapshot.experiment.benchmark_name.value == "minif2f"
    )
    research_snapshot = next(
        snapshot
        for snapshot in snapshots.values()
        if snapshot.experiment.benchmark_name.value == "researchrubrics"
    )

    assert_minif2f_two_pass_case(minif2f_snapshot)
    assert_researchrubrics_search_synthesize_case(research_snapshot)
