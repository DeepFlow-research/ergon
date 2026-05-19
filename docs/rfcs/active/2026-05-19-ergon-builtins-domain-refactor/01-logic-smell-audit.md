# Logic Smell Audit

This audit looks at `ergon_builtins` in `ergon-core-refactor-pr01` as example
code for public authors. The bar is higher than "works": these modules should
model the style we want external benchmark authors to copy.

## Evaluation criteria

For each smell, ask:

1. Is this logic necessary in built-ins at all?
2. If necessary, does it live at the right domain boundary?
3. Could it be expressed with fewer concepts, less inheritance, fewer
   compatibility paths, or simpler Python?
4. Does it depend only on the public API unless it is explicitly an adapter?
5. Would this be a good example for an external benchmark author?

## High-priority smells

### 1. `_manager_backed.py` should become an explicit E2B runtime + E2B sandbox base

File:

- `ergon_builtins/ergon_builtins/sandbox/_manager_backed.py`

Current shape:

- imports `ergon_core.core.shared.settings`
- imports `ergon_core.core.infrastructure.sandbox.manager.BaseSandboxManager`
- defines e2b SDK protocols
- defines two runtime adapters
- creates and binds e2b sandboxes
- owns a workspace bootstrap command
- shells out for direct `list_files`

Necessary parts:

- an E2B-backed implementation of the public `SandboxRuntime` protocol
- optional E2B SDK import handling
- creating a fresh E2B sandbox for `Sandbox.provision()`
- reconnecting to an existing E2B sandbox for `Sandbox.from_definition(..., sandbox_id=...)`
- shared workspace bootstrap

Smells:

- Built-ins reaches into core infrastructure instead of using only public
  sandbox interfaces.
- `_ManagerBackedSandboxRuntime` and `_DirectSandboxRuntime` duplicate
  `run_command`, `write_file`, `read_file`, `sandbox_id`, and `close_local`.
- `cmd: Sequence[str]` is rendered with `" ".join(cmd)`, which is not shell
  safe and gives users the false impression that list-form commands are
  argument-safe.
- `list_files()` in `_DirectSandboxRuntime` interpolates `path` into
  `find {path}` without shell quoting.
- `close()` semantics differ sharply between the two runtime classes:
  manager-backed terminate vs direct kill. The docstring explains it, but the
  type surface does not make lifecycle ownership obvious.
- The module name starts private but is effectively a public built-ins adapter
  used by benchmark sandboxes.
- The real benchmark sandboxes only call `provision_e2b_runtime()` and
  `bind_e2b_runtime()`, both of which return `_DirectSandboxRuntime`.
  `_ManagerBackedSandboxRuntime` is not the production path for built-in E2B
  benchmarks; it appears to support smoke fixtures.
- Every E2B-backed benchmark sandbox repeats the same `provision()` and
  `_bind_runtime()` implementation.

Cleaner expression:

```text
sandbox/
  e2b_runtime.py        # E2BSandboxRuntime, optional import, SDK protocol
  e2b_sandbox.py        # E2BSandbox base class for benchmark sandbox specs
```

The runtime should be one concrete implementation of `SandboxRuntime`:

```python
class E2BSandboxRuntime:
    def __init__(self, sandbox: E2BSandboxHandle) -> None:
        self._sandbox = sandbox
        self.sandbox_id = sandbox.sandbox_id

    @classmethod
    async def create(
        cls,
        *,
        template: str | None,
        envs: dict[str, str] | None,
        timeout_seconds: int | None,
    ) -> "E2BSandboxRuntime":
        sandbox = await create_e2b_sandbox(
            template=template,
            envs=envs,
            timeout_seconds=timeout_seconds,
        )
        await bootstrap_workspace(sandbox)
        return cls(sandbox)

    @classmethod
    async def connect(cls, sandbox_id: str) -> "E2BSandboxRuntime":
        return cls(await connect_e2b_sandbox(sandbox_id))

    async def run_command(...): ...
    async def write_file(...): ...
    async def read_file(...): ...
    async def list_files(...): ...
    async def close(self) -> None: ...
    async def close_local(self) -> None: ...
```

