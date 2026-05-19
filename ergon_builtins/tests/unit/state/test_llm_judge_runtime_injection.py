"""Tests for LLM-judge criteria using provider-owned structured judge calls.

Verifies:
- LLMJudgeCriterion.evaluate() does not rely on CriterionRuntime LLM policy
- Legacy criteria keep working with the final object-bound context shape
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.worker import WorkerOutput
from ergon_core.test_support.task_factory import task_with_id


def _make_eval_context() -> CriterionContext:
    return CriterionContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=task_with_id(
            uuid4(),
            task_slug="test",
            instance_key="default",
            description="What is quantum computing?",
        ),
        worker_result=WorkerOutput(
            output="Quantum computing uses qubits...",
        ),
    )


class TestCriterionContextRuntime:
    def test_runtime_field_is_removed(self):
        ctx = _make_eval_context()
        assert "runtime" not in CriterionContext.model_fields
        assert not hasattr(ctx, "runtime")

    def test_context_is_frozen(self):
        ctx = _make_eval_context()
        with pytest.raises(Exception):  # slopcop: ignore[no-broad-except]
            ctx.run_id = uuid4()  # type: ignore[misc]


class TestLLMJudgeCriterionWithRuntime:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "passed,expected_score,reasoning",
        [
            (True, 1.0, "Good coverage of the topic."),
            (False, 0.0, "Report lacks sources."),
        ],
    )
    async def test_evaluate_verdict(self, monkeypatch, passed, expected_score, reasoning):
        from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import (
            LLMJudgeCriterion,
            _JudgeVerdict,
        )

        judge = AsyncMock(return_value=_JudgeVerdict(reasoning=reasoning, passed=passed))
        monkeypatch.setattr(
            "ergon_builtins.benchmarks.gdpeval.criteria.llm_judge.call_structured_judge",
            judge,
        )

        criterion = LLMJudgeCriterion(
            slug="test-criterion",
            prompt_template="Evaluate whether the report covers the topic.",
            weight=1.0,
            max_score=1.0,
        )

        ctx = _make_eval_context()
        result = await criterion.evaluate(ctx)

        assert result.passed is passed
        assert result.score == expected_score
        assert result.feedback == reasoning
        judge.assert_awaited_once()


class TestLegacyCriterionIgnoresRuntime:
    """Legacy criteria that don't use context.runtime should keep working."""

    @pytest.mark.asyncio
    async def test_criterion_with_final_context_shape(self):
        """A criterion that only uses public context fields still works fine."""
        from ergon_core.api.criterion import Criterion

        class _SimpleCriterion(Criterion):
            type_slug = "simple-test"

            async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
                return CriterionOutcome(
                    slug=self.slug,
                    name=self.slug,
                    score=1.0,
                    passed=True,
                    weight=self.weight,
                    feedback="Always passes",
                )

        criterion = _SimpleCriterion(slug="simple")
        ctx = _make_eval_context()
        result = await criterion.evaluate(ctx)

        assert result.passed is True
        assert result.score == 1.0
