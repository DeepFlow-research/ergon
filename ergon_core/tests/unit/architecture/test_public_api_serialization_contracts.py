"""Architecture guards for public API definition snapshot importability."""

import ast
import inspect
from pathlib import Path

from ergon_core.api._serialization import (
    component_type_path,
    import_component,
    inject_type_discriminator,
)
from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.minif2f.prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.task import MiniF2FTask
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.researchrubrics.prompts import RESEARCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.task import ResearchRubricsTask
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from ergon_builtins.benchmarks.swebench_verified.prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.task import SweBenchTask
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_core.api.criterion import Criterion
from ergon_core.api.rubric import Evaluator, Rubric
from ergon_core.api.worker import Worker


def _minif2f_worker() -> ReActWorker:
    return ReActWorker(
        name="mini-proof-solver",
        model="test:none",
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
        toolkit=MiniF2FToolkit(),
    )


def _swebench_worker() -> ReActWorker:
    return ReActWorker(
        name="swebench-solver",
        model="test:none",
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
        toolkit=SWEBenchToolkit(),
    )


def _research_worker() -> ReActWorker:
    return ReActWorker(
        name="research-runner",
        model="test:none",
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        max_iterations=16,
        toolkit=ResearchRubricsToolkit(),
    )


_REPO_ROOT = Path(__file__).resolve().parents[4]


def _class_assignments(class_def: ast.ClassDef) -> dict[str, ast.expr]:
    assignments: dict[str, ast.expr] = {}
    for statement in class_def.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            assignments[statement.target.id] = statement.value
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = statement.value
    return assignments


def _is_non_empty_literal_sequence(value: ast.expr | None) -> bool:
    return isinstance(value, ast.List | ast.Tuple) and bool(value.elts)


def _is_non_empty_literal_string(value: ast.expr | None) -> bool:
    return (
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and bool(value.value.strip())
    )


def test_public_api_root_exports_author_facing_exceptions() -> None:
    from ergon_core.api import (
        ContainmentViolation,
        CriterionCheckError,
        DependencyError,
        SandboxKindMismatch,
        SandboxNotLiveError,
    )
    from ergon_core.api.errors import (
        ContainmentViolation as ErrorContainmentViolation,
        CriterionCheckError as ErrorCriterionCheckError,
        DependencyError as ErrorDependencyError,
        SandboxKindMismatch as ErrorSandboxKindMismatch,
        SandboxNotLiveError as ErrorSandboxNotLiveError,
    )

    assert DependencyError is ErrorDependencyError
    assert SandboxKindMismatch is ErrorSandboxKindMismatch
    assert CriterionCheckError is ErrorCriterionCheckError
    assert ContainmentViolation is ErrorContainmentViolation
    assert SandboxNotLiveError is ErrorSandboxNotLiveError


def test_rubric_is_intentionally_core_public_api_evaluator() -> None:
    """Rubric stays in core as the generic fixed-criteria Evaluator."""

    assert Rubric.__module__ == "ergon_core.api.rubric.rubric"
    assert issubclass(Rubric, Evaluator)
    assert Rubric.type_slug == "rubric"

    source = inspect.getsource(Rubric)
    assert "generic fixed-criteria Evaluator" in source


def test_dependency_bearing_public_components_require_install_hints() -> None:
    for base in (Worker, Criterion, Evaluator):
        assert base.install_hint is None

    dependency_bearing_components: list[str] = []
    missing_install_hints: list[str] = []
    for package_path in (
        _REPO_ROOT / "ergon_core" / "ergon_core",
        _REPO_ROOT / "ergon_builtins" / "ergon_builtins",
    ):
        for path in package_path.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for class_def in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
                assignments = _class_assignments(class_def)
                if not _is_non_empty_literal_sequence(assignments.get("required_packages")):
                    continue
                component = f"{path.relative_to(_REPO_ROOT)}::{class_def.name}"
                dependency_bearing_components.append(component)
                if not _is_non_empty_literal_string(assignments.get("install_hint")):
                    missing_install_hints.append(component)

    assert missing_install_hints == []


def test_type_discriminator_helpers_use_importable_component_paths() -> None:
    task = MiniF2FTask(
        task_slug="mini",
        instance_key="default",
        description="MiniF2F sample.",
        task_payload=MiniF2FTaskPayload(
            name="mini",
            informal_statement="Prove one equals one.",
            formal_statement="theorem mini : 1 = 1 := by",
            header="import Mathlib\n",
        ),
        worker=_minif2f_worker(),
        sandbox=LeanSandbox(),
        evaluators=(MiniF2FRubric(name="minif2f-rubric"),),
    )
    payload: dict[str, object] = {"task_slug": task.task_slug}

    injected = inject_type_discriminator(payload, task)

    assert injected is payload
    assert injected["_type"] == component_type_path(task)
    assert import_component(injected["_type"]) is type(task)


def test_migrated_builtin_task_classes_persist_importable_type_discriminators() -> None:
    task_payloads = (
        MiniF2FTask(
            task_slug="mini",
            instance_key="default",
            description="MiniF2F sample.",
            task_payload=MiniF2FTaskPayload(
                name="mini",
                informal_statement="Prove one equals one.",
                formal_statement="theorem mini : 1 = 1 := by",
                header="import Mathlib\n",
            ),
            worker=_minif2f_worker(),
            sandbox=LeanSandbox(),
            evaluators=(MiniF2FRubric(name="minif2f-rubric"),),
        ),
        SweBenchTask(
            task_slug="swe",
            instance_key="default",
            description="SWE sample.",
            task_payload=SWEBenchTaskPayload(
                instance_id="org__repo-1",
                repo="org/repo",
                base_commit="abcdef123456",
                version="1.0",
                problem_statement="Fix a bug.",
                fail_to_pass=[],
                pass_to_pass=[],
                environment_setup_commit="abcdef123456",
                test_patch="diff --git a/test.py b/test.py\n",
            ),
            worker=_swebench_worker(),
            sandbox=SWEBenchSandbox(),
            evaluators=(SWEBenchRubric(name="swebench-rubric"),),
        ),
        ResearchRubricsTask(
            task_slug="rr",
            instance_key="default",
            description="ResearchRubrics sample.",
            task_payload=ResearchRubricsTaskPayload(
                sample_id="rr",
                domain="quality",
                prompt="Write a report.",
                rubrics=[],
            ),
            worker=_research_worker(),
            sandbox=ResearchE2BSandbox(),
            evaluators=(ResearchRubricsRubric(name="researchrubrics-rubric"),),
        ),
    )

    for task in task_payloads:
        dumped = task.model_dump(mode="json")

        assert "[" not in dumped["_type"]
        assert "]" not in dumped["_type"]
        assert import_component(dumped["_type"]) is type(task)