Benchmark-specific E2B sandboxes should inherit a shared base class:

```python
class E2BSandbox(Sandbox):
    template: str | None = None

    async def provision(self) -> None:
        object.__setattr__(self, "_runtime", await self._runtime_create())

    async def _bind_runtime(self, sandbox_id: str) -> None:
        object.__setattr__(self, "_runtime", await self._runtime_connect(sandbox_id))

    async def _runtime_create(self) -> E2BSandboxRuntime:
        return await E2BSandboxRuntime.create(
            template=self.template,
            envs=self.env or None,
            timeout_seconds=self.timeout_seconds,
        )

    async def _runtime_connect(self, sandbox_id: str) -> E2BSandboxRuntime:
        return await E2BSandboxRuntime.connect(sandbox_id)
```

Then benchmark sandboxes become config-only in the common case:

```python
class LeanSandbox(E2BSandbox):
    template: str = "ergon-minif2f-v1"
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"
    lean_version: str = "4.7.0"
```

This removes the misleading manager-backed naming, removes duplicated
provision/bind boilerplate from every benchmark sandbox, and keeps built-ins
from importing `BaseSandboxManager`.

### 2. `cloud_passthrough.py` is probably unnecessary

File:

- `ergon_builtins/ergon_builtins/models/cloud_passthrough.py`

Current shape:

```python
def resolve_cloud(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    return ResolvedModel(model=target, supports_logprobs=False)
```

Necessary parts:

- The behavior is already the fallback behavior of `resolve_model_target()`.

Smells:

- `model_name`, `policy_version`, and `api_key` are unused.
- The docstring says "PydanticAI's infer_model", but the function does not call
  anything; it just returns the string target.
- Keeping this resolver encourages a fake abstraction: it has the same effect
  as doing nothing unless registered elsewhere.

Cleaner expression:

- Delete this file unless there is a real backend registration path that needs
  a callable.
- If a callable is needed for registry symmetry, name it
  `resolve_passthrough_target`, accept only `target`, and document that the
  resolver intentionally returns a string for PydanticAI to infer later.
- If `api_key` support matters, this should not be passthrough; use concrete
  provider adapters such as OpenRouter or OpenAI Responses.

### 3. Model resolution mixes routing, policy, and capture settings

File:

- `ergon_builtins/ergon_builtins/models/resolution.py`

Necessary parts:

- prefix-based resolution is useful
- capture settings are useful for richer transcripts and logprobs

Smells:

- Model policy is embedded in string-prefix checks:
  `claude-opus-4.7`, `anthropic/claude-opus-4`, `openai/gpt-5`,
  `google/gemini-3`, `moonshotai/kimi-k2`.
- `capture_model_settings_for()` knows provider-specific PydanticAI setting
  names for Anthropic, OpenRouter, OpenAI Responses, and Gemini.
- Prefix routing and transcript-capture policy change for different reasons
  but live in one module.

Cleaner expression:

```text
models/
  resolution.py          # resolve target -> ResolvedModel
  capture_settings.py    # target -> model settings
  policies.py            # provider/model policy table
```

Prefer a data table over a chain of prefix checks:

```python
CAPTURE_POLICIES = (
    CapturePolicy(prefix="vllm", requires_logprobs=True, settings=OPENAI_LOGPROBS),
    CapturePolicy(prefix="openai-responses", settings=OPENAI_RESPONSES_REASONING),
    CapturePolicy(prefix="google", settings=GEMINI_THINKING),
)
```

Provider-specific exceptional cases can still be functions, but they should be
named as policy, not hidden inside generic model resolution.

### 4. ResearchRubrics judge criterion crosses the public API boundary

File:

- `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py`

Current shape:

