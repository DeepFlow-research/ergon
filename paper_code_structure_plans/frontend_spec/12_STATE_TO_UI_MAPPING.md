# State To UI Mapping

This document maps backend truth to frontend surfaces.

Its purpose is to stop the frontend from inventing a parallel product model that drifts away from persisted state.

## Core Rule

The frontend should treat:

- persisted backend state as the authoritative snapshot
- live events as deltas that update that snapshot

The frontend may derive presentation state such as:

- current selection
- expanded or collapsed sections
- local layout preferences
- unread or highlighted affordances

The frontend must not derive domain truth such as:

- task completion that the backend has not persisted
- output existence that the backend has not recorded
- evaluation results that only exist as UI guesses

## Two Layers Of Truth

### Snapshot Truth

Snapshot truth is what the page should be able to render from a fetch alone.

This should come from persisted records and domain DTOs derived from them.

### Delta Truth

Delta truth is the stream of updates that advances the visible page without a full refresh.

These events should merge into the snapshot model without breaking identity or chronology.

## Entity-To-Surface Mapping

## `Experiment Cohort`

Primary meaning:

- the top-level named grouping of runs the operator is monitoring

Important fields and signals:

- cohort identity
- mixed benchmark membership
- reproducibility metadata
- status counts across runs
- aggregate score and duration summaries

Primary UI surfaces:

- cohort page header
- cohort summary cards
- cohort run list

Useful reproducibility metadata may include:

- code commit or snapshot id
- worker or prompt version
- model or provider version
- tool or sandbox config snapshot

This likely requires backend lineage and query support rather than being only an FE concern.

## `Experiment`

Primary meaning:

- benchmark context
- task archetype context
- experiment metadata that explains what kind of run the user is looking at

Primary UI surfaces:

- runs list secondary context
- run header benchmark and experiment metadata

Not a primary graph or workspace evidence record by itself.

## `Run`

Primary meaning:

- the top-level execution unit the user is triaging and inspecting

Important fields and signals:

- run identity
- terminal or non-terminal status
- error summary
- high-level score
- sandbox lifecycle indicators where surfaced
- `questions_asked` when stakeholder interaction matters

Primary UI surfaces:

- runs list row or card
- run header

Secondary surfaces:

- graph-level run status framing
- workspace header only when useful as contextual metadata

When a cohort mixes benchmarks:

- benchmark identity should remain visible per run on the cohort page

## Task Identity And Task Graph State

Primary meaning:

- the structural topology of work
- task-level status within the run

This state may be represented by one or more backend models or DTOs, but the frontend should treat it as one stable graph truth source.

Important signals:

- task id
- task name
- task status
- parent, child, or dependency relationships
- structural additions or removals

Primary UI surfaces:

- graph view nodes
- graph view edges
- workspace header for the selected task

Secondary surfaces:

- run header task counts if shown

## `TaskExecution`

Primary meaning:

- a concrete execution attempt for a task

Important signals:

- execution attempt identity
- status
- start and end timing
- retry boundaries
- currently active attempt

Primary UI surfaces:

- workspace header
- workspace `Executions` section

Secondary surfaces:

- graph node badges or retry markers

The frontend should never flatten multiple execution attempts into one ambiguous task status if retry history matters.

## `Action`

Primary meaning:

- the ordered sequence of worker or tool operations taken during task execution

Important signals:

- action name
- order
- success or failure
- serialized payload summary
- relation to task and execution

Primary UI surfaces:

- workspace `Actions` section

Secondary surfaces:

- workspace overview counters
- graph node summaries only if extremely lightweight

Actions should render as a chronological operation timeline, not as chat.

## `ResourceRecord`

Primary meaning:

- persisted outputs and artifacts that the run or task produced

Important signals:

- resource identity
- output name
- output path or download reference
- whether the record is a final artifact versus intermediate scratch state

Primary UI surfaces:

- workspace `Outputs` section

Secondary surfaces:

- run header final-output indicators
- workspace primary evidence area when outputs are the main thing to inspect

The UI should not imply that an output exists until a `ResourceRecord` or equivalent persisted output contract says it exists.

## `Evaluation` And `CriterionResult`

Primary meaning:

- the system's judgment over run or task outcomes

Important signals:

- verdict
- score
- criterion-level reasoning or result

Primary UI surfaces:

- workspace `Evaluation` section
- run header score or verdict summary when run-scoped

Secondary surfaces:

- runs list summary score if useful for triage

Evaluation should render as judgment, not as raw logs.

## `Thread` And `ThreadMessage`

Primary meaning:

- agent-to-agent or agent-to-stakeholder communication history

Important signals:

- thread identity and topic
- ordered message sequence
- sender and recipient identity
- created time
- message count

Primary UI surfaces:

- workspace `Communication` section

Secondary surfaces:

- workspace header thread summary or question count if useful

Communication should render as a message thread, not as a tool-action timeline.

For v1:

- communication does not need a dedicated graph signal

This matters especially because backend state tests already care about persisted `Thread` and `ThreadMessage` rows for stakeholder flows.

## `TaskStateEvent` And Dashboard Event Contracts

Primary meaning:

- incremental updates that keep the page live

Important signals:

- status change
- topology change
- action append
- output availability
- evaluation arrival
- communication arrival

Primary UI surfaces:

- graph view for structural and status changes
- workspace sections for deep evidence changes on the selected task
- run header for connection and live-status framing

Important rule:

- these events are not the primary long-term source of truth

They are the mechanism for updating the visible projection between snapshots.

## Raw Event Stream

Primary meaning:

- an operator-facing chronological debugging feed for one run

Important signals:

