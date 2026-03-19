"""Deterministic PG-state tests for ResearchRubrics."""

import asyncio

import pytest

from h_arcane.core.settings import settings
from tests.deterministic.cases import researchrubrics_search_synthesize_report_case
from tests.deterministic.runtime import run_deterministic_case
from tests.utils.assertions import (
    assert_researchrubrics_search_synthesize_case,
    load_run_state_snapshot,
)


@pytest.mark.e2e
@pytest.mark.timeout(900)
def test_researchrubrics_search_synthesize_case_persists_expected_state(clean_db):
    if not settings.e2b_api_key:
        pytest.skip("E2B_API_KEY is required for deterministic ResearchRubrics state tests")

    result = asyncio.run(run_deterministic_case(researchrubrics_search_synthesize_report_case()))
    snapshot = load_run_state_snapshot(result.run_id)

    assert_researchrubrics_search_synthesize_case(snapshot)
    span_names = [span.span_name for span in result.transcript.spans]
    assert "sandbox.setup" in span_names
    assert "worker.execute" in span_names
    assert "persist.outputs" in span_names
