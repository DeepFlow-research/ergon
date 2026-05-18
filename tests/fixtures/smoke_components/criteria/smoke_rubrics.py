"""Single-criterion ``Rubric`` wrappers so smoke criteria can be
registered as evaluators.

The composition layer (``ergon_cli.composition.build_experiment``) looks
up ``EVALUATORS[evaluator_slug]`` and instantiates the class as
``cls(name="evaluator")``.  Downstream code calls ``.criteria_for(task)``
and ``.aggregate_task(task, results)`` on the instance — methods that
live on ``Evaluator`` / ``Rubric``, not on the bare ``Criterion`` ABC.

Each smoke run needs exactly one criterion (the env's
``{env}-smoke-criterion``), so the simplest evaluator wrapper is a
``Rubric`` subclass that hardcodes a single-element criteria list.  We
reuse the ``{env}-smoke-criterion`` slug on the rubric so the CLI arg
``--evaluator {env}-smoke-criterion`` resolves directly.
"""

from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import Field, model_validator

from ergon_core.api.criterion import Criterion
from ergon_core.api.rubric import Rubric
from tests.fixtures.smoke_components.criteria.minif2f_smoke import MiniF2FSmokeCriterion
from tests.fixtures.smoke_components.criteria.researchrubrics_smoke import (
    ResearchRubricsSmokeCriterion,
)
from tests.fixtures.smoke_components.criteria.swebench_smoke import SweBenchSmokeCriterion


class ResearchRubricsSmokeRubric(Rubric):
    """Evaluator wrapping the researchrubrics smoke criterion.

    PR 10b: migrated from custom ``__init__`` to pure-Pydantic
    ``Field(default_factory=tuple, exclude=True)`` + ``@model_validator``
    so the rubric round-trips through ``Evaluator.from_definition`` (the
    object-bound code path used by ``ResearchRubricsSmokeTask.evaluators``).
    Mirrors the PR 10a SWE-Bench smoke rubric migration.
    """

    type_slug: ClassVar[str] = "researchrubrics-smoke-criterion"
    name: str = "researchrubrics-smoke-criterion"
    criteria: tuple[Criterion, ...] = Field(default_factory=tuple, exclude=True)

    @model_validator(mode="after")
    def _build_criterion(self) -> "ResearchRubricsSmokeRubric":
        if not self.criteria:
            self.criteria = (ResearchRubricsSmokeCriterion(slug="researchrubrics-smoke"),)
        return self


class MiniF2FSmokeRubric(Rubric):
    """Evaluator wrapping the minif2f smoke criterion."""

    type_slug: ClassVar[str] = "minif2f-smoke-criterion"

    def __init__(
        self,
        *,
        name: str,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name,
            criteria=(MiniF2FSmokeCriterion(slug="minif2f-smoke"),),
            metadata=dict(metadata) if metadata else {},
        )


class SweBenchSmokeRubric(Rubric):
    """Evaluator wrapping the swebench smoke criterion.

    PR 10a: migrated from custom ``__init__`` to pure-Pydantic
    ``Field(default_factory=tuple, exclude=True)`` + ``@model_validator``
    so the rubric round-trips through ``Evaluator.from_definition`` (the
    object-bound code path used by ``SweBenchSmokeTask.evaluators``).
    See ``ergon_builtins/benchmarks/minif2f/rubric.py`` for the exemplar.
    """

    type_slug: ClassVar[str] = "swebench-smoke-criterion"
    name: str = "swebench-smoke-criterion"
    criteria: tuple[Criterion, ...] = Field(default_factory=tuple, exclude=True)

    @model_validator(mode="after")
    def _build_criterion(self) -> "SweBenchSmokeRubric":
        if not self.criteria:
            self.criteria = (SweBenchSmokeCriterion(slug="swebench-smoke"),)
        return self
