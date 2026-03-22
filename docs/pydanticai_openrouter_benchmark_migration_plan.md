# PydanticAI + OpenRouter Benchmark Migration Plan

This document captures the narrow migration scope for moving Arcane's benchmark runtime from the OpenAI Agents SDK to PydanticAI, while using OpenRouter-style model names directly.

This is not a benchmark architecture rewrite.

The intent is:

- keep the existing benchmark architecture
- keep the existing `ReActWorker` class
- keep the existing toolkit and stakeholder abstractions
- swap the OpenAI Agents SDK internals for PydanticAI
- use OpenRouter model names directly instead of adding a broader model abstraction layer

## Scope

This migration is intentionally small in architectural scope.

We are not trying to introduce:

- a new worker class
- a model resolver
- a content builder abstraction
- a typed history persistence layer
- a broad re-think of benchmark orchestration

We are only trying to replace the engine inside the current setup.

## What Stays The Same

The following parts of the benchmark system should remain structurally unchanged:

- `h_arcane/benchmarks/common/workers/react_worker.py` remains the main worker type
- `h_arcane/core/_internal/agents/base.py` remains the main toolkit/stakeholder contract layer
- benchmark-specific toolkits stay in `h_arcane/benchmarks/*/toolkit.py`
- benchmark-specific stakeholders stay in `h_arcane/benchmarks/*/stakeholder.py`
- benchmark registry wiring stays in `h_arcane/benchmarks/registry.py`
- benchmark run orchestration stays in `h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py`
- worker execution orchestration stays in `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `WorkerResult`, `WorkerExecutionOutput`, `QAExchange`, and `Action` remain the core execution contracts

The migration should preserve the current runtime shape and only replace the OpenAI-specific guts.

## What Changes

Only a few focused implementation areas need to change.

### 1. `ReActWorker` internals

The `ReActWorker` class should remain, but its internals should stop using:

- `agents.Agent`
- `Runner.run`
- OpenAI Agents SDK result item types

Instead, it should:

- create and run a PydanticAI agent
- keep using the current benchmark prompt as the system prompt
- keep using the toolkit-provided tools
- keep returning `WorkerResult`
- keep using `WorkerExecutionOutput` as the final typed output if possible

In short: same class, new engine.

### 2. Toolkit tool registration

Benchmark toolkits should keep their structure and tool logic, but stop using:

- `agents.function_tool`
- OpenAI Agents SDK tool objects

The migration should replace only the registration/wrapping mechanism with the PydanticAI equivalent.

The actual tool bodies should remain as unchanged as possible.

That applies to:

- `h_arcane/benchmarks/gdpeval/toolkit.py`
- `h_arcane/benchmarks/minif2f/toolkit.py`
- `h_arcane/benchmarks/researchrubrics/toolkit.py`
- `h_arcane/benchmarks/smoke_test/toolkit.py`

### 3. Model strings

The system should use OpenRouter-style model names directly.

Examples:

- `openrouter:openai/gpt-5`
- `openrouter:anthropic/claude-3.7-sonnet`
- `openrouter:google/gemini-2.5-pro`

There is no need to add a model resolver unless direct model naming becomes painful later.

### 4. Stakeholder transport

Stakeholder classes can remain as they are conceptually, but their transport layer should stop depending directly on OpenAI-specific client usage where necessary.

Current direct usage exists in:

- `h_arcane/benchmarks/minif2f/stakeholder.py`
- `h_arcane/benchmarks/gdpeval/stakeholder.py`
- `h_arcane/benchmarks/researchrubrics/stakeholder.py`

The migration goal is not to redesign stakeholders, only to make their underlying LLM calls compatible with the new OpenRouter-based setup.

### 5. Evaluation runtime

The benchmark migration may also require a follow-up cleanup in:

- `h_arcane/core/_internal/evaluation/runtime.py`

But this should be treated as secondary to getting benchmark execution working.

## Main OpenAI-Specific Coupling Points

The current benchmark runtime is tied to OpenAI-specific infrastructure in a few concentrated places:

- `agents.Agent` and `Runner.run` in `h_arcane/benchmarks/common/workers/react_worker.py`
- `agents.function_tool` in benchmark toolkit implementations
- `AsyncOpenAI` in stakeholder implementations
- `openai_api_key`-oriented settings in `h_arcane/core/settings.py`
- OpenAI structured parsing in `h_arcane/core/_internal/evaluation/runtime.py`

These are the seams where migration work should happen.

## Migration Plan

The work should happen in a small number of focused steps.

### Phase 1: Update runtime dependencies and settings

Add the dependencies and settings needed for PydanticAI + OpenRouter.

Work items:

- add the relevant PydanticAI dependency
- add any OpenRouter-related environment variable support needed in `h_arcane/core/settings.py`
- confirm what model string format PydanticAI expects in practice for OpenRouter-backed execution

Goal:

- make the runtime capable of calling OpenRouter-backed models without changing benchmark logic yet

### Phase 2: Refactor `ReActWorker` to use PydanticAI

This is the core of the migration.

Work items:

- replace OpenAI Agents SDK agent creation with PydanticAI agent creation
- replace `Runner.run(...)` with the PydanticAI execution path
- preserve the current `execute()` signature and return type
- preserve current task prompt formatting
- preserve extraction of final `reasoning` and `output_text`

Goal:

- keep `ReActWorker` as the benchmark worker, but run it on PydanticAI internally

### Phase 3: Port toolkit tool wrappers

This should be a mostly mechanical refactor.

Work items:

- remove `function_tool` usage
- register tools the way PydanticAI expects
- keep the underlying async tool bodies the same
- keep stakeholder question handling and sandbox behavior the same

Goal:

- preserve benchmark toolkit behavior while swapping the agent runtime

### Phase 4: Rebuild action extraction for PydanticAI events

This is likely the trickiest part of the migration.

Today `ReActWorker` extracts actions from OpenAI Agents SDK item types such as:

- messages
- reasoning items
- tool calls
- tool call outputs

PydanticAI exposes a different execution/event model, so `ReActWorker` will need a new translation layer that maps PydanticAI activity into the existing `Action` schema.

Goal:

- preserve dashboard events, persistence, and tracing semantics without changing downstream systems

### Phase 5: Update stakeholder transport if required

If the stakeholder implementations cannot cleanly continue using their current client approach under the new model naming/runtime assumptions, update only their transport path.

Goal:

- keep stakeholder prompts and benchmark-specific behavior intact
- only change how stakeholder LLM calls are issued

### Phase 6: Clean up evaluation runtime separately

After benchmark execution works, clean up any remaining OpenAI-specific judge/runtime code in:

- `h_arcane/core/_internal/evaluation/runtime.py`

This should be a second-pass cleanup, not a prerequisite for the benchmark runtime migration.

## Non-Goals

The following are explicitly out of scope for this migration:

- redesigning the benchmark architecture
- replacing `ReActWorker` with a differently named worker abstraction
- adding a model resolver layer
- adding a multimodal content abstraction layer
- adding typed chat history persistence
- redesigning benchmark toolkits or stakeholder semantics
- changing benchmark orchestration flow

If any of those become necessary, they should be treated as separate follow-up work rather than bundled into this migration.

## Suggested Rollout Order

The rollout should start with the smallest proof point and then expand.

### 1. `smoke_test`

Use this to prove:

- `ReActWorker` still works after the internal runtime swap
- tools still execute correctly
- `Action` rows still persist correctly
- dashboard events still look correct

This is the safest first migration target.

### 2. `gdpeval`

Use this to prove:

- richer tool use still works
- file and artifact workflows still work
- OpenRouter-backed non-OpenAI models can be exercised in a realistic benchmark

### 3. `researchrubrics`

Use this to prove:

- longer tool loops still behave correctly
- stakeholder clarification still works
- model/provider flexibility is actually useful in practice

### 4. `minif2f`

Use this after the runtime swap and toolkit refactor are stable.

This benchmark should be migrated after the general execution path is proven out.

### 5. Evaluation and judge flows

Treat these as follow-up work after benchmark runtime parity is established.

## Biggest Risks

### 1. Action extraction parity

The current dashboard and persistence model depends on the existing `Action` extraction behavior in `ReActWorker`.

That means the key technical risk is not "can PydanticAI call tools?" but:

- can we map its execution model cleanly back into the current `Action` schema?

### 2. Tool registration differences

Toolkit logic is already benchmark-specific and works today.

The migration risk is mainly in:

- how tools are registered
- what metadata PydanticAI exposes for calls and results

### 3. Stakeholder transport mismatch

Even if benchmark execution is migrated cleanly, stakeholder implementations may still remain coupled to direct OpenAI client usage.

That should be treated as a contained transport cleanup, not a redesign.

### 4. Scope creep

The biggest non-technical risk is turning this into a broader architecture rewrite.

The correct target is:

- same architecture
- same worker abstraction
- same benchmark logic
- different agent runtime under the hood

## Concrete First Sprint

The first sprint should stay narrow.

Scope:

- add the PydanticAI dependency
- add OpenRouter-related settings support
- refactor `ReActWorker` to use PydanticAI internally
- port `smoke_test` toolkit tool registration
- get one benchmark run working end to end
- confirm `Action` persistence and dashboard output still make sense

That is enough to validate the direction without over-committing to broader changes.

## File-By-File Checklist

This section turns the migration into a concrete edit list.

### 1. Dependency and settings updates

Files:

- `pyproject.toml`
- `h_arcane/core/settings.py`
- `.env.example` if applicable

Changes:

- add the PydanticAI dependency
- add any OpenRouter API key setting needed by the runtime
- document the expected environment variable names
- confirm the model string format that will be passed through the system

Done when:

- the project can import PydanticAI successfully
- the runtime can read the OpenRouter API key from settings

### 2. Swap the guts of `ReActWorker`

File:

- `h_arcane/benchmarks/common/workers/react_worker.py`

Changes:

- remove OpenAI Agents SDK imports
- add PydanticAI imports
- replace OpenAI agent construction with PydanticAI agent construction
- replace `Runner.run(...)` with the PydanticAI execution path
- preserve task prompt formatting
- preserve final structured output extraction into `WorkerExecutionOutput`
- preserve `WorkerResult` construction

Done when:

- `ReActWorker.execute()` still has the same signature
- benchmark runs still produce `WorkerResult`
- no downstream runtime files need interface changes just because the worker internals changed

### 3. Rebuild action extraction

File:

- `h_arcane/benchmarks/common/workers/react_worker.py`

Changes:

- replace OpenAI item-type based action extraction
- map PydanticAI execution events into the existing `Action` schema
- preserve message actions
- preserve tool-call actions
- preserve reasoning capture where available
- preserve token and cost accounting if still feasible

Done when:

- persisted `Action` rows still look correct
- dashboard action streaming still makes sense
- tracing spans still reflect tool activity in the expected order

### 4. Port toolkit registration for `smoke_test`

File:

- `h_arcane/benchmarks/smoke_test/toolkit.py`

Changes:

- remove `function_tool`
- register tools using the PydanticAI-compatible pattern
- keep tool logic unchanged where possible

Done when:

- `smoke_test` is the first benchmark that runs end to end on the new internals

### 5. Port toolkit registration for benchmark toolkits

Files:

- `h_arcane/benchmarks/gdpeval/toolkit.py`
- `h_arcane/benchmarks/minif2f/toolkit.py`
- `h_arcane/benchmarks/researchrubrics/toolkit.py`

Changes:

- replace OpenAI Agents SDK tool wrappers
- keep benchmark-specific logic and sandbox calls unchanged
- verify that `ask_stakeholder` still behaves the same way

Done when:

- all toolkits expose tools in the new format without changing benchmark semantics

### 6. Update stakeholder transport only if needed

Files:

- `h_arcane/benchmarks/minif2f/stakeholder.py`
- `h_arcane/benchmarks/gdpeval/stakeholder.py`
- `h_arcane/benchmarks/researchrubrics/stakeholder.py`

Changes:

- keep prompts and benchmark behavior the same
- update the client path only if OpenRouter-backed execution requires it
- avoid introducing broader stakeholder abstraction work unless forced by implementation needs

Done when:

- stakeholders still answer benchmark questions correctly under the new model/runtime setup

### 7. Clean up evaluation later

File:

- `h_arcane/core/_internal/evaluation/runtime.py`

Changes:

- remove OpenAI-specific parsing only after benchmark execution migration is proven

Done when:

- evaluation no longer depends on OpenAI-only structured parsing paths

## Recommended Edit Order

The safest implementation sequence is:

1. Update `pyproject.toml` and `h_arcane/core/settings.py`
2. Refactor `h_arcane/benchmarks/common/workers/react_worker.py`
3. Port `h_arcane/benchmarks/smoke_test/toolkit.py`
4. Run `smoke_test` successfully
5. Fix `Action` extraction and dashboard/tracing parity issues
6. Port the remaining benchmark toolkits
7. Clean up stakeholder transport only where it blocks the migration
8. Tackle evaluation runtime separately

## Review Checklist

When reviewing the implementation, these are the questions that matter most:

- Does `ReActWorker` still look like the same public worker, just with different internals?
- Are toolkit changes mostly wrapper-level rather than logic rewrites?
- Do model strings pass through directly as OpenRouter-style names?
- Do `Action` rows still capture message, reasoning, and tool activity in a useful way?
- Does `smoke_test` pass before the more complex benchmarks are migrated?
- Have we avoided introducing extra abstractions that are not required for this migration?

## Practical Recommendation

Treat this migration as:

1. keep the benchmark architecture
2. keep `ReActWorker`
3. replace OpenAI Agents SDK internals with PydanticAI
4. use OpenRouter-style model names directly
5. clean up remaining OpenAI-specific surfaces only where necessary

That keeps the work aligned with the actual goal and avoids an unnecessary redesign.
