# Real Sandbox Smoke Posture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ergon test smoke` exercise the real sandbox class for each benchmark environment instead of the local `SmokePublicSandbox` substitute, while making the canonical smoke scenario realistic and assertion-rich enough to catch runtime, dashboard, RL-view, resource-handoff, messaging, and evaluation-ordering regressions.

**Architecture:** Keep one top-of-stack PR that changes both smoke posture and smoke depth. Replace the sandbox posture so root and dynamically spawned smoke tasks carry the benchmark environment's production sandbox type (`ResearchE2BSandbox`, `LeanSandbox`, `SWEBenchSandbox`, and `GDPEvalSandbox` where applicable). At the same time, upgrade the deterministic smoke scenario: realistic root/child task prompts, seeded source documents, cross-task resource handoff, message visibility/reply checks, production builtin toolkit calls, synthetic token/logprob telemetry, tighter host-side assertions, and one deterministic dynamic graph/team mutation lane. Most assertions stay static or host-side for debuggability; add exactly one dynamic-subtask evaluator on the handoff consumer to prove intermediary task evaluation works at terminal state without adding evaluators to every child. The smoke workers remain deterministic and do not invoke an LLM, but when they need file/command/report/proof/repo operations they should exercise the real `ergon_builtins` toolkit surfaces. The test harness should fail fast if a smoke task snapshot contains `SmokePublicSandbox` or `TestSandbox`.

**Tech Stack:** Python 3.13, pytest, FastAPI danger test harness, Ergon public `Sandbox`/`Task` APIs, benchmark sandbox classes, Docker dev stack, Playwright dashboard smoke specs.

---

## File Map

- Modify `tests/fixtures/smoke_components/benchmarks.py`
  - Owns deterministic smoke environments and root task construction.
  - Replace `SmokePublicSandbox()` with per-environment real sandbox factories.
  - Improve root task names/descriptions/payloads so dashboard/API surfaces resemble realistic benchmark work.

- Modify `tests/fixtures/smoke_components/smoke_base/dynamic_tasks.py`
  - Owns dynamic child task construction for recursive smoke workers.
  - Carry the parent's sandbox type/config into spawned child tasks, or accept an explicit sandbox factory/spec.
  - Preserve realistic child task descriptions from the smoke graph instead of generic "child task" phrasing.

- Modify `tests/fixtures/smoke_components/smoke_base/constants.py`
  - Owns the recursive child-task graph shape.
  - Replace abstract node descriptions with realistic subtasks that require file IO, shell commands, artifact production, resource handoff, messaging, dependency ordering, and nested delegation.

- Modify `tests/fixtures/smoke_components/smoke_base/worker_base.py`
  - Owns parent smoke worker orchestration.
  - Seed a realistic source document/message before children run and execute one deterministic graph/team mutation lane.

- Modify `tests/fixtures/smoke_components/smoke_base/leaf_base.py`
  - Owns leaf worker execution.
  - Make selected leaves read upstream resources/messages, invoke production builtin toolkits where practical, emit deterministic token/logprob metadata, and produce handoff artifacts.

- Modify per-environment smoke workers under `tests/fixtures/smoke_components/workers/`
  - Bind each environment to the production toolkit it should exercise:
    `ResearchRubricsToolkit`, `MiniF2FToolkit`, `SWEBenchToolkit`, and `GDPEvalToolkit` if included.

- Modify `tests/fixtures/smoke_components/smoke_base/criterion_base.py`
  - Owns shared smoke criterion assertions.
  - Add exactly one dynamic-subtask evaluator/criterion for the handoff consumer so smoke proves non-root dynamic task evaluation observes terminal state and required upstream resources/messages.

- Modify `tests/e2e/_asserts.py`
  - Owns host-side E2E assertions.
  - Add stricter static/host-side checks for resource lineage, messages, RL training records/logprobs, graph/team mutation visibility, and root + dynamic evaluation rows.

- Modify or retire `tests/fixtures/smoke_components/sandbox.py`
  - This file currently implements the fake local smoke sandbox.
  - Keep only if still needed for narrow unit tests; canonical E2E smoke must not use it.

- Modify `tests/e2e/_submit.py`
  - If needed, include a real-sandbox posture flag in the danger endpoint payload.
  - Default should be real sandbox for `ergon test smoke`.

- Modify `ergon_core/ergon_core/core/infrastructure/http/routes/test_harness.py`
  - Add a smoke posture guard before submission.
  - Optionally support the future multi-environment single-experiment submission shape, but keep this PR focused unless the code change is trivial.

- Add/modify `tests/e2e/test_smoke_real_sandbox_posture.py`
  - Fast static/contract test proving smoke fixture task JSON uses real sandbox types and rejects fake test sandboxes.

- Modify `tests/e2e/test_researchrubrics_smoke.py`, `tests/e2e/test_minif2f_smoke.py`, `tests/e2e/test_swebench_smoke.py`
  - Update misleading docstrings/comments that say "against real E2B" only after the posture is actually true.

---

## Task 1: Add A Failing Contract Test For Root Smoke Sandbox Types

**Files:**
- Create: `tests/e2e/test_smoke_real_sandbox_posture.py`
- Read: `tests/fixtures/smoke_components/benchmarks.py`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
from tests.fixtures.smoke_components.benchmarks import (
    MiniF2FSmokeEnvironment,
    ResearchRubricsSmokeEnvironment,
    SweBenchSmokeEnvironment,
)


def _root_sandbox_type(environment_cls) -> str:
    environment = environment_cls()
    sample = next(iter(environment.iter_samples()))
    [task] = sample.tasks
    task_json = task.model_dump(mode="json")
    return task_json["sandbox"]["_type"]


def test_smoke_root_tasks_use_real_environment_sandboxes() -> None:
    assert _root_sandbox_type(ResearchRubricsSmokeEnvironment) == (
        "ergon_builtins.benchmarks.researchrubrics.sandbox:ResearchE2BSandbox"
    )
    assert _root_sandbox_type(MiniF2FSmokeEnvironment) == (
        "ergon_builtins.benchmarks.minif2f.sandbox:LeanSandbox"
    )
    assert _root_sandbox_type(SweBenchSmokeEnvironment) == (
        "ergon_builtins.benchmarks.swebench_verified.sandbox:SWEBenchSandbox"
    )
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_root_tasks_use_real_environment_sandboxes -q
```

Expected: FAIL because the root smoke environments currently serialize `tests.fixtures.smoke_components.sandbox:SmokePublicSandbox`.

- [ ] **Step 3: Commit only the failing test if desired**

For strict TDD checkpoints:

```bash
git add tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: require real sandbox posture for smoke roots"
```

---

## Task 2: Switch Root Smoke Environments To Real Sandbox Classes

**Files:**
- Modify: `tests/fixtures/smoke_components/benchmarks.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`

- [ ] **Step 1: Import the real benchmark sandboxes**

In `tests/fixtures/smoke_components/benchmarks.py`, replace the `SmokePublicSandbox` import with real sandbox imports:

```python
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
```

- [ ] **Step 2: Replace root sandbox construction**

In each smoke environment `_tasks()` method, use the real sandbox:

```python
# ResearchRubricsSmokeEnvironment
sandbox=ResearchE2BSandbox(),

# MiniF2FSmokeEnvironment
sandbox=LeanSandbox(),

# SweBenchSmokeEnvironment
sandbox=SWEBenchSandbox(),

# GDPEvalSmokeEnvironment
sandbox=GDPEvalSandbox(),
```

Remove stale comments claiming the smoke fixture uses `SmokeSandboxManager`.

- [ ] **Step 3: Verify GREEN for root posture**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_root_tasks_use_real_environment_sandboxes -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/smoke_components/benchmarks.py tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: run smoke roots with real benchmark sandboxes"
```

