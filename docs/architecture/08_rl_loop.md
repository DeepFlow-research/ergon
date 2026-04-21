# 08 — RL Loop

## Purpose

Generation turns produced by workers during experiment runs are the training
signal for TRL/GRPO. This layer describes how turns are persisted, how the
trainer pulls them, and how rewards from evaluators are joined at training
time. The loop is deliberately asymmetric: workers emit turns into a durable
event log, evaluators write scores into a separate table, and a server-side
extractor pure-functionally combines the two into immutable `Trajectory`
records that the trainer consumes over HTTP. The RL layer therefore sits on
top of the persistence and evaluation layers rather than beside them, and
never touches the live worker loop.

## Core abstractions

| Type | Location | Freeze | Owner |
|------|----------|--------|-------|
| `GenerationTurn` | `ergon_core/api/generation.py:97-118` | Unstable; worker-internal | Worker layer |
| `RunContextEvent` | `ergon_core/core/persistence/context/models.py:25` | Stable wire format (table `run_context_events`) | Persistence layer |
| `ContextEventType` | enum in context persistence module | Stable; additions only | Persistence layer |
| `RunTaskEvaluation` | evaluation ORM row | Stable | Evaluation layer |
| `Trajectory` | `ergon_core/core/rl/rollout_types.py:38-51` | Stable HTTP contract | RL layer |
| `AgentTrajectory` | intermediate in `extract_agent_trajectories()` | Unstable; extraction-internal | RL layer |
| `reward_strategy.assign()` | `ergon_core/core/rl/extraction.py` | Single seam for reward joining | RL layer |

`GenerationTurn` is the in-memory, worker-side abstraction yielded from the
worker's async generator. It carries `messages_in`, `response_parts`,
`tool_results`, `turn_token_ids`, `turn_logprobs`, `policy_version`,
`started_at`, and `completed_at`. It is never serialized outside the worker
process.

`RunContextEvent` is the persisted unit. A single `GenerationTurn` is
DECOMPOSED into multiple context-event rows — one per message
(`system_prompt`, `user_message`, `assistant_text`, `tool_call`, `thinking`,
`tool_result`). The row shape is `id`, `run_id`, `task_execution_id`,
`worker_binding_key`, `sequence`, `event_type`, `payload` (JSON),
`started_at`, `completed_at`, `created_at`, `policy_version`. The
`sequence` field preserves intra-turn ordering; the tuple
`(task_execution_id, sequence)` is monotonic.

`RunTaskEvaluation` is where reward scores live. It is keyed by
`execution_id` and produced by the evaluator layer, not the worker. Rewards
are NEVER stored on the turn.

`Trajectory` is the trainer-facing dataclass with fields `prompt_ids`,
`completion_ids`, `logprobs`, `completion_reward`, and `env_mask`. It is
what crosses the HTTP boundary to TRL. `AgentTrajectory` is the
intermediate produced by `extract_agent_trajectories()` before HTTP
serialization.

## Control flow

```
Worker.execute() yields GenerationTurn
    |
    v
worker_execute.py:81 -> _persist_context_events() (lines 150-174)
    |  decomposes the turn into RunContextEvent rows, one per message
    v
turn stored in run_context_events; also emits DashboardContextEventEvent (Inngest)
    |
    v
task COMPLETED -> evaluators run -> RunTaskEvaluation.score populated
    |
    v
TRL trainer (ergon_infra/adapters/trl_http.py):
    1. POST /rollouts/submit with (definition_id, num_episodes)     [lines 44-89]
    2. poll GET /rollouts/{batch_id} until status="complete"        [lines 57-86]
    3. receive list[Trajectory] with (prompt_ids, completion_ids, logprobs, reward)
    |
    v
server-side (ergon_core/core/rl/rollout_service.py):
    _extract_trajectories() (lines 243-311)
      reads RunContextEvent rows (line 247)
      reads RunTaskEvaluation rows (line 259)
      joins by execution_id (lines 272-286)
      calls extract_agent_trajectories() in core/rl/extraction.py (lines 49-117)
      -> converts events + scores into (prompt_ids, completion_ids, logprobs, env_mask, reward)
      -> wraps in Trajectory for HTTP response
```

Three data movements matter:

1. Worker -> persistence. The yield-site in the worker's async generator is
   the persistence hook; nothing else writes `run_context_events`.
2. Evaluator -> evaluation table. Independent of the worker loop. Runs
   after task COMPLETED.
3. Trainer -> runtime. Pull-only, over HTTP. The trainer drives cadence;
   the runtime never pushes.

