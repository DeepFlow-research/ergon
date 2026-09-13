> **Historical design record, September 13 update:** Full implementation is authorized and underway. The [single implementation plan](../../../superpowers/plans/2026-09-07-manager-gym-native-port.md) now records actual files, core changes, native semantics and live acceptance gates. Earlier statements below about unimplemented code, approval gates, per-decision Tasks, alternative sandboxes or proposed mappings are historical and do not describe the current implementation.

> **Superseded implementation guidance:** Use the [single MA-Gym implementation plan](../../../superpowers/plans/2026-09-07-manager-gym-native-port.md). This document is retained as historical product/design/source-audit context; its earlier proposals do not override the consolidated plan.

# PRD: Manager Agent Gym as a native Ergon evaluation benchmark

**Status:** Draft, updated 2026-09-13 after the [Ergon-way audit](ergon-way-audit.md). Product direction follows Charlie's September 8 answers and September 13 decision to use Ergon scheduling; remaining mapping details and benchmark corrections are proposals. No native runtime has been implemented. The audit removes optional-sandbox and new general actor/journal APIs as prerequisites, while preserving the evaluation scope.

**Outcome:** A researcher can run the 20 registered Manager Agent Gym (MAG) scenarios through Ergon, compare manager policies, and inspect the decisions, simulated team, messages, resources and rubric evidence using the same records and workflows as existing Ergon benchmarks.

The port must make the manager, AI workers, simulated human workers, stakeholder work and decomposition native Ergon executions. Actor rules and scoring remain benchmark-owned; task scheduling and normal result visibility use Ergon. The original MAG engine is an independent development oracle. V1 is evaluation-only; its identities, decision boundaries and provenance must support a later manager RL integration without rebuilding the benchmark.

Read this document for requirements and the full feature manifest, the [RFC](README.md) for composition and execution design, and the [implementation plan](../../../superpowers/plans/2026-09-07-manager-gym-native-port.md) for dependent PRs and validation gates. The [capability map](capability-mapping.md) records current Ergon support and source pointers.

## Decisions supplied by Charlie

| Topic | Direction |
|---|---|
| First use | Evaluation now, with a path to RL |
| Native scope | Port agents, messaging, rubrics and rubric execution into Ergon |
| Human simulation | Keep an LLM human simulator; investigate PostgreSQL records as the basis for fatigue and state |
| Clock | Use Ergon task scheduling for v1; replacement may be considered later. Accept differences from MAG collection and result visibility |
| Coverage | All 20 registered scenarios; a full manifest of faithful ports and changes |
| Data and inspection | Use existing Ergon benchmark structures and inspection workflows |
| Constraints | No additional constraints or delivery deadline supplied; surface concrete discoveries |

## Users and evaluation journey

The primary user is a researcher evaluating manager behavior. The second user is an engineer diagnosing a policy result or adding a scenario.

1. Select scenario(s), seeds, stakeholder persona, manager baseline/model, environment models, judge model, horizon and benchmark version through normal Ergon authoring.
2. Submit an experiment. Every sample represents one episode and carries the resolved configuration and source provenance.
3. Inspect manager decisions and team work as native task attempts and actor traces. Follow messages and resources across logical work items, and inspect decision index, hours, cost and recorded fatigue inputs.
4. Inspect final stakeholder utility alongside its preference scores, each rubric's result and evidence, and separate workflow diagnostics. Distinguish a valid low score from incomplete execution or evaluation.
5. Compare samples only under explicitly recorded conditions. Rerun a failed episode as a new attempt; reuse a frozen final snapshot for re-evaluation with provenance linking the original result.

No custom dashboard, live human participant interface, or workflow editor is required. Missing essential fields in existing inspection paths are in scope; presentation should stay consistent with other benchmarks.

## Measured scope

