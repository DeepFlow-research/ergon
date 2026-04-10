"""TEST FIXTURE ONLY. Do not use as a template for real rubrics.

Bundles a single StubCriterion. For smoke tests only.
"""

from ergon_core.api import Rubric

from ergon_builtins.evaluators.criteria.stub_criterion import StubCriterion


class StubRubric(Rubric):
    type_slug = "stub-rubric"

    def __init__(self, *, name: str = "stub-rubric") -> None:
        super().__init__(name=name, criteria=[StubCriterion()])
