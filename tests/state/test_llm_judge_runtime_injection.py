"""Tests for LLM-judge runtime injection via EvaluationContext.

Verifies:
- EvaluationContext accepts an optional runtime field
- LLMJudgeCriterion.evaluate() reads context.runtime.call_llm_judge()
- LLMJudgeCriterion.evaluate() raises when runtime is None
- Legacy criteria that ignore context.runtime keep working
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult, WorkerOutput
from ergon_core.api.task_types import BenchmarkTask


def _make_eval_context(
    *,
    runtime: object = None,
) -> EvaluationContext:
    return EvaluationContext(
        run_id=uuid4(),
        task=BenchmarkTask(
            task_key="test",
            instance_key="default",
            description="What is quantum computing?",
        ),
        worker_result=WorkerOutput(
            output="Quantum computing uses qubits...",
        ),
        runtime=runtime,
    )


class TestEvaluationContextRuntime:
    def test_runtime_defaults_to_none(self):
        ctx = _make_eval_context()
        assert ctx.runtime is None

    def test_runtime_can_be_set(self):
        fake_runtime = object()
        ctx = _make_eval_context(runtime=fake_runtime)
        assert ctx.runtime is fake_runtime

    def test_context_is_frozen(self):
        ctx = _make_eval_context()
        with pytest.raises(Exception):  # slopcop: ignore[no-broad-except]
            ctx.run_id = uuid4()  # type: ignore[misc]


class TestLLMJudgeCriterionWithRuntime:
    @pytest.mark.asyncio
    async def test_evaluate_calls_runtime(self):
        from ergon_builtins.evaluators.criteria.llm_judge import (
            LLMJudgeCriterion,
            _JudgeVerdict,
        )

        fake_runtime = AsyncMock()
        fake_runtime.call_llm_judge = AsyncMock(
            return_value=_JudgeVerdict(
                reasoning="Good coverage of the topic.",
                passed=True,
            ),
        )

        criterion = LLMJudgeCriterion(
            name="test-criterion",
            prompt_template="Evaluate whether the report covers the topic.",
            weight=1.0,
            max_score=1.0,
        )

        ctx = _make_eval_context(runtime=fake_runtime)
        result = await criterion.evaluate(ctx)

        assert result.passed is True
        assert result.score == 1.0
        assert result.feedback == "Good coverage of the topic."
        fake_runtime.call_llm_judge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evaluate_failing_verdict(self):
        from ergon_builtins.evaluators.criteria.llm_judge import (
            LLMJudgeCriterion,
            _JudgeVerdict,
        )

        fake_runtime = AsyncMock()
        fake_runtime.call_llm_judge = AsyncMock(
            return_value=_JudgeVerdict(
                reasoning="Report lacks sources.",
                passed=False,
            ),
        )

        criterion = LLMJudgeCriterion(
            name="test-criterion",
            prompt_template="Evaluate the report.",
            weight=2.0,
            max_score=2.0,
        )

        ctx = _make_eval_context(runtime=fake_runtime)
        result = await criterion.evaluate(ctx)

        assert result.passed is False
        assert result.score == 0.0
        assert result.feedback == "Report lacks sources."

    @pytest.mark.asyncio
    async def test_evaluate_raises_without_runtime(self):
        from ergon_builtins.evaluators.criteria.llm_judge import (
            LLMJudgeCriterion,
        )

        criterion = LLMJudgeCriterion(
            name="test-criterion",
            prompt_template="Evaluate the report.",
        )

        ctx = _make_eval_context(runtime=None)
        with pytest.raises(
            RuntimeError,
            match="LLMJudgeCriterion requires EvaluationContext.runtime",
        ):
            await criterion.evaluate(ctx)


class TestLegacyCriterionIgnoresRuntime:
    """Legacy criteria that don't use context.runtime should keep working."""

    @pytest.mark.asyncio
    async def test_criterion_with_runtime_present_but_unused(self):
        """A criterion that doesn't touch runtime still works fine."""
        from ergon_core.api.criterion import Criterion

        class _SimpleCriterion(Criterion):
            type_slug = "simple-test"

            async def evaluate(self, context: EvaluationContext) -> CriterionResult:
                return CriterionResult(
                    name=self.name,
                    score=1.0,
                    passed=True,
                    weight=self.weight,
                    feedback="Always passes",
                )

        criterion = _SimpleCriterion(name="simple")
        fake_runtime = AsyncMock()
        ctx = _make_eval_context(runtime=fake_runtime)
        result = await criterion.evaluate(ctx)

        assert result.passed is True
        assert result.score == 1.0
        # Runtime was never called
        fake_runtime.call_llm_judge.assert_not_awaited()
