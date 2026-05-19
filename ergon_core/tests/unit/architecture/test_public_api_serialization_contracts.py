"""Architecture guards for public API definition snapshot importability."""

from ergon_core.api._serialization import import_component
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FTask
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload
from ergon_builtins.benchmarks.minif2f.workers import make_minif2f_rubric, make_minif2f_worker
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsTask
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload
from ergon_builtins.benchmarks.researchrubrics.workers import (
    make_research_rubric,
    make_research_worker,
)
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchTask
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload
from ergon_builtins.benchmarks.swebench_verified.workers import (
    make_swebench_rubric,
    make_swebench_worker,
)


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
            worker=make_minif2f_worker(),
            sandbox=LeanSandbox(),
            evaluators=(make_minif2f_rubric(),),
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
            worker=make_swebench_worker(),
            sandbox=SWEBenchSandbox(),
            evaluators=(make_swebench_rubric(),),
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
            worker=make_research_worker(),
            sandbox=ResearchE2BSandbox(),
            evaluators=(make_research_rubric(),),
        ),
    )

    for task in task_payloads:
        dumped = task.model_dump(mode="json")

        assert "[" not in dumped["_type"]
        assert "]" not in dumped["_type"]
        assert import_component(dumped["_type"]) is type(task)
