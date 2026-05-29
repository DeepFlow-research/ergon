"""Static posture contracts for canonical smoke fixtures."""

from copy import deepcopy

import pytest

from ergon_core.api import Task
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from tests.fixtures.smoke_components.benchmarks import (
    GDPEvalSmokeEnvironment,
    MiniF2FSmokeEnvironment,
    ResearchRubricsSmokeEnvironment,
    SweBenchSmokeEnvironment,
)
from tests.fixtures.smoke_components.smoke_base.constants import (
    ENV_PROBE_SLUG,
    EXPECTED_SUBTASK_SLUGS,
    EXPECTED_RESOURCE_HANDOFF,
    HANDOFF_RESOURCE_NAME,
    HANDOFF_VERIFY_SLUG,
    NESTED_LINE_SLUGS,
    SMOKE_THREAD_TOPIC,
    SOURCE_REVIEW_SLUG,
    SUBTASK_GRAPH,
)
from tests.fixtures.smoke_components.smoke_base.dynamic_tasks import (
    SmokeChildTaskSpec,
    smoke_task_from_spec,
)
from tests.fixtures.smoke_components.smoke_base.recursive import (
    NESTED_SUBTASK_GRAPH,
)


EXPECTED_ROOT_SANDBOX_TYPES = {
    ResearchRubricsSmokeEnvironment: (
        "ergon_builtins.benchmarks.researchrubrics.sandbox:ResearchE2BSandbox"
    ),
    MiniF2FSmokeEnvironment: "ergon_builtins.benchmarks.minif2f.sandbox:LeanSandbox",
    SweBenchSmokeEnvironment: (
        "ergon_builtins.benchmarks.swebench_verified.sandbox:SWEBenchSandbox"
    ),
    GDPEvalSmokeEnvironment: "ergon_builtins.benchmarks.gdpeval.sandbox:GDPEvalSandbox",
}

EXPECTED_ROOT_POSTURE = {
    ResearchRubricsSmokeEnvironment: (
        "smoke-001",
        "Review the supplied research notes and produce a concise evidence-backed report.",
    ),
    MiniF2FSmokeEnvironment: (
        "mathd_algebra_478",
        "Verify the supplied Lean theorem and record proof evidence.",
    ),
    SweBenchSmokeEnvironment: (
        "astropy__astropy-12907",
        "Inspect the Python issue and produce a minimal source patch with evidence.",
    ),
    GDPEvalSmokeEnvironment: (
        "gdpeval-smoke-001",
        "Process the reference documents and write a structured output bundle.",
    ),
}

EXPECTED_CHILD_SLUGS = (
    "source-review",
    "handoff-verify",
    "primary-artifact",
    "artifact-summary",
    "metadata-review",
    "environment-probe",
    "metadata-validate",
    "evidence-artifact",
    "completion-marker",
)

EXPECTED_CHILD_DEPENDENCIES = {
    "source-review": (),
    "handoff-verify": ("source-review",),
    "primary-artifact": ("source-review",),
    "artifact-summary": ("handoff-verify", "primary-artifact"),
    "metadata-review": (),
    "environment-probe": ("metadata-review",),
    "metadata-validate": ("environment-probe",),
    "evidence-artifact": (),
    "completion-marker": (),
}

EXPECTED_NESTED_SLUGS = ("nested-input-review", "nested-verification")


def _root_task(environment_cls: type) -> Task:
    environment = environment_cls()
    sample = next(iter(environment.iter_samples()))
    [task] = sample.tasks
    return task


def _sandbox_type(task: Task) -> str:
    return task.model_dump(mode="json")["sandbox"]["_type"]


def _child_task(parent_task: Task) -> Task:
    return smoke_task_from_spec(
        parent_task=parent_task,
        spec=SmokeChildTaskSpec(
            task_slug=TaskSlug("child"),
            description="child task",
            assigned_worker_slug=AssignedWorkerSlug("researchrubrics-smoke-leaf"),
            depends_on=[],
        ),
        model="openai:gpt-4o",
    )


def test_smoke_root_tasks_use_real_environment_sandboxes() -> None:
    for environment_cls, expected_type in EXPECTED_ROOT_SANDBOX_TYPES.items():
        task = _root_task(environment_cls)
        assert _sandbox_type(task) == expected_type
        assert "SmokePublicSandbox" not in expected_type
        assert "TestSandbox" not in expected_type