---

## Task 3: Ensure Dynamically Spawned Smoke Tasks Keep Real Sandbox Posture

**Files:**
- Modify: `tests/fixtures/smoke_components/smoke_base/dynamic_tasks.py`
- Modify if needed: `tests/fixtures/smoke_components/smoke_base/worker_base.py`
- Modify if needed: `tests/fixtures/smoke_components/smoke_base/recursive.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`

- [ ] **Step 1: Add failing dynamic-task posture test**

Append to `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from tests.fixtures.smoke_components.smoke_base.dynamic_tasks import (
    SmokeChildTaskSpec,
    smoke_task_from_spec,
)


def _child_sandbox_type(environment_cls) -> str:
    environment = environment_cls()
    sample = next(iter(environment.iter_samples()))
    [parent_task] = sample.tasks
    child = smoke_task_from_spec(
        parent_task=parent_task,
        spec=SmokeChildTaskSpec(
            task_slug=TaskSlug("child"),
            description="child task",
            assigned_worker_slug=AssignedWorkerSlug("child-worker"),
            depends_on=[],
        ),
        model="openai:gpt-4o",
    )
    return child.model_dump(mode="json")["sandbox"]["_type"]


def test_smoke_dynamic_tasks_inherit_real_parent_sandbox_type() -> None:
    assert _child_sandbox_type(ResearchRubricsSmokeEnvironment) == (
        "ergon_builtins.benchmarks.researchrubrics.sandbox:ResearchE2BSandbox"
    )
    assert _child_sandbox_type(MiniF2FSmokeEnvironment) == (
        "ergon_builtins.benchmarks.minif2f.sandbox:LeanSandbox"
    )
    assert _child_sandbox_type(SweBenchSmokeEnvironment) == (
        "ergon_builtins.benchmarks.swebench_verified.sandbox:SWEBenchSandbox"
    )
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_dynamic_tasks_inherit_real_parent_sandbox_type -q
```

Expected: FAIL if `smoke_task_from_spec` still constructs `SmokePublicSandbox()`.

- [ ] **Step 3: Implement inheritance from parent task sandbox**

In `tests/fixtures/smoke_components/smoke_base/dynamic_tasks.py`, replace direct fake sandbox construction with a copy of the parent task sandbox config.

Preferred implementation:

```python
from copy import deepcopy


def _clone_parent_sandbox(parent_task: Task) -> Sandbox:
    return deepcopy(parent_task.sandbox)
```

Then in `smoke_task_from_spec(...)`, set:

```python
sandbox=_clone_parent_sandbox(parent_task),
```

If `Task.sandbox` may be absent, fail loudly:

```python
if parent_task.sandbox is None:
    raise ValueError("smoke dynamic tasks require parent_task.sandbox")
```

- [ ] **Step 4: Verify dynamic posture**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/smoke_components/smoke_base/dynamic_tasks.py tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: inherit real sandbox posture for smoke subtasks"
```

---

## Task 4: Make Smoke Task Names And Descriptions Realistic

**Files:**
- Modify: `tests/fixtures/smoke_components/benchmarks.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/constants.py`
- Modify if needed: `tests/fixtures/smoke_components/smoke_base/dynamic_tasks.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`

- [ ] **Step 1: Add failing realism contract tests**

Append to `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
from tests.fixtures.smoke_components.smoke_base.constants import SUBTASK_GRAPH


def _root_task_snapshot(environment_cls) -> dict:
    environment = environment_cls()
    sample = next(iter(environment.iter_samples()))
    [task] = sample.tasks
    return task.model_dump(mode="json")


def test_smoke_root_tasks_have_realistic_environment_descriptions() -> None:
    research = _root_task_snapshot(ResearchRubricsSmokeEnvironment)
    assert research["task_slug"] == "research-report"
    assert "research brief" in research["description"].lower()
    assert "evidence" in research["description"].lower()

    mini = _root_task_snapshot(MiniF2FSmokeEnvironment)
    assert mini["task_slug"] == "lean-proof"
    assert "lean" in mini["description"].lower()
    assert "proof" in mini["description"].lower()

    swe = _root_task_snapshot(SweBenchSmokeEnvironment)
    assert swe["task_slug"] == "repo-fix"
    assert "repository" in swe["description"].lower()
    assert "regression" in swe["description"].lower()


def test_smoke_child_task_descriptions_cover_real_runtime_behaviors() -> None:
    descriptions = " ".join(description.lower() for _, _, description in SUBTASK_GRAPH)
    for expected in (
        "inspect",
        "write",
        "command",
        "artifact",
        "verify",
        "summarize",
    ):
        assert expected in descriptions
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_root_tasks_have_realistic_environment_descriptions tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_child_task_descriptions_cover_real_runtime_behaviors -q
```

Expected: FAIL because current smoke roots use generic slugs/descriptions like `smoke-001`, `mathd_algebra_478`, and child graph descriptions like `Nested line node 2a`.

- [ ] **Step 3: Update root task slugs/descriptions**

In `tests/fixtures/smoke_components/benchmarks.py`, update the smoke environment constants:

```python
class ResearchRubricsSmokeEnvironment(_SingleTaskSmokeEnvironment):
    task_slug: ClassVar[str] = "research-report"
    task_description: ClassVar[str] = (
        "Draft a concise research brief from the supplied prompt, preserve the "
        "expected smoke-test evidence marker, and write the final report artifact."
    )


class MiniF2FSmokeEnvironment(_SingleTaskSmokeEnvironment):
    task_slug: ClassVar[str] = "lean-proof"
    task_description: ClassVar[str] = (
        "Inspect the Lean theorem statement, run the proof-check command, and "
        "produce a final proof artifact for the smoke theorem."
    )


class SweBenchSmokeEnvironment(_SingleTaskSmokeEnvironment):
    task_slug: ClassVar[str] = "repo-fix"
    task_description: ClassVar[str] = (
        "Inspect the repository regression, apply a minimal code fix, run the "
        "verification command, and summarize the patch artifact."
    )
```

For `GDPEvalSmokeEnvironment`, use:

```python
task_slug: ClassVar[str] = "workflow-debug"
task_description: ClassVar[str] = (
    "Inspect the workflow inputs, run the smoke validation command, and produce "
    "a final workflow-debug artifact."
)
```

- [ ] **Step 4: Update child graph slugs and descriptions**

In `tests/fixtures/smoke_components/smoke_base/constants.py`, rename the dynamic topology slugs to semantic IDs and replace descriptions with realistic work. The slugs are part of the smoke contract and should be referenced through named constants, not repeated as raw strings elsewhere:

```python
SOURCE_REVIEW_SLUG = "source-review"
ENV_PROBE_SLUG = "environment-probe"
HANDOFF_VERIFY_SLUG = "handoff-verify"
PRIMARY_ARTIFACT_SLUG = "primary-artifact"
EVIDENCE_ARTIFACT_SLUG = "evidence-artifact"
ARTIFACT_SUMMARY_SLUG = "artifact-summary"
METADATA_REVIEW_SLUG = "metadata-review"
METADATA_VALIDATE_SLUG = "metadata-validate"
COMPLETION_MARKER_SLUG = "completion-marker"

EXPECTED_SUBTASK_SLUGS: tuple[str, ...] = (
    SOURCE_REVIEW_SLUG,
    ENV_PROBE_SLUG,
    HANDOFF_VERIFY_SLUG,
    PRIMARY_ARTIFACT_SLUG,
    EVIDENCE_ARTIFACT_SLUG,
    ARTIFACT_SUMMARY_SLUG,
    METADATA_REVIEW_SLUG,
    METADATA_VALIDATE_SLUG,
    COMPLETION_MARKER_SLUG,
)

