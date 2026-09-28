# 09 — Native Manager Agent Gym

## 1. Purpose

Run the pinned 20-scenario MA-Gym catalog as ordinary Ergon evaluation samples.
`mag-native-v1` preserves scenario definitions, actor simulation formulas and
terminal scoring while using Ergon scheduling and completion visibility.
[The implementation record](../superpowers/plans/2026-09-07-manager-gym-native-port.md)
owns the feature manifest and acceptance status;
[the runbook](../../examples/manager_gym/README.md) owns operating commands.

## 2. Core abstractions

- `EpisodeConfig` is a scenario/seed/persona/policy/budget record passed to
  `Environment.from_records`. `make_manager_gym_sample` builds an object-bound
  root `EpisodeTask`, `MAGManagerWorker`, `E2BSandbox` and `MAGRubric`.
- `EpisodeState` holds authored plans, scenario events and frozen projections
  of native results. An unassigned leaf or composite is input data. The
  `bindings` map links its logical UUID to a native Task after assignment;
  it is not an execution queue or alternative graph authority.
- `MAGWorkWorker`, `MAGHumanWorker` and `MAGStakeholderWorker` execute role
  work. Configured `actor_key` identifies the person across tasks;
  `type_slug` identifies executable code. The root is the manager policy actor.
- `MAGCommunication` scopes model tools over the native communication service.
  Scripted stakeholder tick behavior remains a benchmark function executed by
  the root, with messages attributed to the stakeholder. It is not an LLM
  policy and does not create an otherwise empty Task for every tick.
- Each source terminal rubric becomes a `MAGCriterion`. `MAGRubric` groups
  preference scores and excludes diagnostic criteria from headline utility.

## 3. Control flow

The native worker checkpoint facade saves results as existing sample artifacts,
leaving only verified hash/size references in Inngest. This avoids accumulation
of full transcripts and workflow state beyond Inngest's 32 MB limit; all retained
checkpoint bytes are included in normal evidence exports.

The manager checkpoints initialization, then each native observation and model
decision. It executes the chosen action through existing WorkerContext task
tools. Spawns, pending refinements/reassignments and cancellations use the
runtime's existing service and durable step boundary. A decision does not
create another task or sandbox.

Native dependency edges express authored work prerequisites, with no implicit
same-actor serialization or capacity queue.
The next human invocation captures prior completed attempt IDs, accounted
hours, messages and predecessor resources from PostgreSQL once. Its initial resource inputs are selected by the planned task's declared IDs; unrelated workflow resources are excluded. The source
fatigue, Gaussian quality/speed, misunderstanding and wage formulas operate on
that input. Inference and estimation use the ordinary provider resolver and
transcript adapter. Output artifacts are written into the task's E2B sandbox
and published by Ergon's resource lifecycle.

The root's decision index drives roster/preference events and the stakeholder
outbox. Wall time bounds execution; simulated labor hours are reported metrics.
An end request or decision limit stops decisions. The manager drains admitted
native tasks, cancels remaining work at its deadline, freezes one final JSON
snapshot and writes it to E2B. The native evaluator job reconstructs the pinned
criteria and evaluates that snapshot before terminal sandbox cleanup.

## 4. Invariants

- Native graph status, attempts, messages and resources are authoritative.
  Observation construction cannot release work, fabricate completion or hide
  an otherwise visible native result.
- Assignment requires prerequisites to be bound first. Composite dependency
  references expand to leaves. Unclaimed Task configuration/dependencies can
  change atomically; running or terminal executable replacement is rejected.
  Reassignment preserves existing task prerequisites; native reference/cycle
  validation remains authoritative. Concurrent work by one actor is permitted.
- Initial stakeholder preferences are public as in the source. Future events,
  current private preference changes and judge definitions are not manager
  input. Assigned stakeholder work receives its authorized current weights.
- The source misunderstanding branch omits actor fatigue-hours/count accrual;
  that quirk is retained while reported episode labor/cost still accrues.
- Checkpointed observations, inference and draws replay deterministically.
  Already-persisted identical context chunks are reused; mismatches fail.
  This does not guarantee exactly one provider call across a crash between a
  provider response and its checkpoint, nor recovery of that failed transcript.
- Terminal selection is 1,230 criteria across all scenarios: 876 LLM and 354
  callable. All 1,281 definitions remain packaged. Source cadence quirks and
  group `sum(raw)/sum(max)` normalization are retained. Utility uses final
  preference weights; diagnostics are inspectable but never dilute utility.
- Missing/failed grading or infrastructure failures yield incomplete/null,
  never a fabricated numeric benchmark score. A valid poor policy can score
  low; policy-cancelled prerequisites are not themselves infrastructure errors.
- Every executable task has an E2B sandbox. The host blob store is retained
  artifact storage, not a local-filesystem task runtime.

## 5. Extension points

Add a scenario factory, team/preference timeline and rubric factories to the
package and explicit catalog; update source/criterion manifests and acceptance
coverage. Use the existing sample factory, not a new Environment subclass.
The default policy is `cot`; source `random` and `assign_all` baselines reuse
the same manager Worker, action execution and model routing.

Later manager-only RL must verify token alignment, environment-role filtering
and reward attachment using native context/actor records. This evaluation port
does not establish training readiness. A scheduler replacement, new workday
model or optional per-tick grading profile requires a named benchmark version.

## 6. Anti-patterns

- Starting the upstream engine inside a wrapper and calling that native Ergon.
- Adding a MAG scheduler, completion inbox, actor queue or second task database.
- Running one E2B task per decision or giving an LLM unrestricted SQL access
  to calculate fatigue when typed native input projection suffices.
- Mixing snapshots or dropping failing criteria to obtain a numeric score.
- Equating a healthy model endpoint, completed wrapper or aggregate score with
  a validated catalog run. Inspect per-sample criteria, artifacts and cleanup.