def test_smoke_dynamic_tasks_inherit_deepcopy_of_parent_sandbox() -> None:
    for environment_cls, expected_type in EXPECTED_ROOT_SANDBOX_TYPES.items():
        parent_task = _root_task(environment_cls)
        original_sandbox = parent_task.sandbox
        child_task = _child_task(parent_task)

        assert _sandbox_type(child_task) == expected_type
        assert child_task.sandbox == original_sandbox
        assert child_task.sandbox is not original_sandbox


def test_smoke_dynamic_task_requires_parent_sandbox() -> None:
    parent_task = deepcopy(_root_task(ResearchRubricsSmokeEnvironment))
    parent_task.sandbox = None

    with pytest.raises(ValueError, match="parent task must define a sandbox"):
        _child_task(parent_task)


def test_smoke_roots_have_semantic_slugs_and_descriptions() -> None:
    for environment_cls, (expected_slug, expected_description) in EXPECTED_ROOT_POSTURE.items():
        task = _root_task(environment_cls)
        assert task.task_slug == expected_slug
        assert task.description == expected_description


def test_smoke_child_topology_uses_semantic_slugs_and_descriptions() -> None:
    assert EXPECTED_SUBTASK_SLUGS == EXPECTED_CHILD_SLUGS

    graph_by_slug = {slug: (deps, description) for slug, deps, description in SUBTASK_GRAPH}
    assert tuple(graph_by_slug) == EXPECTED_CHILD_SLUGS

    for slug, expected_deps in EXPECTED_CHILD_DEPENDENCIES.items():
        deps, description = graph_by_slug[slug]
        assert deps == expected_deps
        assert description
        assert "Diamond" not in description
        assert "Line node" not in description


def test_smoke_nested_topology_uses_semantic_slugs() -> None:
    assert NESTED_LINE_SLUGS == EXPECTED_NESTED_SLUGS
    assert tuple(slug for slug, _deps, _description in NESTED_SUBTASK_GRAPH) == (
        EXPECTED_NESTED_SLUGS
    )
    assert NESTED_SUBTASK_GRAPH[1][1] == (EXPECTED_NESTED_SLUGS[0],)


def test_smoke_handoff_constants_point_to_semantic_tasks() -> None:
    assert EXPECTED_RESOURCE_HANDOFF.producer_slug == SOURCE_REVIEW_SLUG
    assert EXPECTED_RESOURCE_HANDOFF.consumer_slug == HANDOFF_VERIFY_SLUG
    assert EXPECTED_RESOURCE_HANDOFF.resource_name == HANDOFF_RESOURCE_NAME
    assert SMOKE_THREAD_TOPIC == "smoke-coordination"


def test_recursive_worker_routes_the_semantic_probe_node() -> None:
    from tests.fixtures.smoke_components.smoke_base.recursive import RecursiveSmokeWorkerMixin

    assert RecursiveSmokeWorkerMixin.RECURSIVE_SLUGS == frozenset({ENV_PROBE_SLUG})


def test_smoke_worker_toolkit_binding_constants_when_available() -> None:
    bindings = {
        "tests.fixtures.smoke_components.workers.researchrubrics_smoke": (
            "ResearchRubricsSmokeLeafWorker",
            "ergon_builtins.benchmarks.researchrubrics.toolkit:ResearchRubricsToolkit",
        ),
        "tests.fixtures.smoke_components.workers.minif2f_smoke": (
            "MiniF2FSmokeLeafWorker",
            "ergon_builtins.benchmarks.minif2f.toolkit:MiniF2FToolkit",
        ),
        "tests.fixtures.smoke_components.workers.swebench_smoke": (
            "SweBenchSmokeLeafWorker",
            "ergon_builtins.benchmarks.swebench_verified.toolkit:SWEBenchToolkit",
        ),
    }

    for module_name, (class_name, expected_type) in bindings.items():
        module = __import__(module_name, fromlist=[class_name])
        worker_cls = getattr(module, class_name)
        if hasattr(worker_cls, "toolkit_type"):
            assert worker_cls.toolkit_type == expected_type
