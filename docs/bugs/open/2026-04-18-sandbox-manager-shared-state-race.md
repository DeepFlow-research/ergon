---
status: open
opened: 2026-04-18
fixed_pr: null
priority: P3
invariant_violated: docs/architecture/03_providers.md#sandboxeventsink
related_rfc: docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md
---

# Bug: `BaseSandboxManager` singleton + `__init__` stomp races across construction sites

## Symptom

`BaseSandboxManager.__init__` unconditionally overwrites `self._event_sink` whenever a
non-None `event_sink` is passed
(`ergon_core/ergon_core/core/providers/sandbox/manager.py:76-78`):

```python
def __init__(self, event_sink: SandboxEventSink | None = None):
    if event_sink is not None:
        self._event_sink = event_sink
```

Combined with the singleton-per-subclass pattern at `manager.py:69-72`:

```python
def __new__(cls, *args, **kwargs):
    if cls._instance is None:
        cls._instance = super().__new__(cls)
    return cls._instance
```

— every re-construction of the same subclass returns the SAME instance and re-runs
`__init__`, so any second construction with a different `event_sink=` silently replaces
the first. Class-level state dicts (`_sandboxes`, `_run_ids`,
`_creation_locks` at `manager.py:61-66`) are also shared, so all tasks funneled through
any construction site operate on the same cross-context registries.
(`_display_task_ids` was removed by `docs/rfcs/accepted/2026-04-18-sandbox-manager-key-cleanup.md`; the remaining five dicts are still addressed by the process-state RFC.)

No production site hits this today: all 5 construction sites
(`ergon_builtins/workers/baselines/minif2f_react_worker.py:111`,
`ergon_builtins/workers/baselines/swebench_worker.py:123`,
`ergon_builtins/benchmarks/swebench_verified/criterion.py:72`,
`ergon_builtins/workers/research_rubrics/researcher_worker.py:74`,
`ergon_builtins/workers/research_rubrics/stub_worker.py:78`) construct without args, and
`dashboard_emitter` is a process-wide singleton
(`ergon_core/ergon_core/core/dashboard/emitter.py:451`) — so swapping one
`DashboardEmitterSandboxEventSink` for another is an identity substitution in effect.
The latent race is real but currently masked by the uniform argument-less construction.

## Repro

Conceptual — no production repro exists; this documents the hazard:

```python
sink_a = RecordingSandboxEventSink()
sink_b = DashboardEmitterSandboxEventSink(dashboard_emitter)

m1 = MiniF2FSandboxManager(event_sink=sink_a)
m2 = MiniF2FSandboxManager(event_sink=sink_b)   # silently overwrites m1's sink

assert m1._event_sink is sink_a                 # FAILS — it is sink_b
assert m1 is m2                                 # holds — singleton
```

Any test that constructs a manager with a recording sink while another code path holds
the same subclass with the production sink will see its `RecordingSandboxEventSink`
stomped (or will stomp the production sink, depending on order).

## Root cause

Two interacting design choices: (a) `__new__` returns a cached `cls._instance` so the
same object backs every construction; (b) `__init__` still runs on every construction
and is last-write-wins for any attribute it assigns. The `event_sink` kwarg is the only
current trigger, but the same shape would bite any future `__init__` parameter that sets
instance state.

## Scope

- **No production impact today.** All 5 construction sites omit `event_sink=`, so the
  stomp branch at `manager.py:77-78` never runs.
- **Latent risk** for: concurrent tests that swap sinks per-test without a full reset;
  multi-sink scenarios (e.g. adding a logging-only sink alongside the dashboard sink);
  any future refactor that starts threading `event_sink=` through constructors.
- Will become a live hazard the moment someone adopts the pre-revision proposal to pass
  `event_sink=` at construction sites — which is why
  `docs/rfcs/active/2026-04-17-sandbox-event-sink-activation.md` was rewritten to use a
  class-level setter instead.

## Proposed fix

Resolved by either of:

1. **Narrowly:** `docs/rfcs/active/2026-04-17-sandbox-event-sink-activation.md` — the
   class-level `set_event_sink` setter removes the need to pass `event_sink` at
   construction, making the stomp branch at `manager.py:77-78` vestigial. Delete the
   `event_sink=` kwarg from production `__init__` as part of that RFC's implementation.
2. **Broadly:** `docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md` — removes
   the singleton entirely in favor of instance-owned managers, eliminating the class
   hierarchy of shared state dicts along with the stomp. This is the correct long-term
   fix; the narrow fix above is sufficient to close this bug.

## On fix

- Set `status: fixed`, `fixed_pr: <PR#>`.
- If the broader RFC lands, confirm `manager.py:61-72` no longer holds class-level
  mutable state and update `docs/architecture/03_providers.md` to drop the
  singleton-pattern note.
- Move this file to `docs/bugs/fixed/`.