SUBTASK_GRAPH: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (SOURCE_REVIEW_SLUG, (), "Inspect the task payload and write an initial workspace note."),
    (ENV_PROBE_SLUG, (), "Run a sandbox command to probe the environment and record the result."),
    (
        HANDOFF_VERIFY_SLUG,
        (SOURCE_REVIEW_SLUG, ENV_PROBE_SLUG),
        "Verify the inspected inputs against the command probe output.",
    ),
    (
        PRIMARY_ARTIFACT_SLUG,
        (HANDOFF_VERIFY_SLUG,),
        "Write the primary artifact into the final output directory.",
    ),
    (
        EVIDENCE_ARTIFACT_SLUG,
        (HANDOFF_VERIFY_SLUG,),
        "Create a secondary evidence artifact for evaluation.",
    ),
    (
        ARTIFACT_SUMMARY_SLUG,
        (PRIMARY_ARTIFACT_SLUG, EVIDENCE_ARTIFACT_SLUG),
        "Summarize the artifact set and dependency decisions.",
    ),
    (METADATA_REVIEW_SLUG, (), "Inspect optional metadata and produce an auxiliary note."),
    (
        METADATA_VALIDATE_SLUG,
        (METADATA_REVIEW_SLUG,),
        "Validate the auxiliary note with a sandbox command.",
    ),
    (COMPLETION_MARKER_SLUG, (), "Write a standalone completion marker artifact."),
)
```

If `NESTED_SUBTASK_GRAPH` in `tests/fixtures/smoke_components/smoke_base/recursive.py` still uses generic descriptions, update it to:

```python
NESTED_INSPECT_SLUG = "nested-input-review"
NESTED_VERIFY_SLUG = "nested-verification"
NESTED_LINE_SLUGS: tuple[str, ...] = (NESTED_INSPECT_SLUG, NESTED_VERIFY_SLUG)

NESTED_SUBTASK_GRAPH: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (NESTED_INSPECT_SLUG, (), "Inspect nested worker inputs and write a nested scratch note."),
    (
        NESTED_VERIFY_SLUG,
        (NESTED_INSPECT_SLUG,),
        "Run a nested verification command and summarize the result.",
    ),
)
```

Update any tests/assertions that import `NESTED_LINE_SLUGS` to import it from the canonical constants module if the ownership moves. The old internal slugs (`d_root`, `d_left`, `l_2`, etc.) should not remain in canonical smoke assertions.

- [ ] **Step 5: Verify realism tests**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/smoke_components/benchmarks.py tests/fixtures/smoke_components/smoke_base/constants.py tests/fixtures/smoke_components/smoke_base/recursive.py tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: make smoke task prompts more realistic"
```

---

## Task 5: Add A Harness Guard Against Fake Sandboxes In Canonical Smoke

**Files:**
- Modify: `ergon_core/ergon_core/core/infrastructure/http/routes/test_harness.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`

- [ ] **Step 1: Add failing guard test**

Append to `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
import pytest

from ergon_core.core.infrastructure.http.routes.test_harness import (
    _assert_real_smoke_sandbox_posture,
)


def test_test_harness_rejects_smoke_public_sandbox() -> None:
    bad_task_json = {
        "sandbox": {
            "_type": "tests.fixtures.smoke_components.sandbox:SmokePublicSandbox",
        }
    }
    with pytest.raises(ValueError, match="canonical smoke requires real benchmark sandboxes"):
        _assert_real_smoke_sandbox_posture([bad_task_json])


def test_test_harness_rejects_test_support_sandbox() -> None:
    bad_task_json = {
        "sandbox": {
            "_type": "ergon_core.test_support.task_factory:TestSandbox",
        }
    }
    with pytest.raises(ValueError, match="canonical smoke requires real benchmark sandboxes"):
        _assert_real_smoke_sandbox_posture([bad_task_json])
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_test_harness_rejects_smoke_public_sandbox tests/e2e/test_smoke_real_sandbox_posture.py::test_test_harness_rejects_test_support_sandbox -q
```

Expected: FAIL because `_assert_real_smoke_sandbox_posture` does not exist.

- [ ] **Step 3: Implement the guard helper**

In `ergon_core/ergon_core/core/infrastructure/http/routes/test_harness.py`, add:

```python
_DISALLOWED_SMOKE_SANDBOX_TYPES = frozenset(
    {
        "tests.fixtures.smoke_components.sandbox:SmokePublicSandbox",
        "ergon_core.test_support.task_factory:TestSandbox",
    }
)


def _assert_real_smoke_sandbox_posture(task_jsons: list[dict]) -> None:
    for task_json in task_jsons:
        sandbox = task_json.get("sandbox")
        sandbox_type = sandbox.get("_type") if isinstance(sandbox, dict) else None
        if sandbox_type in _DISALLOWED_SMOKE_SANDBOX_TYPES:
            raise ValueError(
                "canonical smoke requires real benchmark sandboxes; "
                f"found disallowed sandbox type {sandbox_type!r}"
            )
```

- [ ] **Step 4: Call the guard before submit**

In `submit_experiment_samples`, after materializing `samples` and before `experiment.submit(...)`, call:

```python
samples = list(environment.iter_samples())[: body.limit]
_assert_real_smoke_sandbox_posture(
    [task.model_dump(mode="json") for sample in samples for task in sample.tasks]
)
experiment = Experiment(
    name=body.experiment,
    environments=[
        _HarnessEnvironment(
            name=body.environment_slug,
            samples=samples,
            metadata={"source": "test-harness"},
        )
    ],
    metadata={"source": "test-harness"},
)
```

Translate `ValueError` to `HTTPException(500, ...)` or let it raise as a test-harness bug. Prefer a 500 because this is a broken harness invariant, not user input.

- [ ] **Step 5: Verify guard tests**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ergon_core/ergon_core/core/infrastructure/http/routes/test_harness.py tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: reject fake sandboxes in smoke harness"
```

---

## Task 6: Seed Realistic Documents And Cross-Task Handoffs

**Files:**
- Modify: `tests/fixtures/smoke_components/smoke_base/worker_base.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/leaf_base.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/criterion_base.py`
- Modify: `tests/e2e/_asserts.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`
- Test: `tests/e2e/test_researchrubrics_smoke.py`, `tests/e2e/test_minif2f_smoke.py`, `tests/e2e/test_swebench_smoke.py`

- [ ] **Step 1: Add failing semantic coverage tests**

Append to `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
from tests.fixtures.smoke_components.smoke_base.constants import (
    EXPECTED_RESOURCE_HANDOFF,
    HANDOFF_RESOURCE_NAME,
    HANDOFF_VERIFY_SLUG,
    SEEDED_SOURCE_DOC_NAME,
    SMOKE_THREAD_TOPIC,
    SOURCE_REVIEW_SLUG,
)


def test_smoke_semantic_contract_names_seeded_docs_handoffs_and_threads() -> None:
    assert SEEDED_SOURCE_DOC_NAME == "smoke_source_brief.md"
    assert SMOKE_THREAD_TOPIC == "smoke-coordination"
    assert SOURCE_REVIEW_SLUG == "source-review"
    assert HANDOFF_VERIFY_SLUG == "handoff-verify"
    assert HANDOFF_RESOURCE_NAME == "handoff_source_review.json"
    assert EXPECTED_RESOURCE_HANDOFF.producer_slug == SOURCE_REVIEW_SLUG
    assert EXPECTED_RESOURCE_HANDOFF.consumer_slug == HANDOFF_VERIFY_SLUG
    assert EXPECTED_RESOURCE_HANDOFF.resource_name == HANDOFF_RESOURCE_NAME
