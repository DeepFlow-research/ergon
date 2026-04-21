---
status: open
opened: 2026-04-21
fixed_pr: null
priority: P2
invariant_violated: docs/architecture/03_providers.md#21-generation-registry
related_rfc: null
---

# Bug: `stub:constant` model backend is not registered

## Symptom

The real-LLM harness canary at `tests/real_llm/benchmarks/test_smoke_stub.py:70`
invokes the CLI with `--model stub:constant`, yet no backend resolver is
registered for the `stub:` prefix in the generation registry
(`ergon_builtins/ergon_builtins/registry_core.py:97-102` — only `vllm`,
`openai`, `anthropic`, `google` are registered; `ergon_builtins/ergon_builtins/registry_local_models.py`
adds `transformers`).

Today the canary still passes because `StubWorker` never calls
`resolve_model_target` — `stub_worker.py:12-27` only accepts the `model`
kwarg for signature compatibility and discards it. The bug is therefore a
latent one: any future consumer (telemetry, provenance, or a worker that
swaps to `resolve_model_target`) will silently fall through to the
unregistered-prefix branch at
`ergon_core/ergon_core/core/providers/generation/model_resolution.py:70`,
returning a pass-through `ResolvedModel(model="stub:constant", ...)`.
If anything then hands that string to PydanticAI's `infer_model`, it will
raise at call time because `stub:` is not a PydanticAI scheme.

## Repro

1. Import `resolve_model_target` after builtins are loaded.
2. Call `resolve_model_target("stub:constant")`.
3. Observe the returned `ResolvedModel` holds the literal string
   `"stub:constant"` (no backend matched); this string is not a valid
   PydanticAI model identifier.

Equivalent code path is exercised by the canary at
`tests/real_llm/benchmarks/test_smoke_stub.py` (it only passes because
the stub worker bypasses resolution).

## Root cause

The `stub:` prefix is absent from `MODEL_BACKENDS` in
`ergon_builtins/ergon_builtins/registry_core.py:97-102`. The canary
(`tests/real_llm/benchmarks/test_smoke_stub.py:70`) and the unit test at
`tests/unit/test_cli_react_generic_composition.py:10` both use
`"stub:constant"` as though it were registered. `StubWorker`
(`ergon_builtins/ergon_builtins/workers/baselines/stub_worker.py:12-27`)
accepts `model` but never resolves it, so the canary is incidentally
safe — but this is coupling by accident, not by design.

The providers doc
(`docs/architecture/03_providers.md:26`) enumerates the registered
prefixes and does not list `stub`, confirming the discrepancy.

## Scope

- Every real-LLM canary run (`tests/real_llm/benchmarks/test_smoke_stub.py`).
- Every unit test composing an experiment with `model="stub:constant"`
  (`tests/unit/test_cli_react_generic_composition.py:10`).
- Anything that introspects or resolves the model target off the CLI args
  before worker execution (telemetry, logging, provenance) would observe
  the pass-through `ResolvedModel` with a non-PydanticAI string and fail
  downstream.

Today: zero user-visible failures because no such consumer exists on the
stub path. Tomorrow: the first consumer that adds `resolve_model_target`
or provenance plumbing over the stub path will trip.

## Proposed fix

Register a `stub:` backend resolver
(`ergon_builtins/ergon_builtins/models/stub_constant_backend.py`) that
returns a deterministic `ResolvedModel` containing a fixed constant
string. Wire it into `MODEL_BACKENDS` in `registry_core.py` keyed on
`"stub"`. This makes the `stub:constant` convention explicit, keeps
resolution total (no silent pass-through), and gives tests/telemetry
something sensible to observe. Update `docs/architecture/03_providers.md`
to list the new prefix.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Confirm `docs/architecture/03_providers.md` lists `stub:*` as a
    registered prefix.
