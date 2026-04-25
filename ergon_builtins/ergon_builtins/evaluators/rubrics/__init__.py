"""Built-in evaluator rubrics.

Test-only stub rubrics (``StubRubric``, ``VariedStubRubric``) were
retired alongside the canonical-smoke refactor — smoke criteria live
under ``tests/e2e/_fixtures/criteria/`` and do not use rubric
composition.
"""

from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric

__all__ = ["SWEBenchRubric"]