```

Expected new constants:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectedResourceHandoff:
    producer_slug: str
    consumer_slug: str
    resource_name: str


SEEDED_SOURCE_DOC_NAME = "smoke_source_brief.md"
SMOKE_THREAD_TOPIC = "smoke-coordination"
HANDOFF_RESOURCE_NAME = "handoff_source_review.json"
EXPECTED_RESOURCE_HANDOFF = ExpectedResourceHandoff(
    producer_slug=SOURCE_REVIEW_SLUG,
    consumer_slug=HANDOFF_VERIFY_SLUG,
    resource_name=HANDOFF_RESOURCE_NAME,
)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_semantic_contract_names_seeded_docs_handoffs_and_threads -q
```

Expected: FAIL because those constants do not exist.

- [ ] **Step 3: Add smoke semantic constants**

In `tests/fixtures/smoke_components/smoke_base/constants.py`, add the dataclass and constants from Step 1. Keep names stable because both fixture code and host-side assertions will consume them.

- [ ] **Step 4: Seed a realistic source document and coordination message**

In `tests/fixtures/smoke_components/smoke_base/worker_base.py`, before spawning children, write a source document and coordination message. Use existing runtime/context APIs already used in smoke workers; the implementation must be deterministic.

Target behavior:

```python
seeded_doc = "\n".join(
    [
        "# Smoke Source Brief",
        "",
        "The child tasks must preserve marker SMOKE_RESOURCE_HANDOFF_OK.",
        f"The consumer task must read {HANDOFF_RESOURCE_NAME} before writing its artifact.",
    ]
)
await task.sandbox.write_file(f"/workspace/{SEEDED_SOURCE_DOC_NAME}", seeded_doc)
await communication_service.save_message(
    CreateMessageRequest(
        sample_id=context.sample_id,
        task_attempt_id=context.execution_id,
        from_agent_id="parent",
        to_agent_id=EXPECTED_RESOURCE_HANDOFF.consumer_slug,
        thread_topic=SMOKE_THREAD_TOPIC,
        content=f"Read {HANDOFF_RESOURCE_NAME} before producing your artifact.",
    )
)
```

If `WorkerContext` already provides a higher-level message/resource API, use that instead of directly importing `communication_service`. The assertion contract is the important bit: the message must exist before `EXPECTED_RESOURCE_HANDOFF.consumer_slug` starts.

- [ ] **Step 5: Make the source-review task produce a named handoff resource**

In `tests/fixtures/smoke_components/smoke_base/leaf_base.py`, when executing `EXPECTED_RESOURCE_HANDOFF.producer_slug`, write and persist `HANDOFF_RESOURCE_NAME` with deterministic content:

```json
{
  "marker": "SMOKE_RESOURCE_HANDOFF_OK",
  "producer": "source-review",
  "consumer": "handoff-verify",
  "source_doc": "smoke_source_brief.md"
}
```

The resource must be persisted as a normal task resource, not only left in the sandbox filesystem.

- [ ] **Step 6: Make the handoff-verify task read the handoff and reply on the thread**

In `leaf_base.py`, when executing `EXPECTED_RESOURCE_HANDOFF.consumer_slug`:

```python
handoff = await context.read_resource_by_name(HANDOFF_RESOURCE_NAME)
assert "SMOKE_RESOURCE_HANDOFF_OK" in handoff.decode("utf-8")
await communication_service.save_message(
    CreateMessageRequest(
        sample_id=context.sample_id,
        task_attempt_id=context.execution_id,
        from_agent_id=EXPECTED_RESOURCE_HANDOFF.consumer_slug,
        to_agent_id="parent",
        thread_topic=SMOKE_THREAD_TOPIC,
        content=f"Confirmed {HANDOFF_RESOURCE_NAME} marker SMOKE_RESOURCE_HANDOFF_OK.",
    )
)
```

If no `read_resource_by_name` helper exists, use the repository/read-service path that production criterion code uses to read task resources. Do not fake success by sharing an in-memory variable.

- [ ] **Step 7: Add one dynamic-subtask evaluator for intermediary terminal-state coverage**

Add one evaluator/criterion attached to `EXPECTED_RESOURCE_HANDOFF.consumer_slug` only. Do not add evaluators to every dynamic child. The purpose is narrow: prove evaluation works for a non-root dynamic task after that task reaches terminal state, and prove the evaluator context can see the upstream handoff resource and coordination messages.

Target criterion behavior:

```python
class SmokeIntermediateHandoffCriterion(Criterion):
    slug = "smoke-intermediate-handoff"

    async def evaluate(self, context: CriterionContext) -> CriterionResult:
        task_slug = context.task.task_slug
        assert task_slug == EXPECTED_RESOURCE_HANDOFF.consumer_slug
        handoff_body = read_handoff_resource(context, HANDOFF_RESOURCE_NAME)
        assert handoff_body["marker"] == "SMOKE_RESOURCE_HANDOFF_OK"
        assert handoff_body["producer"] == EXPECTED_RESOURCE_HANDOFF.producer_slug
        assert handoff_body["consumer"] == EXPECTED_RESOURCE_HANDOFF.consumer_slug
        assert thread_contains(
            context,
            topic=SMOKE_THREAD_TOPIC,
            from_agent_id="parent",
            to_agent_id=EXPECTED_RESOURCE_HANDOFF.consumer_slug,
        )
        assert thread_contains(
            context,
            topic=SMOKE_THREAD_TOPIC,
            from_agent_id=EXPECTED_RESOURCE_HANDOFF.consumer_slug,
            content_fragment=f"Confirmed {HANDOFF_RESOURCE_NAME}",
        )
        return CriterionResult(score=1.0, reason="intermediate handoff visible")
```

Attach this criterion to the `handoff-verify` dynamic task when it is created. If the current dynamic-task API does not support attaching an evaluator at spawn time, extend the smoke task construction path just enough to pass `evaluators=[SmokeIntermediateHandoffCriterion(...)]` for `EXPECTED_RESOURCE_HANDOFF.consumer_slug`.

This makes exactly one check happen through the runtime evaluation path, not just host-side pytest. It covers the ordering gap we care about: dynamic task evaluation should happen after that dynamic task is terminal and after the required upstream resource/message exists.

- [ ] **Step 8: Add host-side E2E assertions**

In `tests/e2e/_asserts.py`, add:

```python
def _assert_resource_handoff_and_coordination_thread(sample_id: UUID) -> None:
    handoff_prefix = HANDOFF_RESOURCE_NAME.removesuffix(".json")
    handoffs = list_named_resources(sample_id, prefix=handoff_prefix, suffix=".json")
    assert len(handoffs) == 1, (
        f"expected one {EXPECTED_RESOURCE_HANDOFF.producer_slug} handoff resource, "
        f"got {len(handoffs)}"
    )
    body = json.loads(read_resource_bytes(handoffs[0]).decode("utf-8"))
    assert body["marker"] == "SMOKE_RESOURCE_HANDOFF_OK"
    assert body["producer"] == EXPECTED_RESOURCE_HANDOFF.producer_slug
    assert body["consumer"] == EXPECTED_RESOURCE_HANDOFF.consumer_slug

    snapshot = require_run_snapshot(sample_id)
    thread = next((t for t in snapshot.threads if t.topic == SMOKE_THREAD_TOPIC), None)
    assert thread is not None, f"missing {SMOKE_THREAD_TOPIC} thread"
    messages = sorted(thread.messages, key=lambda message: message.sequence_num)
    assert messages[0].from_agent_id == "parent"
    assert messages[0].to_agent_id == EXPECTED_RESOURCE_HANDOFF.consumer_slug
    assert any(
        message.from_agent_id == EXPECTED_RESOURCE_HANDOFF.consumer_slug
        and f"Confirmed {HANDOFF_RESOURCE_NAME}" in message.content
        for message in messages
    )
```

Add a host-side evaluation assertion alongside this:

