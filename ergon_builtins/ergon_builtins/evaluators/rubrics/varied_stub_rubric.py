"""Test fixture: rubric with random scores for GRPO gradient testing."""

from ergon_core.api import Rubric

from ergon_builtins.evaluators.criteria.varied_stub_criterion import VariedStubCriterion


class VariedStubRubric(Rubric):
    """Rubric that returns random scores. Produces reward variance for GRPO."""

    type_slug = "varied-stub-rubric"

    def __init__(self, *, name: str = "varied-stub-rubric") -> None:
        super().__init__(name=name, criteria=[VariedStubCriterion()])
