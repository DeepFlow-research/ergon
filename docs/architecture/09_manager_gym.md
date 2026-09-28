# 09 — Manager Agent Gym

## 1. Purpose

[Manager Agent Gym](https://github.com/DeepFlow-research/manager_agent_gym) (MAG) evaluates
an LLM manager that plans, assigns and supervises work for a simulated team of AI and human
workers while a stakeholder's priorities change. Ergon runs its 20 registered scenarios as
ordinary samples: scheduling, messaging, sandboxes, retries, checkpoints and grading are native
Ergon, while scenario definitions, actor simulation formulas and rubrics come from upstream.

- Upstream scenarios, schemas, evaluators and prompts are vendored under
  `manager_gym/_vendor/mag` at a pinned revision, byte-for-byte apart from import paths; see
  its README. Native code reaches them only through `manager_gym/upstream.py`.
- `BENCHMARK_VERSION = "mag-native-v1"` names the native execution semantics; rubric versions
  (section 7) name the scoring.
- How to run it: [`examples/manager_gym/README.md`](../../examples/manager_gym/README.md).

At the pinned revision the catalog has 20 scenarios with 694 tasks (541 atomic, 14–58 per
scenario), 312 scheduled team additions, 2–8 preference dimensions per scenario and 1,281
rubric definitions, of which 1,230 run at the end of an episode (876 LLM-judged, 354 callable).

## 2. Core abstractions

- `EpisodeConfig` is a scenario, seed, stakeholder persona, manager policy, budget and
  `InferenceProfile` record passed to `Environment.from_records`. `make_manager_gym_sample`
  builds a root `EpisodeTask` with `MAGManagerWorker`, an `E2BSandbox` and `MAGRubric`.
- `EpisodeState` holds the authored plan, scenario events and frozen projections of native
  results. An unassigned leaf or composite task is input data. `bindings` links a planned
  task's UUID to its native Ergon task after assignment; it is not an execution queue or a
  second graph.
- `MAGWorkWorker`, `MAGHumanWorker` and `MAGStakeholderWorker` perform role work. A worker's
  `actor_key` identifies the simulated person across tasks; `type_slug` identifies the code
  that runs. The root task is the manager.
- `MAGCommunication` exposes actor-scoped messaging tools over Ergon's communication service.
  Scripted stakeholder behaviour between decisions runs in the manager task, with messages
  attributed to the stakeholder; it is not an LLM policy and creates no tasks.
- Each upstream rubric becomes a `MAGCriterion`. `MAGRubric` groups criteria by preference
  and excludes diagnostic criteria from the headline utility.

## 3. Control flow

The manager checkpoints its initial state, then each observation of native state and each
model decision, and executes the chosen action through the existing `WorkerContext` task
tools. Spawns, refinements, reassignments and cancellations go through the runtime's task
service and durable step boundary; a decision creates no extra task or sandbox. Checkpoints
are stored as sample artifacts and Inngest keeps only their hash and size, so long episodes
stay below Inngest's state limit.

Native dependency edges express the authored prerequisites. There is no implicit
serialisation per actor and no capacity queue. When a human worker starts, it reads its prior
completed attempts, accounted hours and predecessor resources from PostgreSQL once; the
upstream fatigue, Gaussian quality and speed, misunderstanding and wage formulas run on that
input. Work products are written into the task's E2B sandbox and published by Ergon's
resource lifecycle.

The manager's decision index drives roster and preference events and the stakeholder outbox.
Wall time bounds execution; simulated labour hours are a reported metric. An end request or
the decision limit stops decisions; the manager then drains admitted tasks, cancels what
remains at its deadline, freezes one JSON snapshot and writes it to E2B. Ergon's evaluator job
rebuilds the rubric set and grades that snapshot before the sandbox is cleaned up.

## 4. Invariants

- Native graph status, attempts, messages and resources are authoritative. Building an
  observation cannot release work, fabricate completion or hide a visible native result.
- A task can be assigned only after its prerequisites are bound; dependencies on composite
  tasks expand to their leaves. Unclaimed tasks can be edited atomically; replacing a running
  or finished task is rejected. Reassignment keeps existing prerequisites. One actor may work
  on several tasks at once.
- The stakeholder's initial preferences are public, as upstream. Future events, later private
  preference changes and judge definitions are never manager input. Stakeholder work sees its
  current weights.
- Checkpointed observations, inference results and random draws replay deterministically.
  Persisted context chunks that match are reused; mismatches fail. A crash between a provider
  response and its checkpoint can still repeat that one call.
- Grading uses upstream's terminal rubric selection and its per-preference
  `sum(score) / sum(max_score)` normalisation. Utility uses the final preference weights;
  diagnostics are recorded but never dilute utility.
- Missing or failed grading and infrastructure failures make the evaluation incomplete
  (a null score), never a fabricated number. A valid poor policy can score low; tasks the
  policy cancelled are outcomes, not infrastructure errors.
- Every executable task, including the manager, has an E2B sandbox. The host blob store is
  artifact storage, not a task runtime.

## 5. Extension points

- **Policies.** `EpisodeConfig.manager_mode` selects `cot` (default), or upstream's `random`
  and `assign_all` baselines; all three share the manager worker, action execution and model
  routing.
- **Models.** Every role and the judge use the model target passed to
  `make_manager_gym_sample`; `InferenceProfile` sets temperatures per role and request limits.
- **Scenarios.** Scenarios come from the vendored upstream catalog. Updating the pin
  (`scripts/vendor_mag.py`) brings in upstream changes; `test_catalog.py` reports every
  rubric whose name, maximum or definition changed.
- **Scoring.** Corrections to upstream rubrics belong in a new rubric version
  (`manager_gym/rubric_versions.py`), never in the vendored files.

Manager-only RL would additionally need token alignment, filtering of environment roles and
reward attachment to manager decisions; this evaluation port does not establish that.
Changing the scheduler, adding a workday model or grading per decision requires a new
benchmark version.

## 6. Anti-patterns

- Running the upstream engine inside a wrapper and calling the result native Ergon.
- Adding a MAG scheduler, completion inbox, actor queue or second task store.
- Running one E2B task per decision, or giving a model SQL access to compute fatigue that a
  typed input projection already provides.
- Mixing snapshots, or dropping failing criteria to obtain a numeric score.
- Treating a healthy model endpoint, a completed sample or an aggregate score as a validated
  run. Inspect per-sample criteria, artifacts and sandbox cleanup.

## 7. Parity with upstream

Kept from upstream, including known quirks:

- Scenario factories, team and preference timelines, actor formulas, prompts and rubric
  definitions (hash-checked against an inventory taken at the pinned revision).
- Terminal rubric selection: preference rubrics declared `ON_COMPLETION` plus every
  diagnostic. `BOTH` cadence is not expanded (no registered rubric uses it).
- The misunderstanding branch reports simulated duration and cost but does not add to the
  actor's accounted hours.
- The 13 default manager actions; `request_end_workflow` is not among them.
- Workers get upstream's communication tools, not a search or code-execution bundle. Where
  upstream registers a tool name twice, the definition upstream actually dispatches to is used.

Deliberate differences in native execution (`mag-native-v1`):

| Upstream | Native | Why |
|---|---|---|
| Engine ticks decide when work runs | Ergon schedules tasks when prerequisites complete | Scheduling is the runtime's job; ticks remain the decision index. |
| Scheduled preference updates mutate earlier weights | Weights are copied on update | An update at tick 10 no longer rewrites the weights recorded for tick 0. |
| Rubric `llm_model` (`o3`) is ignored; the rule's default judge runs | The judge is the sample's model target | The configured judge is the one that runs, and it is recorded. |
| Human noise draws from the global `random` module | One seeded RNG per actor and task | Replays and reruns see the same draws. |
| Model errors in rubrics can become a score of 0 | Grading errors make the evaluation incomplete | An outage is not a policy failure. |
| Free-text or JSON-mode final answers | Strict output tools with two validation retries | JSON mode can skip required tool calls; prompted JSON exhausted budgets on long outputs. |
| Capacity fields are informational | Also informational | Enforcing capacity would change parallelism and fatigue interleaving. |

Rubric versions (`MAGRubric(rubric_version=...)`, recorded in criterion metadata):

- **Version 1** reproduces upstream scores.
- **Version 2** (default) corrects three upstream rubric bugs listed in the vendored README:
  ICAAP `seeking_sourcing` (it cannot observe tool use and always scores 0), stakeholder
  `response_latency_adherence` (its maximum disagrees with its function), and operational
  `agent_utilization_efficiency` (its description is copied from another rubric).

## 8. Model calls and failures

- Work roles have a request budget and a per-request deadline; their lifetime is otherwise
  governed by native task cancellation and the manager's drain deadline. Manager, estimator,
  decomposer and judge calls also have an operation timeout. Limits live in
  `InferenceProfile` and are recorded with each sample.
- After an observed model response, a work role's exhausted request budget or invalid output
  becomes `WorkerOutput(success=False)` with typed `model_failure` metadata, no resources and
  no simulated cost. The task stays failed and its dependents are not released; the episode
  remains gradeable, as upstream. Provider, tool, storage and timeout exceptions still raise.
  Managers, estimators and judges never downgrade failures this way.
- Provider and usage failures attach a compact summary to the exception (finish reasons, token
  counts, tool names and argument sizes); prompts and tool arguments are not copied.
- Resource output schemas describe content only. The worker assigns each resource a
  deterministic UUID from its planned task and output index, so models never generate IDs.
- Prompts keep upstream's previews: 300 characters of each resource for the manager and judge,
  200 for workers, and the ten most recent manager-visible messages clipped to 140 characters.
  Snapshots and native storage keep full contents; LLM rubrics see upstream's workflow summary
  and callable rubrics receive the full context they request.

A sample with failed work tasks keeps its failed status, but a completed manager with a
complete evaluation is still a valid episode. Selecting RL samples must therefore check that
the reward is complete rather than filter on sample status.

## 9. Limits

- The default horizon is 50 decisions (timesteps 0–49). Seven scenarios schedule events after
  that, which do not occur; a longer horizon changes the benchmark and must be recorded.
- The manager's sandbox lifetime is 3,600 seconds, so decisions, drain and grading must fit
  within it.
- Model and sandbox spend are separate from the simulated labour cost the benchmark reports.
