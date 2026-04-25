"""Evaluator criterion that runs the SWE-Bench test harness.

``SWEBenchTestCriterion`` reuses the task's existing sandbox (via the
``CriterionRuntime`` DI surface), re-runs the repo setup + install script,
applies the gold ``test_patch`` followed by the agent's patch, and then
executes the official ``spec.eval_script``.  The captured stdout/stderr is
written to a local tempfile and fed to
:func:`swebench.harness.grading.get_eval_report` which parses
``FAIL_TO_PASS`` / ``PASS_TO_PASS`` outcomes and decides whether the
instance is ``resolved``.

Empty/whitespace patches short-circuit to score 0 immediately (no sandbox
access required).
"""

import logging
import shlex
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion_runtime import CriterionRuntime
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager_support import (
    payload_to_swebench_row as _payload_to_swebench_row,
)
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload

logger = logging.getLogger(__name__)

WORKDIR = "/workspace/repo"
EVAL_TIMEOUT_SEC = 1800
APPLY_TIMEOUT_SEC = 120
PATCH_EXTRACT_TIMEOUT_SEC = 120


async def _extract_patch_via_runtime(context: EvaluationContext) -> str:
    """Compute ``git add -A && git diff HEAD`` via the criterion runtime.

    The criterion owns patch extraction; the sandbox working tree is the
    only reliable source of truth (nothing crosses the durable Inngest
    ``worker_execute`` boundary).
    """
    if context.runtime is None:
        raise RuntimeError(
            "SWEBenchTestCriterion requires a CriterionRuntime for patch "
            "extraction; none was injected into EvaluationContext."
        )
    await context.runtime.ensure_sandbox()
    result = await context.runtime.run_command(
        f"cd {WORKDIR} && git add -A && git diff HEAD",
        timeout=PATCH_EXTRACT_TIMEOUT_SEC,
    )
    if result.exit_code != 0:
        return ""
    return "" if result.stdout is None else result.stdout


def make_test_spec(row: dict[str, Any]) -> Any:  # slopcop: ignore[no-typing-any]
    """Re-exported for test monkeypatching; lazy swebench import."""
    # reason: swebench is a heavy optional dep; import on first use.
    from swebench.harness.test_spec.test_spec import make_test_spec as _mk

    return _mk(row)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def get_eval_report(
    *,
    test_spec: Any,  # slopcop: ignore[no-typing-any]
    prediction: dict[str, str],
    test_log_path: str,
    include_tests_status: bool = True,
) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    """Re-exported for test monkeypatching; lazy swebench import."""
    # reason: swebench is a heavy optional dep; import on first use.
    from swebench.harness.grading import get_eval_report as _ger

    return _ger(
        test_spec=test_spec,
        prediction=prediction,
        test_log_path=test_log_path,
        include_tests_status=include_tests_status,
    )


def _grade_with_log(
    *,
    spec: Any,  # slopcop: ignore[no-typing-any]
    log: str,
    instance_id: str,
    patch_text: str,
) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    """Write ``log`` to a local tempfile and invoke ``get_eval_report``.

    The tempfile is always deleted, even if grading raises.  Separated
    from ``evaluate`` to avoid a nested ``try`` block.
    """
    with tempfile.NamedTemporaryFile(
        prefix="swebench-eval-", suffix=".log", delete=False, mode="w"
    ) as tmp:
        tmp.write(log)
        log_path = tmp.name

    try:
        return get_eval_report(
            test_spec=spec,
            prediction={
                "instance_id": instance_id,
                "model_name_or_path": "ergon",
                "model_patch": patch_text,
            },
            test_log_path=log_path,
            include_tests_status=True,
        )
    finally:
        Path(log_path).unlink(missing_ok=True)