```python
def _assert_intermediate_handoff_evaluation(sample_id: UUID) -> None:
    snapshot = require_run_snapshot(sample_id)
    consumer = next(
        task
        for task in snapshot.tasks.values()
        if task.name == EXPECTED_RESOURCE_HANDOFF.consumer_slug
    )
    evaluations = snapshot.evaluations_by_task.get(consumer.id, [])
    assert len(evaluations) == 1, (
        f"expected one intermediate evaluation for {EXPECTED_RESOURCE_HANDOFF.consumer_slug}, "
        f"got {len(evaluations)}"
    )
    [evaluation] = evaluations
    assert evaluation.score == 1.0
    assert evaluation.evaluator_name
    assert any(
        criterion.criterion_name == "smoke-intermediate-handoff"
        and criterion.status == "passed"
        for criterion in evaluation.criterion_results
    )
```

Call `_assert_resource_handoff_and_coordination_thread(rid)` and `_assert_intermediate_handoff_evaluation(rid)` from every happy-path smoke assertion. For the sad path, assert that handoff exists only if `EXPECTED_RESOURCE_HANDOFF.producer_slug` completed and that no blocked task fabricated a reply or successful intermediate evaluation.

- [ ] **Step 9: Verify focused and E2E tests**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
ergon test smoke
```

Expected: PASS. The smoke run should now fail if resource visibility, message persistence, or evaluation access to resources regresses.

- [ ] **Step 10: Commit**

```bash
git add tests/fixtures/smoke_components/smoke_base/constants.py tests/fixtures/smoke_components/smoke_base/worker_base.py tests/fixtures/smoke_components/smoke_base/leaf_base.py tests/fixtures/smoke_components/smoke_base/criterion_base.py tests/e2e/_asserts.py tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: add smoke resource handoff and coordination assertions"
```

---

## Task 7: Exercise Production Builtin Toolkits In Smoke Workers

**Files:**
- Modify: `tests/fixtures/smoke_components/smoke_base/leaf_base.py`
- Modify: `tests/fixtures/smoke_components/workers/researchrubrics_smoke.py`
- Modify: `tests/fixtures/smoke_components/workers/minif2f_smoke.py`
- Modify: `tests/fixtures/smoke_components/workers/swebench_smoke.py`
- Modify if included: `tests/fixtures/smoke_components/benchmarks.py`
- Modify: `tests/e2e/_asserts.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`

- [ ] **Step 1: Add failing toolkit posture contract**

Append to `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
from tests.fixtures.smoke_components.workers.minif2f_smoke import MiniF2FSmokeLeafWorker
from tests.fixtures.smoke_components.workers.researchrubrics_smoke import (
    ResearchRubricsSmokeLeafWorker,
)
from tests.fixtures.smoke_components.workers.swebench_smoke import SweBenchSmokeLeafWorker


def test_smoke_leaf_workers_bind_production_builtin_toolkits() -> None:
    assert ResearchRubricsSmokeLeafWorker.toolkit_type == (
        "ergon_builtins.benchmarks.researchrubrics.toolkit:ResearchRubricsToolkit"
    )
    assert MiniF2FSmokeLeafWorker.toolkit_type == (
        "ergon_builtins.benchmarks.minif2f.toolkit:MiniF2FToolkit"
    )
    assert SweBenchSmokeLeafWorker.toolkit_type == (
        "ergon_builtins.benchmarks.swebench_verified.toolkit:SWEBenchToolkit"
    )
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_leaf_workers_bind_production_builtin_toolkits -q
```

Expected: FAIL because smoke leaf workers do not expose production toolkit bindings yet.

- [ ] **Step 3: Add toolkit bindings to smoke leaf workers**

In each env worker module, add class attributes on the leaf worker:

```python
# tests/fixtures/smoke_components/workers/researchrubrics_smoke.py
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit


class ResearchRubricsSmokeLeafWorker(BaseSmokeLeafWorker):
    toolkit_cls: ClassVar[type] = ResearchRubricsToolkit
    toolkit_type: ClassVar[str] = (
        "ergon_builtins.benchmarks.researchrubrics.toolkit:ResearchRubricsToolkit"
    )
```

```python
# tests/fixtures/smoke_components/workers/minif2f_smoke.py
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit


class MiniF2FSmokeLeafWorker(BaseSmokeLeafWorker):
    toolkit_cls: ClassVar[type] = MiniF2FToolkit
    toolkit_type: ClassVar[str] = (
        "ergon_builtins.benchmarks.minif2f.toolkit:MiniF2FToolkit"
    )
```

```python
# tests/fixtures/smoke_components/workers/swebench_smoke.py
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit


class SweBenchSmokeLeafWorker(BaseSmokeLeafWorker):
    toolkit_cls: ClassVar[type] = SWEBenchToolkit
    toolkit_type: ClassVar[str] = (
        "ergon_builtins.benchmarks.swebench_verified.toolkit:SWEBenchToolkit"
    )
```

If GDPEval smoke is wired into `ergon test smoke`, mirror this with `GDPEvalToolkit`.

- [ ] **Step 4: Invoke toolkit tools deterministically**

In `tests/fixtures/smoke_components/smoke_base/leaf_base.py`, add a helper that builds tools from `self.toolkit_cls()` and dispatches by toolkit class name. Keep the sequence deterministic and do not invoke a model/ReAct loop.

Use toolkit name/class as the primary discriminator, not "does this toolkit happen to expose tool names X and Y". Tool-name probing is too brittle: a harmless rename or an added compatibility alias could silently change which branch the smoke takes. The smoke should fail clearly if a known environment is bound to the wrong toolkit, and only then use the small set of tool names needed for that toolkit's intended probe.

Target helper shape:

```python
async def _run_builtin_toolkit_probe(self, task: Task, context: WorkerContext) -> dict:
    toolkit_cls = getattr(type(self), "toolkit_cls", None)
    if toolkit_cls is None:
        return {"toolkit": None, "tools": []}

    toolkit = toolkit_cls()
    toolkit_name = type(toolkit).__name__
    tools = {tool.name: tool for tool in toolkit.tools(task.sandbox, task)}

    if toolkit_name == "ResearchRubricsToolkit":
        write = await tools["write_report"].function(
            "final_output/toolkit_probe.md",
            "SMOKE_TOOLKIT_PROBE_OK research report",
        )
        read = await tools["read_report"].function("final_output/toolkit_probe.md")
        return {"toolkit": toolkit_name, "write": write.model_dump(), "read": read.model_dump()}

    if toolkit_name == "MiniF2FToolkit":
        path = "/workspace/final_output/toolkit_probe.lean"
        content = "theorem smoke_toolkit_probe : True := by trivial\n"
        write = await tools["write_lean_file"].function(path, content)
        verify = await tools["verify_lean_proof"].function(path)
        return {"toolkit": toolkit_name, "write": write.model_dump(), "verify": verify.model_dump()}

    if toolkit_name == "SWEBenchToolkit":
        create = await tools["str_replace_editor"].function(
            command="create",
            path="toolkit_probe.py",
            file_text="def add(a, b):\n    return a + b\n",
        )
        bash = await tools["bash"].function("python -m py_compile toolkit_probe.py", timeout_sec=60)
        return {"toolkit": toolkit_name, "create": create.model_dump(), "bash": bash.model_dump()}

    raise AssertionError(f"Unexpected smoke toolkit {toolkit_name!r}")