Source: MAG commit [`3f7a5d4`](https://github.com/DeepFlow-research/manager_agent_gym/tree/3f7a5d4af1d31abaedbedd525a0090452926fef4). Ergon baseline: `6910ecfc74807209b86db5c6f063ac9932b462a0`. These are the inspected revisions, not a promise that either remains the latest upstream head.

| Inventory | Count |
|---|---:|
| Registered scenarios | 20 |
| Logical task nodes including nested nodes | 694 |
| Atomic work items | 541 |
| Scheduled team additions, excluding separate stakeholder | 312 |
| Default manager actions | 13 |
| Preference rubric definitions | 540 |
| Workflow diagnostic rubric definitions | 741 |
| All rubric definitions across scenario compositions | 1,281: 405 callable, 876 LLM |
| Rubrics selected by the ordinary final-evaluation path | 1,230: 354 callable, 876 LLM |

Definitions are counted per scenario composition, so reused default diagnostics appear for each scenario. These are not unique implementation counts or measured request counts. All 1,281 definitions are in the [rubric manifest (CSV)](evidence/rubric-inventory.csv) and [JSON](evidence/rubric-inventory.json), with stable IDs, owner, maximum score, cadence, context, configured model, definition hash and callable source location. The [generator](evidence/inventory_rubrics.py) makes no model requests. The source final-selection rule excludes 51 preference rubrics configured only for each timestep; it includes workflow diagnostics even when their declared cadence is each timestep.

The [scenario inventory](capability-mapping.md#scenario-coverage) enumerates all 20 scenarios and sizes. `tech_acquisition_integration` exists as a directory but is not registered and is outside the initial catalog. The first implementation slice is proposed as `legal_litigation_ediscovery`, followed by ICAAP, marketing and banking license coverage. Full catalog acceptance remains the release goal.

## Requirements and acceptance

| ID | Requirement | Evidence required |
|---|---|---|
| R1 | All 20 registered scenarios load with tasks, resources, team timelines, preferences and rubric definitions intact | Constructor/serialization inventory equals the pinned manifest; source callable rules remain executable |
| R2 | Model work executes through native Ergon workers and model capture | Native traces for manager, AI, human roleplay/time estimate, stakeholder assigned work and decomposer; no production MAG engine invocation |
| R3 | Port public information and the 13-action interface using native task lifecycle semantics | Every action has a supported transition or explicit restriction; accepted timing differences and proposed edit restrictions are recorded |
| R4 | Preserve actor identity and human simulation formulas across invocations | Two same-class humans remain distinct; fatigue is recomputable from the exact completed native work used as input |
| R5 | Provide native messaging during work, including stakeholder timing and end requests | Recipient-scoped reads while senders are still running; delayed delivery, filters and termination evidence |
| R6 | Use Ergon task scheduling and normal result visibility | Native dependency release, replay and completion traces; separate decision index, labor hours and wall time; no MAG collection barrier |
| R7 | Execute source rubric definitions natively and preserve stakeholder utility | Every selected rubric has a normal criterion result and evidence; independent utility recomputation; diagnostics do not dilute the score |
| R8 | Distinguish benchmark outcomes from infrastructure/evaluation failures | Horizon and misunderstanding can be scored; exhausted judge errors and interrupted episodes are incomplete, excluded from valid-score averages |
| R9 | Use ordinary Ergon benchmark persistence and inspection | Samples, task attempts, actor/model traces, messages, resources and evaluation summaries available through normal paths; no separate results database |
| R10 | Record all comparison conditions and intentional changes | Source/content versions, scheduling semantics, event/end policy, corrections, model settings, seed/draws, action budget, prompts, persona and snapshot identity |
| R11 | Preserve a practical path to manager-only RL | Stable policy/environment role labels and distinct decision records; later trainer work explicitly scoped, no claim of training readiness in v1 |
| R12 | Validate the native implementation before claiming support | All-scenario offline native runs, retained-formula conformance and representative live actor/evaluator paths; no exact MAG scheduling gate |

No score, latency or spend threshold is invented in this PRD. The first native live slice must measure model requests, retry counts, tokens, charges and wall time by role. Use that evidence to set operational defaults and an acceptance budget. Infrastructure latency is not simulated human labor.

## Full feature manifest

**Faithful** means preserve the observed benchmark behavior while changing its implementation. **Native adaptation** uses Ergon composition/persistence with explicit behavioral differences. Native task scheduling and result visibility are accepted changes; detailed action/event/end mappings remain proposals. **Proposed correction** changes observable reference behavior and requires a named benchmark version. **Deferred** is explicitly outside the first release. These are planned dispositions, not implementation status.

### Scenario composition and workflow

| ID | Feature and observed reference contract | Planned disposition |
|---|---|---|
| F01 | 20 registered Python scenario factories and their initial resources | Faithful; package definitions with callable rules and source/license provenance |
| F02 | Scenario × seed × persona × horizon × model configuration | Native adaptation to Environment/Sample, one episode per sample |
| F03 | Unassigned, assigned, atomic and composite logical tasks | Native adaptation: unassigned descriptions and composites remain plan/input data; create bound executable Tasks through the existing API, without a parallel execution graph |
| F04 | Dependencies, parent-to-leaf propagation and composite readiness | Native adaptation: Ergon dependencies and propagation are authoritative; composite summaries are read-only projections. Source transition ordering is intentionally changed |
| F05 | Observation construction registers leaves and updates readiness | Native adaptation: prepare source descriptions for observations; native readiness remains authoritative, with no observation-driven scheduler |
| F06 | Logical task mutations during an episode | Native adaptation: edit pre-execution input data; bound tasks follow existing lifecycle restrictions. Unsupported edits are explicit, not emulated by shadow state |
| F07 | UUID resources, dependency inputs and generated outputs | Native adaptation to normal resources with logical/native ID linkage and access scope |
| F08 | Scheduled joins and removals with public team descriptions | Native adaptation: proposed joins/removals at manager decision indices; already-created work follows Ergon lifecycle |
| F09 | Capacity metadata is not enforced by source dispatch | Use normal Ergon scheduling; add no benchmark capacity queue. Any future actor-capacity restriction is a separate rule change |
| F10 | Numeric initial preferences are present in stakeholder public profile | Faithful; future schedules and judge definitions remain outside manager input |
| F11 | Scenario creation has random identifiers and Python callables | Native adaptation; serialize configuration and typed data, reconstruct registered callables, normalize IDs only in comparison fixtures |
| F12 | Upstream server, streaming demo, file log layout and snapshot restoration | Native adaptation to Ergon lifecycle/inspection; upstream server and a second production engine are excluded |

### Complete manager-action manifest

Proposed mapping: each action consumes one manager decision, including queries, no-op and failed actions. The 13 source names remain mapped; restrictions after native Task creation are explicit proposals, not claims of faithful mutation support. The [action map](capability-mapping.md#complete-default-action-mapping) gives implementation details.

| ID | Action | Planned disposition |
|---|---|---|
| A01 | `assign_task` | Native adaptation: bind selected Worker and concrete dependency IDs through spawn_task. Proposed restriction: unresolved prerequisites must be bound first; no separate pending-assignment queue |
| A02 | `create_task` | Native adaptation: create plan/input data until worker and prerequisites can be bound; executable creation uses the existing spawn API |
| A03 | `remove_task` | Native adaptation: delete unbound input; bound work uses native cancellation with its actual descendant/dependency consequences |
| A04 | `refine_task` | Native adaptation: edit unbound inputs or use native refine_task; reject running-task edits where the runtime does |
| A05 | `add_task_dependency` | Native adaptation: author prerequisites before Task creation; post-creation edge editing is unsupported unless an existing native path is demonstrated |
| A06 | `remove_task_dependency` | Native adaptation: edit unbound prerequisites; do not remove live edges through a second graph authority |
| A07 | `decompose_task` | Native helper invocation with source prompt/schema and resource inheritance; its result is visible through native completion |
| A08 | `inspect_task` | Native public task/resource inspection; no tick-gated result filtering |
| A09 | `get_workflow_status` | Native adaptation: status/cost/progress projection over native results |
| A10 | `get_available_agents` | Faithful roster/public state query |
| A11 | `get_pending_tasks` | Native adaptation: native pending/readiness plus clearly labeled unbound plan inputs |
| A12 | `send_message` | Native adaptation with source recipient/body semantics |
| A13 | `noop` | Consume one manager decision without task mutation or forcing a collection cycle |
| A14 | Manager `request_end_workflow`, defined outside default actions | Deferred policy-interface expansion; preserve worker-originated end requests |

### Agents and tools

| ID | Feature and observed reference contract | Planned disposition |
|---|---|---|
| G01 | CoT manager: fresh observation-driven prompt, dynamic legal ID schemas, one structured action | Preserve fresh prompt, constrained schema and single-action decision boundary; capture multiple decisions within native worker control flow without requiring a Task per decision |
| G02 | RandomV2: chooses an action class randomly, then uses an LLM | Faithful native baseline; label its model cost honestly |
| G03 | Assign-all: LLM bulk assignment with fallback | Faithful baseline; proposed correction to forward the configured model instead of an implicit default |
| G04 | AI worker: persona/configuration, structured resources, tools and reported costs | Faithful role behavior through Ergon's model/trace path |
| G05 | Human worker: LLM roleplay with personality, expertise and work style | Faithful role behavior; explicit typed state per actor |
| G06 | Human fatigue: `min(hours_worked_today × fatigue_rate, 0.5)` | Faithful formula; native adaptation to completed native work recorded at invocation start |
| G07 | Human quality: Gaussian noise minus fatigue, clamped to [0,1] | Faithful formula; sampled inputs retained as evaluation evidence |
| G08 | Human speed: independent Gaussian multiplier with minimum 0.1 | Faithful; fatigue does not directly slow this multiplier in the source |
| G09 | Human duration: provided estimate or auxiliary LLM estimate; normal path applies speed; cost uses hourly rate | Faithful; trace the estimator as environment inference and preserve its fallback behavior with evidence |
| G10 | Human misunderstanding: LLM wrong-work path can report success; duration/cost still accrue | Faithful domain outcome; proposed correction for missing actor hours/count update, separately versioned |
| G11 | “Today” has no actual daily reset; break tool does not reset fatigue | Faithful initially; days, recovery, shifts and rest mechanics deferred |
| G12 | Overlapping work for one human can observe mutable state at timing-dependent moments | Accepted scheduling difference: each invocation captures its completed-work inputs at start; retain exact attempt IDs/draws, deduplicate retries, no admission barrier |
| G13 | Stakeholder assigned work uses an LLM | Faithful native worker with separate identity and resources |
| G14 | Stakeholder tick policy uses rules/RNG, personas and a delayed outbox | Preserve rules/RNG; proposed delivery and policy processing indexed by manager decisions, independent of task scheduling |
| G15 | Stakeholder policy repeatedly scans recent 20 messages without deduplication | Preserve repeated-scan behavior within the proposed decision-index policy; resulting frequency differs from source tick scheduling and is recorded |
| G16 | Decomposition and human estimation have auxiliary model calls | Native adaptation; every call uses Ergon routing and captures role/settings/usage |
| G17 | Actual runner-installed tools differ from ToolFactory defaults; some names duplicate | Preserve reachable capabilities; remove duplicate identical definitions only after dispatch characterization |
| G18 | Placeholder search/analysis/code/break tools | Preserve reachable placeholder behavior; introducing real tools is deferred |
| G19 | Model settings and seed forwarding differ between SDK paths | Native adaptation with explicit resolved settings; each observed forwarding fix goes in the correction list |
| G20 | Randomness partly uses module-global state | Proposed correction to per-actor, per-purpose streams; conformance injects recorded draws; live LLM determinism is not promised |

### Messaging, clock and episode lifecycle

| ID | Feature and observed reference contract | Planned disposition |
|---|---|---|
| C01 | Direct, multicast and broadcast messaging | Native adaptation over Ergon's existing message storage, with derived actor sender and scoped recipients |
| C02 | Recent, sender/conversation, thread and task filters | Faithful ordering/filter semantics; durable cursor translation |
| C03 | Messages readable during still-running work | Faithful live communication, not messages released only in final worker output |
| C04 | Stakeholder reply latency and scheduled preference/team events | Native adaptation proposal: manager decision index drives the event timeline/outbox; it never delays native results |
| C05 | Worker end-workflow signal | Native control signal; proposed stop-decisions-and-drain policy, with explicit change from source termination timing |
| C06 | One manager action each discrete timestep; collect old work before dispatching new work | Accepted change: use Ergon readiness, dependency release and result visibility; no source collection/dispatch phases |
| C07 | Prior-work collection uses a shared 300-second wall-clock timeout | Not ported in v1: use existing native execution deadlines. Do not implement a collection timer or new wait API for MAG timing |
| C08 | Simulated human duration does not determine task finish tick | Use native completion; keep reported simulated duration as a metric, not a dispatch clock. Alternative schedulers are deferred |
| C09 | Total simulated hours sum labor; AI reported duration derives from inference wall time | Faithful measures, separately labeled; record model timing for replay and comparability limitations |
| C10 | Default 50-step run executes 0–49, excluding later events | Proposed mapping: up to 50 manager decisions at indices 0–49, not 50 source simulation ticks; later events require a named longer budget |
| C11 | Completion, end request and horizon are benchmark end reasons | Proposed native end policy: stop manager decisions, settle already-created work, then finalize and evaluate; unfinished unbound plans remain visible |
| C12 | In-flight work at termination or parent failure | Native cancellation/failure remains authoritative; finalization follows required work completion and freezes score input. No pre-completion admission cutoff |
| C13 | Retried/delayed delivery of actions and results | Reuse durable spawning/steps; preserve decision inputs and call order across replay; count each eligible completed attempt once without a second task ledger |
| C14 | Crash recovery and saved snapshots | Saved evidence and final-snapshot re-evaluation in scope; transparent mid-episode resume deferred |

### Rubrics and scoring

| ID | Feature and observed reference contract | Planned disposition |
|---|---|---|
| E01 | All 1,281 composed rubric definitions, including callables and prompt text | Faithful definitions; each maps to a normal native Criterion, tracked in the row-level manifest |
| E02 | Default runner evaluates at completion | Faithful final selection: 1,230 selected rows across the catalog, including all 876 LLM definitions |
| E03 | Optional each-tick evaluation, forced checkpoints and `BOTH` enum | Preserve definitions/cadence metadata; execution of optional tick profiles deferred from terminal-evaluation v1, with source selection quirks documented |
| E04 | Callable return normalization and clamping to each rubric's maximum | Faithful; preserve raw output/reasoning and normalized score evidence |
| E05 | LLM boolean/category/numeric output interpretation | Faithful native judge criterion; source prompt/context contracts retained |
| E06 | Preference groups use `sum(raw)/sum(max)` regardless of advertised aggregation strategy | Faithful executed formula; no automatic use of Ergon's flat weighted average |
| E07 | Utility is sum of preference-group score × final preference weight | Faithful single episode score; snapshot determines final weights |
| E08 | Goal, constraints, efficiency and communication workflow evaluators | Faithful diagnostics in the same saved evaluation; excluded from headline utility |
| E09 | Scheduled preference update currently mutates earlier snapshots | Proposed correction to immutable timeline snapshots |
| E10 | Rubric judge-model override currently ignored | Proposed correction to use and record configured model |
| E11 | Source silently turns some judge errors/refusals into zero | Proposed correction to explicit incomplete evaluation after exhausted retries, with retained evidence |
| E12 | Source executes rubrics concurrently, semaphore default 100; Ergon executes sequentially | Native serial execution first; bounded concurrency is a conditional optimization after measurement, retaining stable result order and a recorded cap |
| E13 | Default context includes workflow/preferences/tick; registered extra requests use manager actions and messages by sender | Native frozen workflow projection with decision index mapped explicitly to source context fields; preserve prompt/score logic, not identical timing or resulting scores |
| E14 | Some declared context channels are placeholders or unrequested by this catalog | Characterize and reject unsupported new demands explicitly; filling placeholders with new private information is deferred |
| E15 | Re-evaluation of saved final state | Native evaluator can consume the same immutable snapshot; record model/version change and link original evaluation |
| E16 | General reward aggregators, alternative projections and dense reward vector | Preserve useful raw preference scores; custom projections and dense RL reward integration deferred |

### Data, operations and future RL

| ID | Feature | Planned disposition |
|---|---|---|
| O01 | Standard samples, attempts, generations, messages, resources and evaluation summaries | Native adaptation; use existing Ergon tables and inspection paths |
| O02 | Human state from PostgreSQL | Typed projection of completed native work and exact input attempt IDs; reuse outputs/resources, no admission ledger or unrestricted SQL tool for the LLM |
| O03 | Logical tick, actor ID, task ID, sampled effects and committed sequence | Decision index, actor/task/attempt IDs, sampled effects and input snapshots are evidence; native task state is the execution authority |
| O04 | Infrastructure error versus valid low score | Explicit evaluation status; nullable invalid score excluded from aggregation; existing records must remain interpretable |
| O05 | Sandbox/runtime composition | Keep mandatory task-bound Sandbox and existing lifecycle. Native inference does not require removing sandboxes; a cheaper runtime is a conditional adapter proposal after measurement |
| O06 | Usage/cost | Track actual model spend, requests and wall time separately from simulated labor cost and duration |
| O07 | RL extension | Policy/environment labels and independent manager decision spans now; trainer filtering, reward attachment, token alignment validation and optimization later |
| O08 | Split and comparisons | No invented official train/test split for eval v1; named suites/seeds/configurations; scenario-family split is a later RL/generalization decision |
| O09 | Extended simulator/product features | Scheduler replacement or MAG clock reproduction, capacity rules, day/rest model, real people, new tools, custom UI and the 21st unregistered scenario are deferred |

## Accepted scheduler decision and proposed timing details

V1 uses Ergon's scheduler, dependency propagation and ordinary result visibility. Charlie explicitly accepted this direction on September 13, superseding the proposed MAG collection/admission layer. Replacing the scheduler is later work, with no compatibility framework required now.

The RFC proposes a manager decision index for team/preference events and stakeholder reply delays, separately from simulated labor hours and wall time. This index must never gate task dispatch or hide completed results. It also proposes stopping manager decisions at the budget/end request, draining already-created native work, then evaluating a finalization task's frozen snapshot. These event and end-policy details remain proposals and are explicit differences from the source.

Human invocation inputs record the actor, exact completed native attempts, simulated hours/cost and sampled noise used at invocation start. Code derives fatigue and passes typed state to the LLM. Concurrent invocation inputs may differ with completion order; there is no MAG admission ledger. Correcting the source's missing misunderstanding-hours update remains a separate benchmark-version proposal.

## Release gates and exclusions

Release requires complete inventory coverage, independent checks of retained formulas/definitions with explicit scheduling and correction deltas, all 20 offline native episodes, and live evidence for the smallest scenario plus dynamic-team/preference and high-rubric-count scenarios. A live run must show a saved final snapshot, native actor/model traces, messages/resources, selected criterion outcomes, recomputable utility, errors/retries and actual cost/time. Job completion alone does not establish support.

Exact source fixture equality applies to retained definitions, formulas and supported action behavior under fixed inputs. Source scheduling, decision interleaving and horizon behavior are intentionally different and are not equality gates. Live stochastic score equality is not an acceptance promise; distribution comparisons require repeated runs and reported variance. No claim of statistical equivalence should be made from one run.

V1 excludes training execution, dense rewards, optional tick-evaluation profiles, transparent crash resume, MAG scheduler reproduction/replacement, generalized mutable core DAG scheduling, new human workday rules, real search/coding tools, and a custom dashboard. These are explicit scope proposals, not hidden omissions from the full manifest. All 20 registered scenarios under the terminal-evaluation profile remain in scope.

No deadline or staffing commitment is assigned. The [implementation plan](../../../superpowers/plans/2026-09-07-manager-gym-native-port.md) uses evidence gates and dependencies; staffing and delivery dates can be set after the first runtime slice. Further questions should be driven by concrete unresolved tradeoffs, with recommendations already prepared.