- imports `RunResourceView`
- imports `RunResourceRepository`
- imports `get_session`
- imports `RunResourceKind`
- reads resource files from local paths
- builds prompts
- calls the LLM judge
- formats `CriterionEvidence`

Necessary parts:

- ResearchRubrics needs final report evidence.
- The criterion needs prompt construction and LLM judgment.

Smells:

- Benchmark-specific criterion imports core application and persistence
  internals directly.
- Evidence loading, resource classification, file IO, prompt construction,
  model calling, and outcome construction are all in one class.
- The criterion is hard to unit-test without patching DB/session/file access.
- `rubric_text` mirrors `rubric.criterion`, which is useful for snapshots, but
  currently looks like denormalized state with unclear source of truth.

Cleaner expression:

```text
benchmarks/researchrubrics/criteria/
  judge.py       # Criterion subclass only
  evidence.py    # ResearchRubricsEvidenceLoader / DTOs
  prompts.py     # prompt rendering
```

The criterion should depend on a public context method or an injected loader:

```python
class ResearchRubricsJudgeCriterion(Criterion):
    evidence_loader: ResearchRubricsEvidenceLoader = Field(default_factory=...)

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        evidence = await self.evidence_loader.load(context)
        verdict = await judge_report(...)
        return build_outcome(...)
```

Longer-term, `CriterionContext` should expose a public resource-reading
capability so benchmark criteria do not need repositories or sessions.

### 5. `graph_toolkit.py` is useful behavior, but not library-tier as written

File:

- `ergon_builtins/ergon_builtins/tools/graph_toolkit.py`

Necessary parts:

- agents need run-scoped resource discovery
- graph/resource inspection tools are useful shared built-ins

Smells:

- The toolkit imports repositories, ORM rows, and `get_session` directly.
- Each nested tool repeats budget checking and session access.
- `list_child_resources()` and `list_descendant_resources()` open a new DB
  session for every child/parent iteration.
- Tool construction and graph/resource query logic are coupled in one class.
- It converts ORM rows directly to LLM-facing DTOs, so persistence concepts
  leak into the tool surface.

Cleaner expression:

```text
tools/
  graph_toolkit.py          # pydantic-ai tool builder
  graph_queries.py          # pure-ish query service over public context/port
  graph_tool_responses.py   # LLM-facing DTOs
```

The public tool builder should delegate to a query port:

```python
class ResourceGraphReader(Protocol):
    async def list_resources_for_execution(self, execution_id: UUID) -> list[ResourceRef]: ...
    async def list_descendant_resources(self, root_execution_id: UUID, max_depth: int) -> list[ResourceRef]: ...
```

Then the runtime can provide a repository-backed implementation, and built-ins
can stay library-tier.

### 6. `SubtaskLifecycleToolkit` exposes removed and not-fully-contained tools

File:

- `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`

Necessary parts:

- manager agents need safe subtask lifecycle tools
- using `WorkerContext` as the capability boundary is the right direction

Smells:

- `plan_subtasks` is still exposed but always returns failure saying it was
  removed.
- The class docstring says containment is not fully enforced for some tools.
  This is not example-quality for manager-agent tools.
- Several success DTOs return placeholders such as `old_status="unknown"`,
  `old_description=""`, `invalidated_node_ids=[]`, and `cascaded_count=0`.
- Broad `except Exception` wraps every tool, which is acceptable at an LLM tool
  boundary, but should be normalized through one helper rather than repeated.

Cleaner expression:

- Delete `plan_subtasks` from the built tool list if it is removed.
- Do not expose cancel/refine/restart/get unless `WorkerContext` guarantees
  subtree containment.
- Return accurate operation results from `WorkerContext` instead of placeholder
  fields, or simplify response models to only fields the tool truly knows.
- Centralize error wrapping:

```python
async def _run_tool(operation: Awaitable[T]) -> T | ToolFailure:
    try:
        return await operation
    except ValueError as exc:
        return ToolFailure(error=str(exc))
```