```

Adjust invocation syntax to match `pydantic_ai.tools.Tool`'s callable API if `.function` is not public in the installed version. The important contract is: verify the smoke leaf is bound to the expected production toolkit, use the production toolkit's `tools(...)` method, and call the same live tool function that a worker would expose to an agent.

- [ ] **Step 5: Persist toolkit probe output as a normal smoke artifact**

When the helper runs, persist the result as a task resource named:

```text
toolkit_probe_<task_slug>.json
```

The JSON body must include:

```json
{
  "toolkit": "ResearchRubricsToolkit | MiniF2FToolkit | SWEBenchToolkit",
  "marker": "SMOKE_TOOLKIT_PROBE_OK",
  "tool_names": ["..."]
}
```

- [ ] **Step 6: Add host-side toolkit assertions**

In `tests/e2e/_asserts.py`, add:

```python
def _assert_builtin_toolkit_probe(sample_id: UUID, *, expected_toolkit: str) -> None:
    resources = list_named_resources(sample_id, prefix="toolkit_probe_", suffix=".json")
    assert resources, "expected at least one toolkit probe resource"
    bodies = [json.loads(read_resource_bytes(resource).decode("utf-8")) for resource in resources]
    matching = [body for body in bodies if body.get("toolkit") == expected_toolkit]
    assert matching, f"missing toolkit probe for {expected_toolkit}; saw {bodies}"
    assert any(body.get("marker") == "SMOKE_TOOLKIT_PROBE_OK" for body in matching)
```

Wire expected toolkit by environment:

```python
_assert_builtin_toolkit_probe(rid, expected_toolkit="ResearchRubricsToolkit")
_assert_builtin_toolkit_probe(rid, expected_toolkit="MiniF2FToolkit")
_assert_builtin_toolkit_probe(rid, expected_toolkit="SWEBenchToolkit")
```

- [ ] **Step 7: Verify**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
ergon test smoke
```

Expected: PASS. Failures should point to real builtin toolkit integration issues: serialization, live sandbox attachment, command wrapping, path assumptions, or response-model shape drift.

- [ ] **Step 8: Commit**

```bash
git add tests/fixtures/smoke_components/smoke_base/leaf_base.py tests/fixtures/smoke_components/workers/researchrubrics_smoke.py tests/fixtures/smoke_components/workers/minif2f_smoke.py tests/fixtures/smoke_components/workers/swebench_smoke.py tests/e2e/_asserts.py tests/e2e/test_smoke_real_sandbox_posture.py
git commit -m "test: exercise builtin toolkits in smoke workers"
```

---

## Task 8: Tighten RL View Shape, Evaluation Ordering, And Dynamic Mutation Assertions

**Files:**
- Modify: `tests/fixtures/smoke_components/smoke_base/leaf_base.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/worker_base.py`
- Modify: `tests/e2e/_asserts.py`
- Modify if needed: `ergon_core/ergon_core/test_support/e2e_read_helpers.py`
- Test: `tests/e2e/test_smoke_real_sandbox_posture.py`
- Test: `ergon_core/tests/unit/views/rl/`

- [ ] **Step 1: Add failing static contract for synthetic RL metadata**

Append to `tests/e2e/test_smoke_real_sandbox_posture.py`:

```python
from tests.fixtures.smoke_components.smoke_base.constants import (
    EXPECTED_PARENT_VISIBLE_CHILD_RESULT,
    EXPECTED_SMOKE_LOGPROBS,
    EXPECTED_SMOKE_TOKEN_IDS,
    EXPECTED_SUBAGENT_INTERNAL_MARKER,
)


def test_smoke_contract_declares_synthetic_rl_tokens_and_logprobs() -> None:
    assert EXPECTED_SMOKE_TOKEN_IDS == [101, 202, 303]
    assert EXPECTED_SMOKE_LOGPROBS == [-0.10, -0.20, -0.30]
    assert EXPECTED_SUBAGENT_INTERNAL_MARKER == "SMOKE_CHILD_INTERNAL_THINKING"
    assert EXPECTED_PARENT_VISIBLE_CHILD_RESULT == "SMOKE_CHILD_RESULT_PARENT_VISIBLE"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py::test_smoke_contract_declares_synthetic_rl_tokens_and_logprobs -q
```

Expected: FAIL because the constants do not exist.

- [ ] **Step 3: Add RL metadata constants**

In `tests/fixtures/smoke_components/smoke_base/constants.py`, add:

```python
EXPECTED_SMOKE_TOKEN_IDS: list[int] = [101, 202, 303]
EXPECTED_SMOKE_LOGPROBS: list[float] = [-0.10, -0.20, -0.30]
EXPECTED_SUBAGENT_INTERNAL_MARKER = "SMOKE_CHILD_INTERNAL_THINKING"
EXPECTED_PARENT_VISIBLE_CHILD_RESULT = "SMOKE_CHILD_RESULT_PARENT_VISIBLE"
```

- [ ] **Step 4: Emit synthetic token/logprob metadata from a smoke leaf**

In `tests/fixtures/smoke_components/smoke_base/leaf_base.py`, make at least one deterministic leaf stream a context/tool/action event whose persisted token metadata includes:

```python
{
    "token_ids": [101, 202, 303],
    "logprobs": [
        {"token_id": 101, "token": "smoke", "logprob": -0.10},
        {"token_id": 202, "token": "handoff", "logprob": -0.20},
        {"token_id": 303, "token": "ok", "logprob": -0.30},
    ],
}
```

Use the same event path that real workers/tool calls use so `RlEpisodeReadService` and `RlProjectionService` see the metadata. Do not add a special-case RL test table writer.

Also emit deterministic text markers through real context events:

- a child-internal action text containing `EXPECTED_SUBAGENT_INTERNAL_MARKER`
- a parent-visible tool result / child result text containing `EXPECTED_PARENT_VISIBLE_CHILD_RESULT`

The smoke RL assertion should verify the parent actor span excludes the child-internal marker while the joint timeline still contains it, and that the parent actor span includes the parent-visible child result. This preserves the formalism we wanted: child internals exist in the joint episode tree, but the parent learns from the spawn action and returned result, not from the child's private rollout.

- [ ] **Step 5: Add host-side RL projection assertion**

In `tests/e2e/_asserts.py`, add:

