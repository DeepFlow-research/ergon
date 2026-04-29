from types import SimpleNamespace

from ergon_core.core.application.evaluation.scoring import aggregate_evaluation_scores


def test_aggregate_evaluation_scores_counts_all_evaluators_and_averages_scored_rows() -> None:
    summary = aggregate_evaluation_scores(
        [
            SimpleNamespace(score=2.0),
            SimpleNamespace(score=None),
            SimpleNamespace(score=4.0),
        ]
    )

    assert summary.final_score == 6.0
    assert summary.normalized_score == 3.0
    assert summary.evaluators_count == 3


def test_aggregate_evaluation_scores_returns_none_scores_when_nothing_scored() -> None:
    summary = aggregate_evaluation_scores([SimpleNamespace(score=None)])

    assert summary.final_score is None
    assert summary.normalized_score is None
    assert summary.evaluators_count == 1
