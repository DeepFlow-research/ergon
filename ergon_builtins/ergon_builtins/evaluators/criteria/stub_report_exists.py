"""Stub criterion: checks that final_report.md exists as a RunResource.

Reads the RunResource rows for the current task execution and asserts that
a ``kind=REPORT`` row exists whose blob content is valid UTF-8 markdown
containing the expected ``# Findings`` and ``## Sources`` section headers.

Used by the ``researchrubrics-smoke`` benchmark for CI / E2B smoke tests.
"""

import hashlib
from pathlib import Path
from typing import ClassVar

from ergon_core.api import Criterion, CriterionResult, EvaluationContext
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.telemetry.models import RunResourceKind


class StubReportExistsCriterion(Criterion):
    """Checks that final_report.md exists as a RunResource with expected fields."""

    type_slug: ClassVar[str] = "stub-report-exists"

    REQUIRED_SECTIONS: ClassVar[tuple[str, ...]] = (
        "# Findings",
        "## Sources",
    )

    def __init__(
        self,
        *,
        name: str = "stub-report-exists",
        weight: float = 1.0,
    ) -> None:
        super().__init__(name=name, weight=weight)

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        # Look up RunResource rows for this execution via metadata.
        execution_id = context.metadata.get("execution_id")
        if execution_id is None:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="No execution_id in EvaluationContext.metadata",
            )

        resources = queries.resources.list_latest_for_execution(execution_id)
        report_rows = [r for r in resources if r.kind == RunResourceKind.REPORT.value]

        if not report_rows:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=(f"No RunResource(kind=REPORT) found for execution {execution_id}"),
            )

        report = report_rows[0]

        # Verify the blob exists on disk and is valid UTF-8 markdown.
        blob_path = Path(report.file_path)
        if not blob_path.exists():
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"Blob file missing at {report.file_path}",
            )

        try:
            content = blob_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"Blob at {report.file_path} is not valid UTF-8",
            )

        # Check required section headers are present.
        missing = [s for s in self.REQUIRED_SECTIONS if s not in content]
        if missing:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"Missing sections in report: {missing}",
            )

        # Verify content_hash matches SHA-256 of blob bytes.
        if report.content_hash is not None:
            actual_hash = hashlib.sha256(blob_path.read_bytes()).hexdigest()
            if actual_hash != report.content_hash:
                return CriterionResult(
                    name=self.name,
                    score=0.0,
                    passed=False,
                    weight=self.weight,
                    feedback=(
                        f"content_hash mismatch: row={report.content_hash}, blob={actual_hash}"
                    ),
                )

        return CriterionResult(
            name=self.name,
            score=1.0,
            passed=True,
            weight=self.weight,
            feedback=(
                f"Report found: {report.name}, "
                f"size={report.size_bytes}B, "
                f"hash={report.content_hash}"
            ),
        )
