"""Registry includes the shared canonical-smoke entries after PR 1.

The env smoke rubrics wrap env-specific SmokeCriterionBase subclasses --
they are registered under "<env>-smoke-rubric" slugs in EVALUATORS.
"""

from uuid import uuid4

from ergon_builtins.benchmarks.minif2f.smoke_rubric import MiniF2FSmokeRubric
from ergon_builtins.benchmarks.researchrubrics.smoke_rubric import (
    ResearchRubricsSmokeRubric,
)
from ergon_builtins.benchmarks.swebench_verified.smoke_rubric import (
    SweBenchSmokeRubric,
)
from ergon_builtins.evaluators.criteria.smoke_criterion import (
    ResearchRubricsSmokeCriterion,
)
from ergon_builtins.registry_core import EVALUATORS, WORKERS
from ergon_builtins.workers.stubs.canonical_smoke_worker import CanonicalSmokeWorker


def test_canonical_smoke_worker_registered() -> None:
    """Post-RFC 2026-04-22: ``_plain`` was dropped (base ``Worker.__init__``
    now requires ``task_id`` / ``sandbox_id``), so the registry entry is
    the bare class. Verify construction still works with registry kwargs."""
    factory = WORKERS["canonical-smoke"]
    worker = factory(
        name="canonical-smoke",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-test",
    )
    assert isinstance(worker, CanonicalSmokeWorker)


def test_env_smoke_rubrics_registered() -> None:
    assert EVALUATORS["researchrubrics-smoke-rubric"] is ResearchRubricsSmokeRubric
    assert EVALUATORS["minif2f-smoke-rubric"] is MiniF2FSmokeRubric
    assert EVALUATORS["swebench-smoke-rubric"] is SweBenchSmokeRubric


def test_researchrubrics_smoke_rubric_wraps_new_criterion() -> None:
    """Regression guard: the in-place replacement actually swapped the criterion."""
    rubric = ResearchRubricsSmokeRubric()
    assert len(rubric.criteria) == 1
    assert isinstance(rubric.criteria[0], ResearchRubricsSmokeCriterion)