### 7. `ReActWorker` has stale imports and a too-magical final-output path

File:

- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`

Necessary parts:

- A reusable ReAct worker is a good shared built-in.
- Transcript adapter usage is needed for generation capture.

Smells:

- Imports `ContextEventService`, `Session`, `Field`, and `UUID` but does not use
  them.
- Imports context part models from `ergon_core.core.domain...`, not public API.
- `_run_agent()` mixes model resolution, Logfire configuration, agent
  construction, iteration, transcript flushing, iteration-limit handling, and
  final output extraction.
- `_latest_final_result_message()` depends on the pydantic-ai structured output
  appearing as a tool call named `final_result`; this is subtle and not obvious
  from the worker API.

Cleaner expression:

```text
workers/
  react_worker.py
  react_agent.py          # build_agent(...)
  react_transcript.py     # run and stream transcript chunks
  react_output.py         # final output extraction
```

At minimum:

- remove unused imports
- move final-output extraction into a named helper module with tests
- prefer public API imports for transcript chunk types, or add a public core
  export if none exists

### 8. `_tools.py` modules are the clearest repeated code smell

Files:

- `benchmarks/minif2f/_tools.py`
- `benchmarks/gdpeval/_tools.py`
- `benchmarks/swebench_verified/_tools.py`
- `benchmarks/researchrubrics/_tools.py`

Necessary parts:

- runtime tool builders should remain lazy so serializable toolkit configs do
  not import heavy runtime dependencies too early

Smells:

- each file mixes response models, sandbox operations, parsing helpers, and
  pydantic-ai `Tool` construction
- nested functions make the actual domain operations hard to test directly
- many operations catch broad exceptions and return typed failure responses
  without a shared convention
- some command paths interpolate user-provided file paths or commands
- MiniF2F has an explicit TODO saying this should be broken down

Cleaner expression:

For each benchmark:

```text
tools/
  response_models.py
  operations.py
  tool_builder.py
```

The tool builder should only adapt operation functions into pydantic-ai tools:

```python
def build_tools(toolkit: MiniF2FToolkit, *, sandbox: Sandbox, task: Task) -> list[Tool]:
    ops = LeanOperations(sandbox=sandbox, workspace=toolkit.lean_workspace)
    return [
        Tool(function=ops.write_file, takes_ctx=False),
        Tool(function=ops.check_file, takes_ctx=False),
    ]