```python
def _assert_smoke_rl_view_shape(sample_id: UUID) -> None:
    from ergon_core.core.persistence.shared.db import get_session
    from ergon_core.core.views.rl.episode import RlEpisodeReadService
    from ergon_core.core.views.rl.projections import RlProjectionService
    from tests.fixtures.smoke_components.smoke_base.constants import (
        EXPECTED_PARENT_VISIBLE_CHILD_RESULT,
        EXPECTED_SMOKE_LOGPROBS,
        EXPECTED_SMOKE_TOKEN_IDS,
        EXPECTED_SUBAGENT_INTERNAL_MARKER,
        EXPECTED_SUBTASK_SLUGS,
    )

    with get_session() as session:
        episode = RlEpisodeReadService(session).get_episode(sample_id)

    assert episode.sample_id == sample_id
    assert episode.experiment_id is not None
    assert episode.environment_id is not None
    assert episode.sample_key is not None
    assert episode.normalized_reward in {0.0, 1.0}
    assert len(episode.root_tasks) == 1

    root = episode.root_tasks[0]
    assert root.parent_task_id is None
    assert root.level == 0
    assert root.actor is not None
    assert root.actor.actor_slug
    assert root.actor.parent_actor_slug is None
    assert sorted(child.task_slug for child in root.children) == sorted(EXPECTED_SUBTASK_SLUGS)

    producer = next(
        child for child in root.children if child.task_slug == EXPECTED_RESOURCE_HANDOFF.producer_slug
    )
    consumer = next(
        child for child in root.children if child.task_slug == EXPECTED_RESOURCE_HANDOFF.consumer_slug
    )
    assert producer.actor is not None
    assert consumer.actor is not None
    assert consumer.actor.parent_actor_slug == root.actor.actor_slug
    assert consumer.parent_task_id == root.task_id
    assert all(attempt.attempt_number >= 1 for attempt in consumer.attempts)

    projector = RlProjectionService()
    timeline = projector.get_joint_timeline(episode)
    assert timeline.records, "expected joint RL timeline records"
    assert all(record.actor.actor_slug for record in timeline.records)
    assert all(record.task_id is not None for record in timeline.records)
    assert all(record.task_attempt_id is not None for record in timeline.records)
    assert timeline.records == sorted(
        timeline.records,
        key=lambda record: (
            record.created_at is None,
            record.created_at,
            record.sequence,
            str(record.task_id),
            str(record.task_attempt_id),
        ),
    )

    actor_spans = list(projector.iter_actor_spans(episode, group_by="actor_slug"))
    assert actor_spans, "expected actor-grouped RL spans"
    root_span = next(span for span in actor_spans if span.key == root.actor.actor_slug)
    assert all(record.actor.actor_slug == root.actor.actor_slug for record in root_span.records)
    assert EXPECTED_SUBAGENT_INTERNAL_MARKER not in [record.text for record in root_span.records]
    assert any(EXPECTED_PARENT_VISIBLE_CHILD_RESULT in record.text for record in root_span.records)
    assert any(EXPECTED_SUBAGENT_INTERNAL_MARKER in record.text for record in timeline.records)

    trajectories = list(projector.iter_task_attempt_trajectories(episode))
    assert trajectories, "expected task-attempt trajectories"
    assert {trajectory.task_slug for trajectory in trajectories} >= {
        EXPECTED_RESOURCE_HANDOFF.producer_slug,
        EXPECTED_RESOURCE_HANDOFF.consumer_slug,
    }
    assert all(trajectory.task_attempt_id is not None for trajectory in trajectories)

    action_records = [record for record in timeline.records if record.step_kind == "action"]
    token_ids = [
        token_id
        for record in action_records
        if record.token_metadata is not None
        for token_id in (record.token_metadata.token_ids or [])
    ]
    logprobs = [
        item.logprob
        for record in action_records
        if record.token_metadata is not None and record.token_metadata.logprobs is not None
        for item in record.token_metadata.logprobs
    ]
    assert EXPECTED_SMOKE_TOKEN_IDS == token_ids[: len(EXPECTED_SMOKE_TOKEN_IDS)]
    assert EXPECTED_SMOKE_LOGPROBS == logprobs[: len(EXPECTED_SMOKE_LOGPROBS)]
```

This assertion should use the new PR-stack RL APIs directly:

- `RlEpisodeReadService.get_episode(sample_id)`
- `RlProjectionService.iter_actor_spans(...)`
- `RlProjectionService.iter_task_attempt_trajectories(...)`
- `RlProjectionService.get_joint_timeline(...)`

Do not assert by scraping raw telemetry tables. If importing production services directly in E2E assertions becomes too heavy, add a thin helper in `ergon_core/ergon_core/test_support/e2e_read_helpers.py` that returns these service DTOs unchanged.

- [ ] **Step 6: Add trainer-facing training-record shape assertion**

In `tests/e2e/_asserts.py`, add a second assertion for the trainer-facing shape produced from the RL view:

```python
def _assert_smoke_training_record_shape(sample_id: UUID) -> None:
    from ergon_core.core.persistence.shared.db import get_session
    from ergon_core.core.rl.rollout_service import _logprobs_for_kind, _token_ids_for_kind
    from ergon_core.core.views.rl.episode import RlEpisodeReadService
    from ergon_core.core.views.rl.projections import RlProjectionService
    from tests.fixtures.smoke_components.smoke_base.constants import (
        EXPECTED_SMOKE_LOGPROBS,
        EXPECTED_SMOKE_TOKEN_IDS,
    )

    with get_session() as session:
        episode = RlEpisodeReadService(session).get_episode(sample_id)

    spans = list(RlProjectionService().iter_actor_spans(episode, group_by="actor_slug"))
    records = []
    for span in spans:
        prompt_ids = _token_ids_for_kind(span.records, "observation")
        completion_ids = _token_ids_for_kind(span.records, "action")
        logprobs = _logprobs_for_kind(span.records, "action")
        if prompt_ids or completion_ids:
            first = span.records[0]
            records.append(
                {
                    "sample_id": sample_id,
                    "actor_slug": first.actor.actor_slug,
                    "base_worker_slug": first.actor.base_worker_slug,
                    "parent_actor_slug": first.actor.parent_actor_slug,
                    "task_id": first.task_id,
                    "task_attempt_id": first.task_attempt_id,
                    "prompt_ids": prompt_ids,
                    "completion_ids": completion_ids,
                    "logprobs": logprobs,
                    "reward": episode.normalized_reward or 0.0,
                }
            )

    assert records, "expected at least one trainer-facing projected record"
    record_with_tokens = next(record for record in records if record["completion_ids"])
    assert record_with_tokens["sample_id"] == sample_id
    assert record_with_tokens["actor_slug"]
    assert record_with_tokens["task_id"] is not None
    assert record_with_tokens["task_attempt_id"] is not None
    assert record_with_tokens["reward"] in {0.0, 1.0}
    assert record_with_tokens["completion_ids"][:3] == EXPECTED_SMOKE_TOKEN_IDS
    assert record_with_tokens["logprobs"][:3] == EXPECTED_SMOKE_LOGPROBS
```

This mirrors the current `RolloutService._build_training_records(...)` behavior without needing to create a rollout batch inside smoke. It specifically asserts the adapter-facing shape:

- sample id
- actor identity
- prompt ids from observation steps
- completion ids/logprobs from action steps
- sample-level normalized reward
- task id and task attempt id

- [ ] **Step 7: Tighten root and intermediate evaluation assertions**

In `tests/e2e/_asserts.py`, extend `_assert_temporal_ordering(sample_id)` or add a new helper. Keep this host-side; the only new runtime evaluator is the single dynamic-subtask evaluator from Task 6.

```python
def _assert_evaluations_after_required_outputs(sample_id: UUID) -> None:
    root_execution, evaluations = list_root_execution_and_evaluations(sample_id)
    assert root_execution is not None
    resources = list_named_resources(
        sample_id,
        prefix=HANDOFF_RESOURCE_NAME.removesuffix(".json"),
        suffix=".json",
    )
    assert resources, "handoff resource missing before evaluation"
    for evaluation in evaluations:
        assert evaluation.created_at >= resources[0].created_at
```

Also assert the intermediary dynamic evaluation exists on happy path:

```python
def _assert_intermediate_evaluation_ordering(sample_id: UUID) -> None:
    snapshot = require_run_snapshot(sample_id)
    consumer = next(
        task
        for task in snapshot.tasks.values()
        if task.name == EXPECTED_RESOURCE_HANDOFF.consumer_slug
    )
    evaluations = snapshot.evaluations_by_task.get(consumer.id, [])
    assert len(evaluations) == 1
    handoffs = list_named_resources(
        sample_id,
        prefix=HANDOFF_RESOURCE_NAME.removesuffix(".json"),
        suffix=".json",
    )
    assert handoffs
    assert evaluations[0].score == 1.0
    assert evaluations[0].created_at >= handoffs[0].created_at
```

The invariant is structural: root and intermediate evaluator rows must not appear before the resources/messages they claim to evaluate. Sad-path smoke should assert there is no successful intermediate evaluation for a blocked or unstarted consumer task.

- [ ] **Step 8: Add deterministic graph/team mutation lane**

In `tests/fixtures/smoke_components/smoke_base/worker_base.py`, add one controlled mutation during parent execution:

```python
# after planning roots, before awaiting children
# Add a transient worker binding or metadata annotation, then remove/supersede it.
await context.record_team_event(
    event_type="worker_binding_added",
    worker_slug="smoke-transient-reviewer",
    reason="smoke mutation lane",
)
await context.record_team_event(
    event_type="worker_binding_removed",
    worker_slug="smoke-transient-reviewer",
    reason="smoke mutation lane complete",
)
```