## 7. Follow-ups and operational limits

The default integration profile has 50 decisions (0–49); seven scenarios have
later events. It is not a full-timeline or statistical-equivalence study.
The observed E2B account has a one-hour maximum lifetime. Serial grading must
finish within that lifecycle; measured expiry is a failed acceptance result.
The integration model profile includes a verified per-request thinking cap of
2,048 tokens after an exploratory worker exhausted 32,768 output tokens.
Source metadata and criterion evidence record the profile; the shared model
deployment is unchanged.
Work roles have a 12-request budget and 300-second provider request deadline;
their lifetime is governed by native task cancellation and the manager's shared
drain deadline. There is no separate whole-work inference timer. Manager,
estimator, decomposer and judge calls retain the 600-second operation cap.
Provider timeouts and native execution failures still make evaluations incomplete;
this is a lifetime change, not a broader model-failure fallback.
Model and VM/E2B billing are separate from simulated labor cost. Serving weight
location and image digest are provenance, not proof of immutable weight bytes.

## Source evidence rendering

Native storage and frozen snapshots retain complete resources and communication. Model prompts preserve source previews: 300 resource characters for manager/judge, 200 for AI/human work, and ten recent manager-visible messages clipped at 140 characters. Manager action briefs omit repeated payloads. The pinned LLM rubric path renders the no-scope workflow summary; callable rubrics receive complete requested context. Do not serialize the entire frozen context into every LLM criterion.

Upstream MAG scenarios, schemas, evaluators and prompts are vendored
byte-for-byte (apart from import paths) under `manager_gym/_vendor/mag`, and
native code reaches them only through `manager_gym/upstream.py`. The vendored
README explains the import rules, the shims and how to update the pin.
`pyproject.toml` excludes that tree from ruff and slopcop so upstream scoring
functions keep their catch-all fallbacks; native manager, worker, transport,
messaging, rubric adapter and core paths keep the normal lint rules.

### Structured output and communication

MAG uses PydanticAI output tools with strict argument schemas. Ordinary
communication tools stay enabled; the final response is validated against the
same typed output model with two validation retries. Live probes rejected native
constrained JSON because it skipped a required tool. Prompted JSON passed small
probes but exhausted request and validation budgets in actual pilots. Strict
output tools passed a small tool round trip and a larger public banking fixture;
the latter still needed retries after truncated responses. A native HTTP-contract
test covers tool execution, strict schema transmission, an invalid final answer,
validation feedback and a valid retry.
Preflight requires the same tool round trip as well as all seven role schemas.
This is an explicitly recorded inference profile change, not evidence of score
parity with upstream models or a guarantee against future model failures.

### Worker communication inputs

The pinned SDK dispatches duplicated tool names through its last-definition map.
That selects the source DI signatures for send/broadcast/recent messages;
conversation/task reads retain the closure signatures. Native tools now retain
source text previews: 100 characters for recent/task messages and 150 for a
conversation, with recent messages newest first. AI/human task prompts do not
receive an extra automatically injected inbox or execution-note block. Messages
remain available through native actor-scoped tools and complete database records.

Native task IDs populate the task-message default (the source closure captured
None), and broadcasts fan out to ordinary recipient rows. Rejected sends expose
only the already-permitted native actor IDs. These are explicit native mapping
choices, not a duplicate MAG communication store. See the
[communication contract audit](../rfcs/active/2026-09-07-manager-gym-port/evidence/implementation/communication-contract-audit.json).

Provider/usage/timeout failures add compact response accounting to the exception
notes retained by normal native error tracebacks: finish reasons, token counts,
tool names and argument sizes. No prompts or tool argument content are copied
into these diagnostics. A request that fails before a response is returned may
still have unavailable usage; full failed transcripts are not reconstructed.

Model resource output schemas describe content drafts without identifiers.
The worker constructs each native Resource with its existing deterministic
UUID from the planned task and output index. Previously, a strict schema forced
the model to generate UUIDs only for the worker to replace them, causing avoidable
validation retries. Original scenario resource identities remain unchanged.
PydanticAI retry feedback is retained as an error tool result (or a user message
for a retry without a tool), preserving the feedback the next model call saw.

Bounded work-role model failures use the existing `WorkerOutput(success=False)`
contract. After an observed model response, request-limit exhaustion and invalid
model outputs become typed `model_failure` metadata, with no work resources or
simulated cost/hours. The inference checkpoint retains the failed transcript and
observed usage. Native tasks remain failed; Ergon does not release their
dependents. Final drain cancels policy-blocked pending work through the native
task API. Those outcomes remain gradeable in the frozen MAG snapshot, matching
the source engine. Provider/HTTP, tool/storage and timeout exceptions still
raise. Judges, managers and estimators do not opt into this work-role policy;
failed grading remains incomplete/null. No historical snapshot is reclassified.

`TaskInspectionService.completion` returns a persisted WorkerOutput for failed
as well as completed nodes. Running/cancelled nodes still omit output. This
read boundary lets callers distinguish an explicit unsuccessful worker result
from an exception without bypassing native task inspection. It does not change
failed-task scheduling. Native samples containing failed work retain their
Failed status; acceptance separately requires a completed manager, all tasks
terminal, every failed task accounted for by typed work-model failure, a complete
numeric evaluation, retained artifacts and closed owned sandboxes.

Future RL sample selection must distinguish reward completeness from native
execution status. Filtering only for Completed samples would discard valid
manager episodes containing unsuccessful worker outputs. Incomplete/null
evaluations remain ineligible as rewards; a numeric low or zero utility is
still a real outcome. Token alignment, policy-role selection and reward
attachment are deferred and require their own training-path validation.
