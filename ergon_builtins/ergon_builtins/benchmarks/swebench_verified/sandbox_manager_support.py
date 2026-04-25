"""Small helpers for SWE-Bench sandbox setup.

Formerly ``_payload_to_swebench_row`` lived on the deleted
``BenchmarkAdapter`` subclass; it belongs to the sandbox manager (and the
evaluation criterion) now.
"""

from typing import Any

from pydantic import BaseModel

from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload


def payload_to_swebench_row(
    payload: SWEBenchTaskPayload | BaseModel | dict[str, Any],  # slopcop: ignore[no-typing-any]
) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    """Translate a ``SWEBenchTaskPayload`` into a harness row.

    The harness expects UPPER_CASE keys for ``FAIL_TO_PASS`` / ``PASS_TO_PASS``
    and a ``patch`` field (we always pass the empty string since the gold
    patch must never reach the worker).
    """
    if isinstance(payload, BaseModel):
        payload = SWEBenchTaskPayload.model_validate(payload.model_dump())
    else:
        payload = SWEBenchTaskPayload.model_validate(payload)
    return {
        "instance_id": payload.instance_id,
        "repo": payload.repo,
        "base_commit": payload.base_commit,
        "version": payload.version,
        "problem_statement": payload.problem_statement,
        "hints_text": payload.hints_text,
        "FAIL_TO_PASS": payload.fail_to_pass,
        "PASS_TO_PASS": payload.pass_to_pass,
        "environment_setup_commit": payload.environment_setup_commit,
        "test_patch": payload.test_patch,
        "patch": "",
    }