```

### 9. `workers/research_rubrics/_run_skill.py` appears obsolete or mislabeled

File:

- `ergon_builtins/ergon_builtins/workers/research_rubrics/_run_skill.py`

Current shape:

- docstring says this is a stub skill runner that asks the model to produce
  plausible tool responses instead of calling real tools
- imports benchmark toolkit response models
- constructs a fresh pydantic-ai agent per skill call

Smells:

- If object-bound ResearchRubrics workers now use benchmark-local toolkits,
  this old worker package may not be necessary.
- A stub runner that simulates tool calls with another LLM is a surprising
  library-tier example unless it is explicitly a test fixture.
- It lives under `workers/research_rubrics`, while the RFC target says
  benchmark-specific worker/tool behavior belongs under
  `benchmarks/researchrubrics`.

Cleaner expression:

- Delete it if no active imports need it.
- If still needed for tests, move to `tests/fixtures` or a clearly named
  `benchmarks/researchrubrics/testing.py`.
- If needed as a real fallback mode, rename it to make the behavior explicit,
  e.g. `synthetic_skill_runner.py`, and document why simulated tools are
  acceptable.

### 10. Compatibility import surfaces should be retired aggressively

Files/packages:

- `ergon_builtins/shared/criteria/*`
- `ergon_builtins/shared/workers/*`
- `ergon_builtins/shared/models/*`
- `ergon_builtins/evaluators/rubrics/swebench_rubric.py`
- `ergon_builtins/evaluators/criteria/*`
- `ergon_builtins/workers/baselines/*`

Smells:

- Some are one-line re-exports.
- Some benchmark code still imports through old locations.
- The package offers multiple plausible import paths for the same concept.

Cleaner expression:

- Pick canonical concept packages:
  `workers`, `models`, `tools`, `sandbox`, `common`, `observability`,
  and `benchmarks/<slug>`.
- Update imports in one PR.
- Add architecture tests that reject imports from compatibility packages.

### 11. `ReActWorker` stores runtime tools on mutable private state

File:

- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`

Current shape:

```python
if self.toolkit is not None and task.sandbox is not None:
    self._tools = list(self.toolkit.tools(task.sandbox, task))
async for chunk in self._run_agent(task, context):
    yield chunk
```

Necessary parts:

- `ReActWorker` needs benchmark-specific runtime tools.
- Toolkit config needs to round-trip in task JSON.

Smells:

- Runtime tools are written onto `self._tools` before execution. That makes a
  Pydantic model instance carry per-run mutable state.
- If the same worker instance is ever reused concurrently, tools from one task
  can bleed into another task.
- `_run_agent()` reads `self._tools` implicitly instead of receiving the tools
  it should use.
- `_seed_messages` has the same hidden runtime-state smell.

Cleaner expression:

Pass runtime-only values as local variables:

```python
async def execute(self, task: Task, *, context: WorkerContext) -> AsyncGenerator[WorkerStreamItem, None]:
    tools = self._build_tools(task)
    seed_messages = self._build_seed_messages(task, context)
    async for chunk in self._run_agent(task, context, tools=tools, seed_messages=seed_messages):
        yield chunk
```

Then `_run_agent()` becomes a pure execution helper for one run rather than a
method that depends on mutable private attributes.

### 12. `ReActWorker` has no explicit behavior for missing toolkit sandbox

File:

- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`

Current behavior:

- if `toolkit is not None` but `task.sandbox is None`, the worker silently runs
  with no tools

Smell:

- A benchmark-specific ReAct worker with a toolkit almost certainly requires a
  live sandbox. Running without tools produces confusing model behavior instead
  of an immediate authoring/runtime error.

Cleaner expression:

```python
def _build_tools(self, task: Task) -> list[AgentTool]:
    if self.toolkit is None:
        return []
    if task.sandbox is None:
        raise ValueError(f"{self.name} has a toolkit but task {task.task_slug!r} has no sandbox")
    return list(self.toolkit.tools(task.sandbox, task))
```

This makes the failure mode crisp and teaches external authors the expected
contract.

### 13. `ReActWorker` imports core internals and stale dependencies

File:

- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`

Smells:

- imports `AssistantTextPart`, `ContextPartChunk`, and `ToolCallPart` from
  `ergon_core.core.domain.generation.context_parts`
- imports `ContextEventService`, `Field`, `Session`, and `UUID` but does not use
  them

Cleaner expression:

- remove stale imports immediately
- expose generation chunk types through `ergon_core.api` or
  `ergon_core.api.worker` if built-ins workers are expected to yield them
- update built-ins to import only the public generation/worker API

This may require a small core API export before built-ins can fully stop
importing `ergon_core.core.domain.generation.context_parts`.

### 14. `ReActWorker` final-output extraction is too implicit

File:

- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`

Current shape:

- pydantic-ai structured output appears as a `final_result` tool call
- `_latest_final_result_message()` finds that tool call by name and pulls
  `final_assistant_message`
- if not found, worker falls back to the last assistant text chunk

Smells:

- The worker's success result depends on a magic tool-call name.
- The fallback can mark success from ordinary assistant text even if structured
  output failed.
- The extraction behavior is important enough to deserve direct tests and a
  named module.

Cleaner expression:

```text
workers/
  react_output.py
```

```python
def worker_output_from_chunks(chunks: Sequence[ContextPartChunk]) -> WorkerOutput:
    structured = latest_structured_final_result(chunks)
    if structured is not None:
        return WorkerOutput(output=structured.final_assistant_message, success=True)
    assistant_text = latest_assistant_text(chunks)
    if assistant_text is not None:
        return WorkerOutput(output=assistant_text, success=True, metadata={"source": "assistant_text_fallback"})
    return WorkerOutput(output="", success=False, metadata={"source": "missing_final_output"})
```

The fallback source should be visible in metadata.

### 15. `TrainingStubWorker` is random, which makes it weaker as a test fixture

File:

- `ergon_builtins/ergon_builtins/workers/baselines/training_stub_worker.py`

Necessary parts:

- A synthetic worker that emits multi-turn chunks and logprobs is useful for
  RL and generation-extraction tests.

Smells:

- It uses global `random` directly.
- Number of turns, number of tokens, and logprobs vary on every run.
- This makes snapshots and regression tests noisier than necessary.
- It imports generation chunk types from core internals.

Cleaner expression:

Add explicit config:

```python
class TrainingStubWorker(Worker):
    type_slug: ClassVar[str] = "training-stub"
    name: str = "training-stub"
    seed: int = 0
    min_turns: int = 2
    max_turns: int = 3
    min_tokens: int = 8
    max_tokens: int = 16
```

Then use a local RNG:

```python
rng = random.Random(f"{self.seed}:{task.task_slug}")
chunks = _build_synthetic_chunks(task.task_slug, rng=rng, ...)
```

This keeps the worker synthetic while making it deterministic per task.

### 16. Benchmark worker factories hard-code default models inconsistently

Files:

- `benchmarks/minif2f/workers.py`
- `benchmarks/swebench_verified/workers.py`
- `benchmarks/gdpeval/workers.py`
- `benchmarks/researchrubrics/workers.py`

Current shape:

- MiniF2F hard-codes `openai:gpt-4o-mini` with no override argument.
- SWE-Bench, GDPEval, and ResearchRubrics accept `model` and
  `max_iterations`.
- worker names vary (`solver`, `swebench-solver`, `gdpeval-runner`,
  `research-runner`).
- prompts for MiniF2F/SWE live in shared `react_prompts`; prompts for GDP and
  ResearchRubrics live inline in worker factory modules.

Smells:

- Examples teach inconsistent factory signatures.
- The default model choice is repeated instead of named once.
- Prompt location is inconsistent.
- `workers.py` also exports rubric factories, so "worker factory" modules are
  really "component factory" modules.

Cleaner expression:

```python
DEFAULT_WORKER_MODEL = "openai:gpt-4o-mini"

def make_minif2f_worker(
    *,
    model: str = DEFAULT_WORKER_MODEL,
    max_iterations: int = 30,
) -> ReActWorker: ...
```

Move prompts to benchmark-local `prompts.py`:

```text
benchmarks/minif2f/prompts.py
benchmarks/swebench_verified/prompts.py
benchmarks/gdpeval/prompts.py
benchmarks/researchrubrics/prompts.py
```

And decide whether rubric factories belong in:

- `worker_factory.py` only if the file becomes `factories.py`, or
- `rubric.py` / `rubric_factory.py` if we want names to stay precise

### 17. `Toolkit` depends on core private serialization helpers

File:

- `ergon_builtins/ergon_builtins/workers/baselines/toolkit.py`

Necessary parts:

- Toolkit configs need to serialize with a concrete type discriminator so
  object-bound workers round-trip.

Smells:

- Imports `TaskDefinitionJson` and `import_component_subclass` from
  `ergon_core.api._serialization`, which is a private API module by name.
- `tools(self, sandbox: Any, task: Any) -> list` loses type information at the
  key worker/tool boundary.

Cleaner expression:

- promote the serialization helper needed by external authoring components to a
  public API location, or create a small built-ins-local helper rather than
  importing `_serialization`
- type the tool boundary with public protocols:

```python
class Toolkit(BaseModel, ABC):
    @abstractmethod
    def tools(self, sandbox: Sandbox, task: Task) -> Sequence[AgentTool]: ...
```

If importing `Task` causes cycles, define a tiny public protocol for the fields
toolkits use.

## Lower-priority cleanups

### Generated/source-trash artifacts

The branch contains generated artifacts and stray files:

- `__pycache__` directories
- `.pyc` files
- `benchmarks/gdpeval/Untitled`

These should not exist in a library-tier example package. Delete them and add a
test or repository hygiene check that rejects them.

### Optional dependency handling

Optional imports are fine, but each optional boundary should have one clean
pattern:

- import lazily inside the function that needs the optional package, or
- define a dedicated adapter module with a single helpful installation error

`_manager_backed.py` currently mixes optional import fallback classes, dynamic
module import, and runtime configuration in the same file. Prefer a small
`e2b_sdk.py` adapter.

### Broad exceptions at tool boundaries

Broad exception handling is often reasonable for LLM-facing tools: a tool
should return a typed failure instead of crashing the whole agent loop. But it
should be deliberate and consistent.

Recommendation:

- broad exceptions are allowed only inside LLM tool call boundaries
- internal operation functions should raise typed exceptions or return typed
  results
- a shared helper should convert exceptions to failure responses

## Suggested cleanup sequence

### PR 1: Hygiene and dead surface audit

- delete generated artifacts and `Untitled`
- remove unused imports in `ReActWorker`
- delete `cloud_passthrough.py` if no active imports require it
- add architecture tests for generated artifacts and compatibility imports

### PR 2: Canonical import paths

- move `workers/baselines/*` to `workers/*`
- move benchmark `workers.py` files to `worker_factory.py`
- update imports
- delete `shared/workers` and `shared/models`

### PR 3: Benchmark-local tools

- split one benchmark `_tools.py` into `tools/response_models.py`,
  `tools/operations.py`, and `tools/tool_builder.py`
- use that as the template for the other benchmarks
- start with MiniF2F because the TODO already marks the issue and the domain
  is compact

### PR 4: Criteria boundary cleanup

- move MiniF2F `rules/proof_verification.py` into
  `criteria/proof_verification.py`
- move SWE-Bench `criterion.py` into `criteria/test_resolution.py`
- split ResearchRubrics judge into `criteria/judge.py`,
  `criteria/evidence.py`, and `criteria/prompts.py`

### PR 5: Core boundary adapters

- replace direct repository/session imports in benchmark criteria and shared
  tools with public context capabilities or injected ports
- decide whether graph/resource tools belong in built-ins or core

### PR 6: Sandbox adapter simplification

- replace `_manager_backed.py` with `sandbox/e2b_runtime.py` and
  `sandbox/e2b_sandbox.py`
- introduce `E2BSandboxRuntime`
- introduce `E2BSandbox`
- make MiniF2F, SWE-Bench, ResearchRubrics, and GDPEval sandboxes inherit from
  `E2BSandbox`
- remove duplicated benchmark `provision()` and `_bind_runtime()` methods
- quote shell paths
- remove built-ins imports of `BaseSandboxManager`

## Proposed architecture tests

Add tests that fail when:

- `ergon_builtins` contains `__pycache__`, `.pyc`, or files named `Untitled`
- benchmark packages import `ergon_core.core.persistence`
- benchmark packages import `ergon_core.core.application` except through
  explicitly approved public facade adapters
- benchmark criteria import repositories or `get_session`
- source imports from `ergon_builtins.shared`
- source imports from `ergon_builtins.evaluators`
- benchmark packages import `ergon_builtins.workers.baselines`
- source imports from `ergon_builtins.sandbox._manager_backed`
- benchmark E2B sandbox subclasses override `provision()` or `_bind_runtime()`
  without an explicit justification comment

These tests are cheap and will keep the example package from drifting back
into migration-mode code.