If no worker/team event API exists, use the closest existing graph mutation API and rename this lane to a graph metadata mutation. The goal is deterministic coverage of add/remove lifecycle visibility, not a new production feature.

- [ ] **Step 9: Assert mutation visibility**

In `tests/e2e/_asserts.py`, add:

```python
def _assert_smoke_dynamic_mutation_events(sample_id: UUID) -> None:
    stream = read_sample_runtime_event_stream(sample_id)
    event_types = [event.event_type for event in stream.events]
    assert "worker_binding_added" in event_types
    assert "worker_binding_removed" in event_types
    assert event_types.index("worker_binding_added") < event_types.index("worker_binding_removed")
```

If the implemented lane uses graph metadata events, assert those concrete event names instead.

- [ ] **Step 10: Wire new assertions into happy and sad smoke tests**

In each E2E smoke file:

```python
_assert_resource_handoff_and_coordination_thread(rid)
_assert_intermediate_handoff_evaluation(rid)
_assert_smoke_rl_view_shape(rid)
_assert_smoke_training_record_shape(rid)
_assert_evaluations_after_required_outputs(rid)
_assert_intermediate_evaluation_ordering(rid)
_assert_smoke_dynamic_mutation_events(rid)
```

For sad path, use sad-specific variants where a blocked task should not have reply/logprob/evaluation artifacts.

- [ ] **Step 11: Verify**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
ergon test smoke
```

Expected: PASS. Failures here are valuable: they indicate the smoke scenario is now catching real resource, message, RL metadata, ordering, or mutation bugs.

- [ ] **Step 12: Commit**

```bash
git add tests/fixtures/smoke_components/smoke_base/constants.py tests/fixtures/smoke_components/smoke_base/leaf_base.py tests/fixtures/smoke_components/smoke_base/worker_base.py tests/e2e/_asserts.py ergon_core/ergon_core/test_support/e2e_read_helpers.py tests/e2e/test_smoke_real_sandbox_posture.py tests/e2e/test_researchrubrics_smoke.py tests/e2e/test_minif2f_smoke.py tests/e2e/test_swebench_smoke.py
git commit -m "test: tighten smoke runtime semantic assertions"
```

---

## Task 9: Update Comments, Docs, And Test Naming Around Smoke Posture

**Files:**
- Modify: `tests/fixtures/smoke_components/sandbox.py`
- Modify: `tests/e2e/test_researchrubrics_smoke.py`
- Modify: `tests/e2e/test_minif2f_smoke.py`
- Modify: `tests/e2e/test_swebench_smoke.py`
- Modify if present: CLI docs mentioning `ergon test smoke`

- [ ] **Step 1: Update stale comments**

Change misleading comments that describe fake sandbox use as intentional canonical smoke behavior. `tests/fixtures/smoke_components/sandbox.py` should say it is legacy/local-unit support only if any references remain.

Use wording like:

```python
"""Legacy local sandbox implementation.

Canonical `ergon test smoke` must use real benchmark sandbox classes.
This module exists only for narrow unit tests that need an in-process
SandboxRuntime without provider access.
"""
```

- [ ] **Step 2: Keep E2E smoke docstrings honest**

For each E2E smoke file, use:

```python
"""<Environment> canonical happy/sad smoke experiment group using real benchmark sandboxes."""
```

- [ ] **Step 3: Run comment/docs-adjacent tests**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/smoke_components/sandbox.py tests/e2e/test_researchrubrics_smoke.py tests/e2e/test_minif2f_smoke.py tests/e2e/test_swebench_smoke.py
git commit -m "docs: clarify smoke sandbox posture"
```

---

## Task 10: Run The Real Smoke Suite Locally

**Files:**
- No code changes expected.

- [ ] **Step 1: Start the dev stack**

Run:

```bash
ergon start
```

Expected: Dashboard, API, Inngest, and Postgres are healthy.

- [ ] **Step 2: Run the new posture contract**

Run:

```bash
uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
```

Expected: PASS.

- [ ] **Step 3: Run canonical smoke**

Run:

```bash
ergon test smoke
```

Expected: PASS for researchrubrics, minif2f, and swebench smoke tests.

Important expected behavior change: this now consumes real sandbox provider resources and can fail for real provider/image/runtime problems. That is the point of this PR.

- [ ] **Step 4: If provider credentials or quota are missing**

Do not weaken `ergon test smoke`. Instead, document the failure clearly in the PR and add/keep a separate local-only smoke command later. The canonical smoke command should remain the real-sandbox confidence check.

- [ ] **Step 5: Commit any final fixes**

```bash
git status --short
git add <changed-files>
git commit -m "test: verify real sandbox smoke suite"
```

---

## Task 11: Push Top-Of-Stack PR

**Files:**
- No code changes expected.

- [ ] **Step 1: Create the branch from the current stack tip**

Run from current PR stack tip:

```bash
git switch codex/episode-sample-pr13-rl-views-stack
git pull --ff-only
git switch -c codex/episode-sample-pr14-real-sandbox-smoke
```

- [ ] **Step 2: Rebase if the lower stack moves**

If PR #132 changes before this PR is opened:

```bash
git fetch origin
git rebase origin/codex/episode-sample-pr13-rl-views-stack
```

- [ ] **Step 3: Push**

```bash
git push -u origin codex/episode-sample-pr14-real-sandbox-smoke
```

- [ ] **Step 4: Open PR**

```bash
gh pr create \
  --base codex/episode-sample-pr13-rl-views-stack \
  --head codex/episode-sample-pr14-real-sandbox-smoke \
  --title "Run canonical smoke tests with real benchmark sandboxes" \
  --body "## Summary
- switches canonical smoke fixtures from fake SmokePublicSandbox to each environment's real sandbox class
- adds posture tests/guards preventing SmokePublicSandbox or TestSandbox from entering canonical smoke task snapshots
- improves smoke root/child task names and descriptions so the real sandbox run catches more realistic task rendering, command, artifact, and dependency bugs
- seeds realistic smoke documents and adds resource-handoff, coordination-thread, RL logprob, root/intermediate evaluation, and dynamic mutation assertions
- adds exactly one dynamic-subtask evaluator for intermediary terminal-state coverage
- exercises production builtin toolkits from deterministic smoke workers for free integration coverage of command/file/report/proof/repo tools
- updates smoke comments/docs so provider coverage is explicit

## Verification
- uv run pytest tests/e2e/test_smoke_real_sandbox_posture.py -q
- ergon test smoke"
```

- [ ] **Step 5: Watch CI**

Run:

```bash
gh pr checks --watch --fail-fast
```

Expected: CI passes. If CI provider resources are missing, treat that as infrastructure/configuration truth, not a reason to silently reintroduce fake sandboxes.

---

## Self-Review

- Spec coverage: The plan changes canonical smoke posture from fake local sandbox to real environment sandbox classes, improves smoke task names/descriptions to cover realistic task rendering and sandbox-runtime behaviors, exercises production builtin toolkits from deterministic smoke workers, adds seeded document/resource/message semantics, asserts RL logprobs and root/intermediate evaluation ordering, adds exactly one dynamic-subtask evaluator for intermediary terminal-state coverage, adds deterministic mutation coverage, guards against fake/test sandboxes, updates comments, and verifies with both a fast contract test and `ergon test smoke`.
- Placeholder scan: No TBD/TODO placeholders remain. Each task has files, code snippets, commands, and expected outcomes.
- Type consistency: Test imports use existing environment class names; sandbox type strings match existing `_type` discriminator format observed in task snapshots; branch base matches the current top-of-stack PR branch.