- exact event ordering
- event type
- associated task where relevant
- ability to inspect a filtered stream by default

Primary UI surfaces:

- raw events drawer or panel attached to the run page

Secondary behavior:

- task filtering within the run-scoped event drawer

This is a secondary debugging surface, not the primary place the user should have to understand the run.

## Surface-To-Source Mapping

## Cohort View

Should primarily be driven by:

- `Experiment Cohort`
- `Run`
- enough `Experiment` context for per-run labeling

Should render:

- total runs
- runs grouped by status
- average score
- best and worst score
- duration summaries
- failure-rate summaries
- benchmark identity for each run when cohorts are mixed

## Runs List

Should primarily be driven by:

- `Run`
- enough `Experiment` context for labeling

May include light derived presentation such as:

- relative time
- sorting
- filter state

Should not need:

- full action history
- full thread history
- full evaluation detail

## Run Header

Should primarily be driven by:

- `Run`
- `Experiment`
- run-scoped evaluation summary when available

May include:

- staleness or connection state from the live-update layer
- breadcrumb context back to the cohort view

## Graph View

Should primarily be driven by:

- task graph state
- task statuses
- task execution badges where needed

May react to:

- topology events
- task status events
- retry or execution updates

Should not be the primary place for:

- dense action payloads
- dense chat history
- criterion detail

## Workspace Header

Should primarily be driven by:

- selected task identity
- selected `TaskExecution` summary
- selected task status

May include:

- latest output or evaluation summary
- latest update time

## Workspace `Executions`

Should primarily be driven by:

- `TaskExecution`

Merge behavior:

- append a new attempt when retry starts
- update the current attempt in place as its status changes

## Workspace `Actions`

Should primarily be driven by:

- `Action`

Merge behavior:

- append ordered actions
- update the visible state of an action if it moves from started to completed or failed

## Workspace `Communication`

Should primarily be driven by:

- `Thread`
- `ThreadMessage`

Merge behavior:

- append new messages in sequence order
- preserve thread grouping and chronology

This section should remain task-scoped rather than becoming a graph-level summary surface.

## Workspace `Outputs`

Should primarily be driven by:

- `ResourceRecord`

Merge behavior:

- reveal newly available artifacts
- update output state without inventing files early

## Workspace `Evaluation`

Should primarily be driven by:

- `Evaluation`
- `CriterionResult`

Merge behavior:

- reveal evaluation when it exists
- update summary and criterion-level state at the right scope

## Raw Events Drawer

Should primarily be driven by:

- raw event stream contracts
- run-scoped event history

Merge behavior:

- append events in chronological order
- allow filtering to the selected task without changing the underlying run-scoped truth

## Update-Family Mapping

## Cohort Aggregate Updated

Source of truth:

- cohort aggregate state or cohort query layer over runs

Primary UI updates:

- cohort summary cards
- cohort status counts
- cohort run list ordering or progress signals

## Run Status Changed

Source of truth:

- `Run.status`

Primary UI updates:

- runs list status
- run header status

## Task Status Changed

Source of truth:

- task graph state and task-level status persistence

Primary UI updates:

- graph node status
- workspace header if selected

## Task Topology Changed

Source of truth:

- task graph state and topology DTOs

Primary UI updates:

- graph nodes and edges
- selection validity checks

## Execution Started, Failed, Completed, Or Retried

Source of truth:

- `TaskExecution`

Primary UI updates:

- workspace header
- workspace `Executions`
- graph retry or activity markers

## Action Started, Failed, Or Completed

Source of truth:

- `Action`

Primary UI updates:

- workspace `Actions`

## Message Or Question Arrived

Source of truth:

- `Thread`
- `ThreadMessage`
- `Run.questions_asked` when a run-level summary count is useful

Primary UI updates:

- workspace `Communication`
- optional run or workspace summary badges

## Output Became Available

Source of truth:

- `ResourceRecord`

Primary UI updates:

- workspace `Outputs`
- optional workspace primary evidence area

## Evaluation Arrived

Source of truth:

- `Evaluation`
- `CriterionResult`

Primary UI updates:

- workspace `Evaluation`
- run header or runs list summary if scoped that way

## Connection Became Stale Or Reconnected

Source of truth:

- live transport state and freshness bookkeeping

Primary UI updates:

- run header
- global page banner if needed

This is one of the few important UI states that is not persisted domain truth.

## Raw Event Arrived

Source of truth:

- dashboard event contracts

Primary UI updates:

- raw events drawer stream

## Merge Rules

The frontend should merge different data shapes differently.

### Replace In Place

Use for:

- run status
- task status
- current execution status
- connection state

### Append In Order

Use for:

- actions
- thread messages
- execution history

### Structural Reconcile

Use for:

- node insertion
- edge insertion
- node removal if supported
- graph regrouping

### Reveal When Available

Use for:

- outputs
- evaluation

## Things The UI May Derive Locally

The frontend may safely derive:

- selected task
- panel layout
- scroll position
- active workspace tab
- hover affordances
- temporary highlight of newly changed nodes or rows

These are view concerns, not domain truth.

## Things The UI Must Not Invent

The frontend must not invent:

- a completed output before persisted output truth exists
- an evaluation verdict before evaluation truth exists
- reordered action chronology
- reordered thread chronology
- task identity changes caused by layout churn

## Test Implications

Seeded-state browser tests should prove:

- each section renders from the right persisted source
- communication does not land in actions
- outputs do not appear before output persistence
- evaluation does not appear at the wrong scope

Controlled-event browser tests should prove:

- status replaces in place
- actions append in order
- messages append in order
- topology changes preserve identity
- output and evaluation become visible only when available
