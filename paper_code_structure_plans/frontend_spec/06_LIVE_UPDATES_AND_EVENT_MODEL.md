# Live Updates And Event Model

## Core Model

The frontend should behave like:

1. load a snapshot of current backend truth
2. subscribe to live updates
3. apply those updates without corrupting identity or ordering
4. rerender the affected views

This is the expected mental model even if the transport changes later.

## Transport Is Secondary

The product behavior matters more than whether updates arrive via:

- websocket
- SSE
- polling
- replay endpoint

Tests should care primarily about semantic correctness.

Chronological fidelity matters.

The frontend should preserve event ordering honestly, especially inside:

- the actions timeline
- the communication thread
- the raw events drawer

## Snapshot Requirements

The initial snapshot should be sufficient to render:

- run summary
- graph structure
- current task statuses
- existing actions
- existing outputs
- existing evaluation state

If the UI needs too many hidden follow-up fetches before it can render basic truth, it becomes hard to debug.

## Update Semantics

Live updates should be able to:

- advance run status
- advance task status
- change task topology
- create or update execution attempts
- append action history
- append communication history
- surface new outputs
- surface new evaluation data
- surface failure details

The UI should not require a full refresh for meaningful state changes.

## Update Taxonomy

The frontend should explicitly model the kinds of changes it can receive.

### 1. Run-Level Updates

Examples:

- run created
- run status changed
- run completed
- run failed
- run-level score or summary arrived

Primary surfaces:

- runs list
- run header

### 2. Task Topology Updates

Examples:

- task added
- task removed or invalidated
- dependency edge added
- dependency edge removed

Primary surfaces:

- graph region

Secondary effects:

- selection validity
- structural progress understanding

### 3. Task Execution Updates

Examples:

- execution started
- execution completed
- execution failed
- retry started

Primary surfaces:

- graph node status
- task overview
- executions section

### 4. Action Updates

Examples:

- action started
- action completed
- action failed

Primary surfaces:

- actions section

Secondary effects:

- task summary counters
- task status if the action changes terminal state

### 5. Communication Updates

Examples:

- agent emitted a message
- stakeholder question was asked
- stakeholder answer arrived

Primary surfaces:

- communication section

These should be visually distinct from tool actions.

### 6. Output Updates

Examples:

- file produced
- resource recorded
- downloadable artifact became available

Primary surfaces:

- outputs section

Secondary effects:

- run summary for important final artifacts

### 7. Evaluation Updates

Examples:

- task evaluation result arrived
- run-level score updated
- criterion-level result arrived

Primary surfaces:

- evaluation section
- run header for run-level summary

### 8. Connection And Staleness Updates

Examples:

- connection lost
- event stream reconnected
- live view is stale

Primary surfaces:

- run header
- global page banner if needed

### 9. Raw Event Stream Updates

Examples:

- task status event emitted
- topology event emitted
- action event emitted
- communication event emitted

Primary surfaces:

- raw events drawer or panel on the run page

This surface should default to a filtered operator-relevant stream, while still allowing a rawer chronological toggle.

## Merge Semantics

Different update types should merge differently.

### Replace-In-Place Updates

These overwrite the current visible value for an existing entity:

- run status
- task status
- current execution status
- connection status

### Append-Only Updates

These should extend a chronological list rather than replace the whole section:

- actions
- communication messages
- execution history
- raw event stream entries

### Structural Updates

These modify topology and therefore require identity-safe graph reconciliation:

- new task
- removed task
- new edge
- removed edge

### Availability Updates

These make previously absent data visible:

- outputs
- evaluation results

## Ordering Expectations

The UI should preserve semantic ordering.

Examples:

- a task should not appear completed before it appears running
- a run should not appear completed before the relevant task changes are visible
- failure should replace running state rather than coexist ambiguously with it
- an output should not appear attached to the wrong task
- a stakeholder answer should not appear in the tool-action timeline

The exact global event stream may be too noisy for the main graph and workspace surfaces.

That is acceptable.

The requirement is:

- graph and workspace preserve truthful ordering within their own evidence surfaces
- the raw events drawer preserves a more literal chronological stream for deeper debugging

## Surface Routing Rules

The frontend should avoid broadcasting every update everywhere.

The intended behavior is:

- runs list gets lightweight run-level updates
- graph gets topology and task-status updates
- selected task detail gets deep evidence updates for the selected task
- non-selected tasks still show enough graph-level change to preserve situational awareness

This keeps the UI readable while still live.

## Partial State Handling

If the backend truth is partially present:

- the UI should render partial truth explicitly
- missing sections should appear as missing, not silently broken

Examples:

- action history exists but outputs are not yet present
- outputs exist but evaluation has not arrived yet
- run exists but graph update is still pending
- communication exists but evaluation does not
- a retry has started but no actions have completed yet

## Reconnection And Staleness Expectations

If live updates fail temporarily:

- the UI should not silently pretend nothing happened
- stale or disconnected state should be understandable

This does not require elaborate offline UX.

It does require that users are not misled by silently stale views.

## Browser-Test Implications

The browser suite should test these update families separately:

- topology changes
- execution changes
- action append behavior
- communication append behavior
- output availability
- evaluation arrival
- staleness and reconnection signaling
