"""Sandbox setup honors explicit sandbox slugs."""

from uuid import uuid4

from ergon_core.core.application.jobs.sandbox_setup import _sandbox_manager_slug
from ergon_core.core.infrastructure.inngest.contracts import SandboxSetupRequest


def test_sandbox_setup_prefers_explicit_sandbox_slug() -> None:
    payload = SandboxSetupRequest(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        benchmark_type="benchmark-slug",
        sandbox_slug="sandbox-slug",
    )

    assert _sandbox_manager_slug(payload) == "sandbox-slug"


def test_sandbox_setup_falls_back_to_benchmark_type() -> None:
    payload = SandboxSetupRequest(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        benchmark_type="benchmark-slug",
    )

    assert _sandbox_manager_slug(payload) == "benchmark-slug"