class SWEBenchTestCriterion(Criterion):
    """Scores 1.0 iff the agent patch resolves FAIL_TO_PASS and doesn't break PASS_TO_PASS."""

    type_slug: ClassVar[str] = "swebench-test-resolution"

    def __init__(
        self,
        *,
        name: str = "swebench-test-resolution",
        weight: float = 1.0,
    ) -> None:
        super().__init__(name=name, weight=weight)

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        patch_text = await _extract_patch_via_runtime(context)
        if not patch_text.strip():
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="Empty patch — agent did not produce any edits.",
                metadata={},
            )

        payload = SWEBenchTaskPayload.model_validate(context.task.task_payload.model_dump())
        row = _payload_to_swebench_row(payload)
        spec = make_test_spec(row)

        # reason: RFC 2026-04-22 §3 — harness ops go through the
        # `CriterionRuntime` Protocol (`run_command`, `write_file`) so the
        # criterion doesn't reach past the DI surface to the concrete
        # `sandbox_manager` attribute. `_extract_patch_via_runtime` above
        # already called `ensure_sandbox`, so subsequent `run_command` /
        # `write_file` calls are guaranteed to hit a live sandbox.
        runtime = context.runtime
        if runtime is None:  # pragma: no cover — guarded above
            raise RuntimeError("runtime disappeared after patch extraction")

        return await self._run_and_grade(
            runtime=runtime, spec=spec, payload=payload, patch_text=patch_text
        )

    async def _run_and_grade(
        self,
        *,
        runtime: CriterionRuntime,
        spec: Any,  # slopcop: ignore[no-typing-any]
        payload: SWEBenchTaskPayload,
        patch_text: str,
    ) -> CriterionResult:
        # 1. install_repo_script: clone + checkout base_commit + install deps.
        r = await runtime.run_command(
            f"bash -c {shlex.quote(spec.install_repo_script)}",
            timeout=EVAL_TIMEOUT_SEC,
        )
        if r.exit_code != 0:
            detail = r.stdout if r.stdout is not None else r.stderr
            return _error_result(
                self.name,
                self.weight,
                "install_repo failed",
                # reason: both CommandResult fields are `str | None`, but
                # _error_result requires `str`. Fall back to empty string
                # so the error message is well-typed even when the sandbox
                # returns no output on failure.
                "" if detail is None else detail,
            )

        # 2. Apply test_patch then agent patch (order matters).
        test_patch = payload.test_patch
        try:
            if test_patch.strip():
                await _write_and_apply(runtime, "/tmp/test.patch", test_patch)
            await _write_and_apply(runtime, "/tmp/agent.patch", patch_text)
        except RuntimeError as exc:
            return _error_result(self.name, self.weight, "git apply failed", str(exc))

        # 3. Run eval script with stderr merged so the log has everything.
        r = await runtime.run_command(
            f"bash -c {shlex.quote(spec.eval_script)} 2>&1",
            timeout=EVAL_TIMEOUT_SEC,
        )
        log = "" if r.stdout is None else r.stdout

        # 4. Grade: persist log locally, hand path to swebench harness.
        report = _grade_with_log(
            spec=spec,
            log=log,
            instance_id=payload.instance_id,
            patch_text=patch_text,
        )
        entry = report.get(payload.instance_id, {}) if isinstance(report, dict) else {}
        resolved = bool(entry.get("resolved"))
        return CriterionResult(
            name=self.name,
            score=1.0 if resolved else 0.0,
            passed=resolved,
            weight=self.weight,
            feedback=_format_feedback(entry),
            metadata={"report": entry},
        )


async def _write_and_apply(
    runtime: CriterionRuntime,
    path: str,
    content: str,
) -> None:
    """Write ``content`` to ``path`` in the sandbox and ``git apply`` it.

    Falls back to ``--3way`` if the straight apply fails. Raises
    ``RuntimeError`` with tail of stdout when both attempts fail.
    """
    await runtime.write_file(path, content.encode())
    r = await runtime.run_command(
        f"cd {WORKDIR} && git apply --allow-empty --verbose {path}",
        timeout=APPLY_TIMEOUT_SEC,
    )
    if r.exit_code != 0:
        r = await runtime.run_command(
            f"cd {WORKDIR} && git apply --3way --verbose {path}",
            timeout=APPLY_TIMEOUT_SEC,
        )
    if r.exit_code != 0:
        stdout = "" if r.stdout is None else r.stdout
        raise RuntimeError(f"git apply {path} failed: {stdout[-800:]}")


def _error_result(name: str, weight: float, kind: str, detail: str) -> CriterionResult:
    return CriterionResult(
        name=name,
        score=0.0,
        passed=False,
        weight=weight,
        feedback=f"{kind}: {detail[-400:]}",
        metadata={"error": kind},
    )


def _format_feedback(entry: dict[str, Any]) -> str:  # slopcop: ignore[no-typing-any]
    tests_status = entry.get("tests_status", {}) if isinstance(entry, dict) else {}
    f2p = tests_status.get("FAIL_TO_PASS", {}) if isinstance(tests_status, dict) else {}
    p2p = tests_status.get("PASS_TO_PASS", {}) if isinstance(tests_status, dict) else {}
    return (
        f"FAIL_TO_PASS success={len(f2p.get('success', []))} "
        f"failure={len(f2p.get('failure', []))}; "
        f"PASS_TO_PASS success={len(p2p.get('success', []))} "
        f"failure={len(p2p.get('failure', []))}"
    )