`_extract_trajectories()` is the join site. It reads both stores, joins by
`execution_id`, and hands the merged record to `extract_agent_trajectories`
which performs tokenization bookkeeping (prompt vs completion spans,
`env_mask` for multi-turn credit assignment) before returning an
`AgentTrajectory`. That is finally converted to `Trajectory` for the
response.

## Invariants

- `RunContextEvent` is the persistence unit; `GenerationTurn` is only
  in-memory. Adding a new kind of event on the worker side requires adding a
  matching `ContextEventType` and teaching `extract_agent_trajectories` how
  to encode it. Enforced by: the extractor switch statement in
  `ergon_core/core/rl/extraction.py` will raise on an unknown event type.
- Reward is NEVER stored on the turn. It lives in `RunTaskEvaluation.score`
  and is joined at extraction time via `reward_strategy.assign()`
  (`extraction.py`). Enforced by: `RunContextEvent.payload` schema has no
  reward field; there is no code path that writes one.
- The trainer pulls. The runtime does not push to the trainer. Enforced by:
  there is no client for the trainer host; only the HTTP endpoints in
  `rollout_service.py` exist.
- Trajectories returned to the trainer are immutable. Extraction is pure on
  top of persisted rows; running `_extract_trajectories` twice with the
  same inputs returns identical output. Enforced by: no mutation of
  `RunContextEvent` rows during extraction; `AgentTrajectory` is a frozen
  dataclass.
- `(task_execution_id, sequence)` ordering is monotonic per task. Enforced
  at insert time in `_persist_context_events`.

## Extension points

- **Add a new event type** (multimodal, structured tool result, etc.): add
  a variant to `ContextEventType`; extend `_persist_context_events`
  (`worker_execute.py:150-174`) to emit it; extend
  `extract_agent_trajectories` (`extraction.py:49-117`) to encode it into
  `prompt_ids`/`completion_ids`. Tokenization belongs in the extractor, not
  the worker.
- **Change reward computation:** `reward_strategy.assign()` is the single
  seam. Change the strategy, not the extraction logic. Strategies are
  composable: outcome-based, dense, stepwise, etc., all plug in here.
- **Add a new trainer backend:** follow the pattern of `trl_http.py` —
  POST `/rollouts/submit`, poll `/rollouts/{batch_id}`, consume
  `Trajectory`. The backend owns batching and lr schedule; the runtime
  owns supply.
- **Add a new rollout filter** (reject short episodes, dedupe by prompt,
  etc.): filter at the server-side extractor rather than the trainer.
  Keeps the trainer contract narrow.

## Anti-patterns

- **Writing reward onto a `RunContextEvent`.** Reward joins at extraction.
  Don't mix the two stores. This would couple the evaluator cadence to the
  worker cadence, which is exactly what the decomposition is designed to
  avoid.
- **Trainer-side direct Postgres reads.** The trainer is decoupled via HTTP
  for good reasons — model-provider isolation, multi-replica extractor,
  independent scaling. Any trainer talking to Postgres directly defeats
  those.
- **Producing a `GenerationTurn` without yielding through the worker's
  async generator.** The persistence hook is attached to the yield. A turn
  returned any other way is invisible to the RL loop.
- **Mutating a `RunContextEvent` after insert.** The append-only shape is
  what makes extraction pure. Corrections should be a new event, never an
  update.
- **Assembling a `Trajectory` on the worker side and shipping it anywhere.**
  The worker has no reward, no global view, and no stable tokenization
  contract. Trajectories are a trainer-facing type; they are built by the
  extractor, not the worker.

## Follow-ups

- **Silent trajectory drop bug.** If a criterion fails to produce a
  `RunTaskEvaluation.score` row, `extract_agent_trajectories` drops the
  trajectory or assigns the default reward. Need to document this as a
  stronger invariant: criteria MUST produce a score row (even if null) for
  every evaluator binding. Consider filing as an RFC. Today the failure
  mode is silent and looks like "training didn't improve" rather than
  "data was missing."
- **Reward-strategy documentation.** `reward_strategy.assign()` currently
  has minimal docs. Needs an architecture note describing the available
  strategies and how to add one. Pair with the cross_cutting/artifacts
  doc, since some strategies read from the blob store.
- **Extraction replay tool.** Because extraction is pure, we should expose
  a CLI that re-runs `_extract_trajectories` for a finished run without
  touching the trainer — useful for debugging reward shaping and
  regression testing extractor changes.
- **Tokenization contract versioning.** `extract_agent_trajectories`
  implicitly assumes a tokenizer shape; changes here silently break
  previously captured runs. Pin a contract version into `Trajectory` and
  refuse mismatches at the trainer.
