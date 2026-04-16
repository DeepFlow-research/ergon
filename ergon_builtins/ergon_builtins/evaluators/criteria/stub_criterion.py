"""TEST FIXTURE ONLY. Do not use as a template for real criteria.

Passes when worker reports success. For smoke tests only.

Emits a non-trivial ``CriterionResult`` (score, passed, feedback, metadata)
so dashboard panels have data to render beyond just "passed". For stub
workers that publish RunResource rows, ``metadata`` references the output
names so the EVALUATION panel can link to OUTPUTS.
"""

from ergon_core.api import Criterion, CriterionResult, EvaluationContext
from ergon_core.core.persistence.queries import queries


class StubCriterion(Criterion):
    type_slug = "stub-criterion"

    def __init__(self, *, name: str = "stub-criterion", weight: float = 1.0) -> None:
        self.name = name
        self.weight = weight

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        passed = context.worker_result.success
        score = 1.0 if passed else 0.0

        # Pull any resources the worker published so the feedback message and
        # metadata reference concrete artefacts instead of being empty.
        resource_names: list[str] = []
        resource_ids: list[str] = []
        try:
            rows = queries.resources.list_by_execution(context.execution_id)
            for row in rows:
                resource_names.append(row.name)
                resource_ids.append(str(row.id))
        except Exception:  # slopcop: ignore[no-broad-except]
            # Persistence lookup is best-effort; never fail evaluation over it.
            pass  # slopcop: ignore[no-pass-except]

        if passed:
            if resource_names:
                feedback = (
                    f"Stub criterion passed: worker produced {len(resource_names)} "
                    f"output(s) ({', '.join(resource_names)})."
                )
            else:
                feedback = "Stub criterion passed: worker reported success."
        else:
            feedback = "Stub criterion failed: worker reported failure."

        return CriterionResult(
            name=self.name,
            score=score,
            passed=passed,
            weight=self.weight,
            feedback=feedback,
            metadata={
                "worker_output_length": len(context.worker_result.output),
                "resource_count": len(resource_names),
                "resource_names": resource_names,
                "evaluated_resource_ids": resource_ids,
            },
        )
