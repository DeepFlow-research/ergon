> **Historical design record, September 13 update:** Full implementation is authorized and underway. The [single implementation plan](../../../superpowers/plans/2026-09-07-manager-gym-native-port.md) now records actual files, core changes, native semantics and live acceptance gates. Earlier statements below about unimplemented code, approval gates, per-decision Tasks, alternative sandboxes or proposed mappings are historical and do not describe the current implementation.

> **Superseded implementation guidance:** Use the [single MA-Gym implementation plan](../../../superpowers/plans/2026-09-07-manager-gym-native-port.md). This document is retained as historical product/design/source-audit context; its earlier proposals do not override the consolidated plan.

# MAG to Ergon capability mapping

This accompanies the [PRD and full feature manifest](prd.md) and [native-port RFC](README.md). Updated September 13 after the [Ergon-way audit](ergon-way-audit.md), which corrects the earlier core-first plan. **Existing** means a concrete public/runtime path was found in the inspected checkout. **Partial** means related infrastructure exists but its behavior or accessibility differs. **Missing** means the required contract was not found on the inspected path. These are source-level support classifications, not claims of live end-to-end verification. Four existing spawn/wait contract tests passed during this audit.

**Accepted v1 change:** Ergon owns scheduling, dependency release and result visibility. The MAG collection/admission layer is withdrawn. Its absence is not a missing v1 capability. The [RFC scheduling decision](README.md#scheduling-decision-for-v1) distinguishes this choice from proposed event/action/end mappings.

## Environment, composition, and runtime support

| Capability | MAG behavior and evidence | Ergon today and evidence | Native-port work / owner |
|---|---|---|---|
| Scenario dataset | Python factories compose workflow, preference evaluators, timeline, and goal evaluator [M1] | **Existing:** `Environment.from_records`, `Sample.from_tasks` [E1] | Benchmark loader over scenario × seed × persona; explicit split and version metadata |
| Task payloads and component serialization | Rich Pydantic tasks, but rubric callables and agent instances are not portable JSON [M2], [M9] | **Existing:** typed `Task[PayloadT]`, `_type` restoration, object-bound workers/evaluators [E2] | Persist configuration and typed invocation data, reconstruct scenario factories; do not put live SDK clients in snapshots |
| Planned but unassigned work | Task can exist with no assignee; assignment is a manager decision [M2], [M4] | **Missing as a runnable task:** `Task.worker` is required; ready spawned work dispatches immediately [E2], [E3] | Keep descriptions as source/manager input data; create native Tasks once bound. No independent mutable execution graph or pending-assignment scheduler |
| Persistent team identity | Named agents survive multiple work items and join/leave over time [M5] | **Partial:** configured Worker objects serialize; existing binding/event fields are populated from class slug on key paths [E8], [E13] | Bind each selected Worker through Task.worker; propagate stable configured actor identity through existing fields, no new registry or mandatory Task.actor |
| Simulated state per actor | Human hours/fatigue/count, stakeholder RNG and outbox [M6], [M7] | **Partial:** task outputs, resources, metadata and sample annotation events persist [E16], [E17], [E25] | Derive human inputs from completed native work; capture exact attempt IDs/draws for replay. No admission ledger or actor table |
| Discrete clock | One action per tick; collect older work before starting new work [M3] | **Different, accepted for v1:** runtime dispatch is event/dependency driven [E3] | Accepted difference: use Ergon scheduling and normal visibility. Proposed manager decision index drives scenario events only; source collection phases are not ported |
| Wait for child results | Engine waits on pending asyncio tasks, with 300-second collection bound [M3] | **Partial:** status inspection/resources exist; output preview truncates at 512 chars; `SpawnedTaskHandle.wait()` explicitly raises [E4], [E12], [E26] | Use native dependencies and finalization; the source 300-second collection wait is not ported. Scoped complete-result access only where needed; unsupported handle wait is not itself a release blocker |
| Dynamic task creation | Adds logical work without executing it immediately [M4] | **Existing for execution:** `spawn_task(Task, depends_on=...)` creates a fully bound child, writes edges and dispatches dependency-free work; worker path memoizes spawning [E3], [E21] | Reuse existing spawn/dispatch once bound; preserve native decisions and call order across replay. Plan descriptions carry no execution status |
| Dependencies and composites | Parent dependencies propagate to leaves; composite dependency expands to leaves; effective status is derived [M2], [M3] | **Existing execution propagation:** dynamic edges, ready dispatch, failure blocking, restart invalidation and terminal checks; these are not MAG composite/tick rules [E3], [E22] | Native execution graph is authoritative. Composite annotations/rubric views project native results; accept ordering changes instead of preserving tick admission |
| Task removal, reassignment, edge editing | Domain actions modify mutable workflow state [M4] | **Partial/missing:** cancel/refine/restart available; no equivalent public reassign or post-creation edge-edit contract [E3], [E4] | Use native cancel/refine/restart restrictions after creation; edit unbound input data beforehand. Proposed unsupported post-creation edits are explicit action results |
| Actor messaging | Direct, multicast, broadcast, thread/task filters, synchronous tool reads, end flag [M8] | **Partial:** durable thread/message storage and dashboard events; no equivalent actor inbox/wakeup facade in `WorkerContext` [E4], [E7] | Existing service with scoped actor tools; proposed decision-index outbox delivery independent of task scheduling and normal result visibility |
| Changing stakeholder preferences | Timeline weights and persona-dependent message behavior [M7] | **Missing:** no domain preference schedule; terminal evaluators exist [E9] | Benchmark timeline/public profile; proposed event coordinate is manager decision index, with source differences recorded |
| Resources | UUID-addressed typed content passed from task outputs/dependencies [M2], [M3] | **Existing:** run-scoped/cross-task reads, file publication and explicit text/JSON value publication [E4], [E25] | Reuse producer publication, native IDs and normal availability with access scope. No tick-based withholding, root republishing or WorkerOutput blob transport |
| Observation privacy | Public stakeholder profile includes initial preference summary; future schedule and rubrics are not the manager contract [M7], [M10] | **Hazard:** generic ReAct appends full task payload to prompt [E5] | Typed public decision input; private scenario/evaluator state excluded from policy payload |
| Structured manager actions | Fresh observation-driven request, dynamic ID schema, exactly one action [M10] | **Partial:** ReAct captures traces but has fixed final-message output and different control flow [E5] | New policy worker with actual structured-decision behavior; reuse resolution and transcript capture |
| Native worker tools | Runner wiring differs from ToolFactory's default bundle [M5], [M6] | **Partial:** tools and serializable toolkit configs exist, but toolkit builder receives no `WorkerContext` [E5], [E6] | Native actor workers can use their execution context directly; extend toolkit signature only if reusable ReAct path needs it |
| Sandbox runtime | MAG calls models without per-agent external sandboxes [M3], [M6] | **Existing extension point:** mandatory task-bound Sandbox delegates to SandboxRuntime; deployed cleanup still has E2B-specific fallback [E15], [E23], [E24] | Keep existing lifecycle/backend first. Optional Task sandbox is unnecessary; cheaper runtime adapter only after measurement and cross-process lifecycle proof |
| Terminal reward | Weighted stakeholder preference utility; workflow evaluator diagnostics separate [M9] | **Existing/partial:** Criterion/Evaluator, result metadata, criterion evidence and sample summaries [E9], [E18], [E19] | Native criterion per selected definition; custom group aggregation, frozen preference weights and normalized score-scale metadata |
| Criterion scheduling | Source runs concurrent rubrics with semaphore cap 100 [M9] | **Existing serial path:** EvaluationService evaluates native criteria and retries whole evaluators [E18] | Serial first; conditional opt-in concurrency after latency measurement, preserving index-based result order [E19] |
| Invalid evaluation score | Source can turn judge errors/refusals into zero [M9], [M15] | **Gap:** `persist_failure` writes 0.0; nullable score and score aggregation already support exclusion [E18], [E20] | Explicit incomplete policy and null persisted score, retained error evidence, CLI/UI validity checks |
| Intermediate reward | EACH_TIMESTEP/BOTH/selected checkpoints exist, with selection quirks; runner selects ON_COMPLETION [M1], [M3], [M9] | **Partial:** episode/task reward plus context traces, no MAG clock-evaluation contract [E8], [E9] | Keep declarations; optional tick-evaluation profiles and dense training projection deferred from terminal-evaluation v1 |
| Model routing and usage | Several SDK paths plus decomposition and judges [M6], [M9], [M11] | **Existing:** central model resolution and PydanticAI transcript capture [E5] | Port every inference path, label by role, separate model charges from simulated labor cost |
| Training selection | Manager is the policy; team and judges define environment dynamics | **Partial:** actor read filters exist; trainer gathers every actor span [E8] | Stable identity/role provenance now; explicit trainer selection and alignment validation in later RL scope |
| End/cancel/horizon | Completion, shared end flag, or max ticks; source labels horizon as failed execution [M3] | **Partial:** cancellation/failure/finalization, but worker failure skips evaluators [E10] | Proposed: stop decisions, settle created native work, then a dependency-bound finalization task evaluates the frozen result. Runtime failures remain incomplete |
| Replay/resume | Source snapshot reconstruction supports re-evaluation; full in-flight restore is absent [M3] | **Existing normal replay:** worker spawning is step-memoized; arbitrary surrounding model calls/mutations are not [E21] | Prove native decisions, model calls, input state and spawn order across normal replay. No source two-tick gate; crash resume remains deferred |
| Inspection/UI | Per-timestep snapshots, messages, action traces, final metrics [M3] | **Existing/partial:** native graph, actor, communication, generation and resource views [E7], [E8] | Expose decision index, logical/native task IDs, actor input attempt IDs, hours and utility detail through existing views |
| Distribution | Scenarios under `examples/` excluded from wheel; agent/provider groups are not base dependencies [M12] | **Existing:** per-benchmark package and environment CLI metadata [E11] | Extract/package reusable scenario definitions; avoid installing MAG's entire FastAPI/docs/runtime stack in Ergon |

## Complete default action mapping

The source has 13 default actions, each consuming a tick. Preserve their definitions in the oracle. The proposed native mapping below consumes a manager decision and uses Ergon lifecycle restrictions; it does not promise identical edit behavior. These detailed restrictions remain proposals under the accepted native scheduler direction.

| MAG action | Observed source semantics | Proposed native implementation |
|---|---|---|
| `assign_task` | Validates IDs, sets assignee; no readiness/capacity/human-approval enforcement in `execute` | Bind Worker and concrete dependencies through spawn_task. Proposed restriction: unresolved prerequisite bindings must be established first; no pending-assignment queue |
| `create_task` | Adds unassigned task with inputs/dependencies and estimates | Create unbound input data; executable creation uses spawn_task once Worker/prerequisites can be bound |
| `remove_task` | Deletes registry entry; not Ergon's recursive cancel/invalidation semantics | Delete unbound input; bound work uses native cancel and its actual propagation consequences |
| `refine_task` | Name, description, estimates, manager instruction notes; no RUNNING-state guard | Edit unbound input or invoke native refine_task; reject running-task edits as core does |
| `add_task_dependency` | Edits dependencies, attempts cycle prevention | Edit prerequisites before creating a Task; reject unsupported post-creation edge edits |
| `remove_task_dependency` | Edits logical prerequisites | Edit unbound prerequisites; do not rewrite live edges through a separate domain graph |
| `decompose_task` | Calls a helper model (default `o3`), creates nested tasks, inherits resources | Native helper with original prompt/schema and inherited resources; result visibility follows native completion |
| `inspect_task` | Returns detailed task state | Read public native task/resource state; consume a manager decision |
| `get_workflow_status` | Returns workflow status/progress | Read native result/status projection; consume a manager decision |
| `get_available_agents` | Uses agent `is_available`, not an enforced scheduler capacity bound | Read roster under the proposed event index; consume a manager decision |
| `get_pending_tasks` | Returns source-defined pending/ready view | Read native pending/readiness state and separately labeled unbound descriptions; consume a decision |
| `send_message` | Direct or broadcast as `manager_agent`; visible to worker tools/stakeholder policy | Existing communication with scoped sender/recipient tools and captured decision context |
| `noop` | Advances execution despite taking no mutation action | Consume one decision; no collection cycle or task dispatch barrier |

Source: [manager actions][M4] and [default list][M13]. `AssignTasksToAgentsAction` and `AssignAllPendingTasksAction` support the bulk baseline; they are not two additional CoT actions. `FailedAction` is a failed-decision record. `RequestEndWorkflowAction` exists but is absent from the default manager list. Workers' `end_workflow` tool remains a termination path.

## New agent implementations

Use existing `Worker`, `WorkerOutput`, model resolution, and transcript conversion. A new class is warranted for a different algorithm or output/state contract; factories should supply scenario prompts and personas. The names below are proposed, not existing exports.

| Component | Required behavior | Reuse / implementation boundary |
|---|---|---|
| `ManagerGymCoordinator` | Earlier dedicated clock/state coordinator | Withdrawn: use native manager task tools and a dependency-bound finalization task. Neither owns task scheduling or result admission |
| `ManagerGymPolicyWorker` | Fresh observation and one structured action per decision | Native manager control flow using task tools; capture decisions separately without requiring one Task per decision. Share existing inference helpers |
| `ManagerGymAIWorker` | Structured resources, reasoning, execution notes, model usage and elapsed-duration behavior | New typed-output work algorithm using existing provider/capture helpers |
| `ManagerGymHumanWorker` | Persona, fatigue, speed/quality sampling, misunderstanding branch, optional duration estimator, wage cost, updated actor state | New stateful simulated-worker algorithm. Time estimator is an internal labeled model call, not another top-level actor abstraction |
| `ManagerGymStakeholderWorker` | Assigned stakeholder work, structured artifacts and model traces | New role configuration/implementation where its output failure behavior differs from AI work. Reuse common execution helpers |
| Stakeholder tick policy | Rules/RNG, due replies, sampled delay and suggestions | Proposed manager decision-index processing, independent of task completion. Preserve non-LLM policy logic and document changed timing |
| `ManagerGymDecomposerWorker` | Existing decomposition prompt, schema and resource inheritance; default model recorded | New helper-worker implementation, excluded from manager training |
| Scripted smoke manager/team | Fixed actions/results for retained-formula and native-flow checks | Test-support workers; source scheduling equality is not a gate. RandomV2 and bulk LLM baselines are not offline |

Model configuration must include manager, AI, human, stakeholder, decomposer, and judge roles. The current upstream factory's `assign_all` constructor also omits the passed model argument, leaving its class default; a native factory must not silently claim that all requested model overrides are honored in the reference.

## Material findings and required decisions

### F1. Future preference updates rewrite earlier weights

**Experiment:** construct 0.5 quality / 0.5 speed at tick 0, schedule absolute 0.9 / 0.1 at tick 10, then reread tick 0. **Expected:** tick 0 stays 0.5 / 0.5. **Observed:** tick 0 becomes 0.9 / 0.1. **Meaning:** preloaded schedule construction can leak future preference changes into earlier scoring. **Proposed fix:** copy preference entries before mutation and preserve immutable timeline snapshots in the native version. Keep the upstream result as a regression characterization. [Probe evidence](evidence/mag-inventory-and-probes.json), [source][M7].

### F2. Rubric model configuration does not reach the judge

**Experiment:** set `WorkflowRubric.llm_model='sentinel-model'`; intercept the constructed validation rule. **Expected:** the requested model is forwarded. **Observed:** the rule uses `o3`. **Meaning:** the older draft's rubric override pass would not actually change judge calls. **Proposed fix:** pass the model explicitly in native evaluation and test invocation metadata; never silently fall back when unsupported. [Probe evidence](evidence/mag-inventory-and-probes.json), [source][M9].

### F3. Capacity metadata is not a scheduler constraint

**Experiment:** preassign two independent tasks to one stub human with capacity 1 and execute one tick. **Expected from the capacity field:** one starts. **Observed:** two start. **Meaning:** serializing each human in the port would change task parallelism and fatigue/RNG interleaving. **Proposed handling:** characterize concurrent state behavior before extraction; do not add enforced capacity accidentally. If approved later, implement explicit queue/rejection semantics as a corrected benchmark rule. [Probe evidence](evidence/mag-inventory-and-probes.json), [engine][M3], [agent interface][M14].

### F4. The reference runner's reachable tools differ from the advertised defaults

**Experiment:** schedule the ICAAP tick-0 team through the real registry with communication injection and inspect SDK tools. **Expected from reading ToolFactory alone:** search, analysis, and role-specific tools. **Observed:** communication-only bundles, duplicate `send_message` / `broadcast_message` / `get_recent_messages`, and `end_workflow`. **Meaning:** installing real search/coding tools is not a neutral port. **Proposed handling:** snapshot actual per-role tool contracts and preserve reachable capability before any cleanup. Duplicate dispatch behavior under the live SDK remains unverified. [Probe evidence](evidence/mag-inventory-and-probes.json), [registry][M5].

### F5. ReAct loop count and policy interface differ

**Experiment:** run PydanticAI `TestModel` through one tool call and a final structured answer in Ergon's venv. **Expected if iterations meant actions:** one or two. **Observed:** `UserPromptNode`, `ModelRequestNode`, `CallToolsNode`, `ModelRequestNode`, `CallToolsNode`, `End`: 6 nodes. **Meaning:** `max_timesteps + 8` is not a faithful horizon conversion. ReAct also has no serialized model-settings override forwarded for `parallel_tool_calls`, and its output is a final message rather than a MAG action. **Proposed fix:** a structured single-action decision boundary within native manager control, with separate decision and provider-attempt budgets. [ReAct source][E5], [upstream manager][M10].

### F6. Finalization in a criterion misses the failed-worker path

**Experiment:** trace `task/execute`'s `worker_result.success == False` branch. **Expected under the earlier draft:** the episode criterion finalizes an interrupted simulator. **Observed:** runtime persists outputs, finalizes failure and returns before evaluator fanout. Successful execution also persists outputs before evaluation. **Meaning:** criterion-driven finalization cannot be the normal episode completion mechanism. **Proposed fix:** a native finalization task depends on the required work and publishes before its evaluator runs; runtime errors remain incomplete attempts. [Runtime source][E10].

### F7. Actor identity and training selection are insufficient for a native team

**Experiment:** follow spawn's `assigned_worker_slug=task.worker.type_slug`, actor reconstruction, and trainer grouping. **Expected:** two same-class humans remain distinct people; only manager data is selected in a future training run. **Observed:** actor reconstruction derives slug from worker type on this path, spans group by actor slug, and trainer iterates every span. **Meaning:** same-class actor trajectories may collapse and environment generations can enter policy training. **Proposed fix:** explicit per-sample actor binding/role metadata now; trainer selection by role later. Verify with two identical worker classes under different actor keys and one repeated actor across tasks. This is source-proven dataflow; a DB-backed reproduction is a PR gate. Evaluation acceptance does not assert trainer readiness. [Spawn][E3], [actor reconstruction][E13], [projection][E14], [trainer][E8].

### F8. Error-as-zero can make model outages look like policy failures

**Experiment:** trace rubric exception handling and the nested validation-rule result conversion. **Expected for a valid benchmark reward:** every required rubric is evaluated, or evaluation is explicitly incomplete. **Observed:** exceptions/refusals can become score 0, and nested validation errors are not uniformly propagated into the outer rubric error field. **Meaning:** checking only utility, or only outer errors, is insufficient. **Proposed fix:** native inference/evaluator errors remain typed and separate from valid low scores; preserve reference values only for characterization. [Validation engine][M9], [validation rules][M15].

### F9. Human fatigue cannot be reconstructed by summing arbitrary task rows

**Inspection:** the normal human path increments hours/count; the misunderstanding path reports simulated duration/cost but returns without those increments. `hours_worked_today` has no daily-reset rule. The same Python actor can handle overlapping tasks and observe timing-dependent mutable state. **Meaning:** summing arbitrary PostgreSQL rows can double-count attempts or include another actor/episode. Native scheduling intentionally changes which completed work a human observes. **Updated design:** source formula over eligible completed native work at invocation start, with exact input attempt IDs and draws retained for replay; no source admission ledger. Counting misunderstood work remains a separate proposed correction. These are source findings, not new live or PostgreSQL experiments. [Human actor][M6], [task-output records][E16], [sample events][E17].

### F10. Native rubric execution needs order, scale and error-validity contracts

**Inspection:** Ergon awaits criteria serially; its summary mapper pairs returned outcomes with specs by list index. `aggregate_task` can compute custom utility, but normalized scale requires metadata. `persist_failure` currently writes a score of zero, which sample aggregation includes. **Meaning:** blindly parallelizing by completion order can mislabel outcomes, and merely raising judge exceptions still records invalid zero performance. **Proposed design:** retain serial execution initially; if concurrency is later justified, preserve definition order. Use `score_scale=normalized_0_1` and explicit incomplete persistence through the existing nullable score. Test the whole persistence/inspection path, including all-error samples. [Evaluation service][E18], [summary mapping][E19], [score aggregation][E20].

### F11. Rubric declarations and actual execution selection differ

**Offline inventory:** 1,281 definitions (540 preference, 741 diagnostic), including 876 LLM definitions. The ordinary final path selects 1,230 definitions: all diagnostic rubrics and preference rubrics declared `ON_COMPLETION`. There are 51 preference rubrics inactive in that profile. Source preference selection compares cadence by equality, so `BOTH` is not expanded; no registered definition uses `BOTH`. **Proposed handling:** retain definitions, port actual terminal selection, defer optional tick profiles and their corrections explicitly. The [CSV manifest](evidence/rubric-inventory.csv) records every definition and final-selection flag. [Validation engine][M9].

## Scenario coverage

Counts include nested nodes once by UUID; additions exclude the separate stakeholder. “Late event” means at least one team/preference event at tick >= 50. LLM rubrics are selected final-evaluation definitions, not measured requests.

| Scenario | Logical nodes | Atomic | Team +/− | Preferences | Final LLM rubrics | Late event |
|---|---:|---:|---:|---:|---:|---|
| icaap | 39 | 30 | 10/0 | 5 | 54 | yes |
| marketing_campaign | 51 | 37 | 29/3 | 4 | 35 | yes |
| data_science_analytics | 21 | 19 | 6/0 | 7 | 42 | yes |
| orsa | 30 | 25 | 22/3 | 4 | 36 | yes |
| legal_contract_negotiation | 23 | 18 | 11/0 | 6 | 40 | no |
| supply_chain_planning | 25 | 22 | 11/3 | 4 | 38 | no |
| legal_litigation_ediscovery | 14 | 10 | 5/0 | 5 | 34 | no |
| legal_m_and_a | 17 | 16 | 23/4 | 2 | 35 | yes |
| global_product_recall | 49 | 37 | 24/0 | 7 | 59 | yes |
| brand_crisis_management | 40 | 29 | 16/0 | 6 | 52 | no |
| banking_license_application | 58 | 44 | 21/0 | 8 | 67 | no |
| tech_company_acquisition | 43 | 32 | 16/0 | 6 | 46 | no |
| legal_global_data_breach | 36 | 29 | 12/4 | 4 | 32 | no |
| enterprise_saas_negotiation_pipeline | 33 | 27 | 12/3 | 4 | 33 | no |
| mnc_workforce_restructuring | 41 | 33 | 12/4 | 5 | 34 | no |
| genai_feature_launch | 42 | 32 | 16/0 | 5 | 41 | no |
| ipo_readiness_program | 26 | 20 | 16/0 | 6 | 49 | no |
| pharmaceutical_product_launch | 30 | 23 | 17/0 | 7 | 47 | yes |
| uk_university_accreditation | 36 | 27 | 15/0 | 6 | 49 | no |
| airline_launch_program | 40 | 31 | 18/0 | 7 | 53 | no |

The inventory is a data/construction audit, not 20 completed episodes. Native action coverage and documented supported/restricted outcomes are still required; identical source scheduling is not. Recommended coverage progression: smallest real scenario (`legal_litigation_ediscovery`); ICAAP for nested composition, later arrivals and preference schedule; `marketing_campaign` for largest roster and departures; `banking_license_application` for maximum node/judge load; then every registered scenario.

## Source index

MAG links are pinned. Ergon links point at the inspected working tree, so line content can change during implementation.

[M1]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/examples/run_examples.py
[M2]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/schemas/core/workflow.py
[M3]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/execution/engine.py
[M4]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/schemas/execution/manager_actions.py
[M5]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/workflow_agents/registry.py
[M6]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/workflow_agents/human_agent.py
[M7]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/workflow_agents/stakeholder_agent.py
[M8]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/communication/service.py
[M9]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/evaluation/validation_engine.py
[M10]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/manager_agent/structured_manager.py
[M11]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/decomposition/service.py
[M12]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/pyproject.toml
[M13]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/manager_agent/llm_action_utils.py
[M14]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/workflow_agents/interface.py
[M15]: https://github.com/DeepFlow-research/manager_agent_gym/blob/3f7a5d4af1d31abaedbedd525a0090452926fef4/manager_agent_gym/core/evaluation/validation_rules.py
[E1]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/api/experiment/environment.py
[E2]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/api/task.py
[E3]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/runtime/task_management.py
[E4]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/api/worker/context.py
[E5]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_builtins/ergon_builtins/agents/react/worker.py
[E6]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_builtins/ergon_builtins/toolkits/common/base.py
[E7]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/communication/service.py
[E8]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/rl/rollout_service.py
[E9]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/api/rubric/rubric.py
[E10]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/jobs/task/execute/job.py
[E11]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_builtins/ergon_builtins/environments/catalog.py
[E12]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/api/worker/results.py
[E13]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/views/rl/actor_state.py
[E14]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/views/rl/projections.py
[E15]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/jobs/task/worker_execute/job.py
[E16]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/persistence/telemetry/models.py
[E17]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/persistence/samples/models.py
[E18]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/evaluation/service.py
[E19]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/evaluation/mappers.py
[E20]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/evaluation/scoring.py
[E21]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/jobs/task/worker_execute/job.py
[E22]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/runtime/lifecycle.py
[E23]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/api/sandbox/runtime.py
[E24]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/infrastructure/sandbox/lifecycle.py
[E25]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/resources/publishing.py
[E26]: /Users/charlie.masters/Desktop/ergon_folder/ergon/ergon_core/ergon_core/core/application/runtime/task_inspection.py
