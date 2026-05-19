from types import SimpleNamespace

from ergon_core.core.views.runs.service import _display_run_score
from ergon_core.core.persistence.shared.enums import RunStatus


def test_display_run_score_uses_normalized_score_for_multi_evaluator_runs() -> None:
    score_summary = SimpleNamespace(final_score=2.0, normalized_score=1.0)

    assert _display_run_score(score_summary, RunStatus.COMPLETED) == 1.0


def test_display_run_score_does_not_fallback_to_raw_total_score() -> None:
    score_summary = SimpleNamespace(final_score=1.0, normalized_score=None)

    assert _display_run_score(score_summary, RunStatus.COMPLETED) is None


def test_display_run_score_hides_scores_for_failed_runs() -> None:
    score_summary = SimpleNamespace(final_score=2.0, normalized_score=1.0)

    assert _display_run_score(score_summary, RunStatus.FAILED) is None
