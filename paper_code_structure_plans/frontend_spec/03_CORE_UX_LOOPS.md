# Core UX Loops

This document defines the main user journeys the frontend must support.

## Loop 0: Monitor An Experiment Cohort Live

User goal:

- understand live progress across many runs and drill into the right one quickly

Expected flow:

1. user opens a named experiment cohort
2. UI shows cohort summary counts and a large clickable list of runs
3. user sees which runs are queued, running, completed, or failed
4. user sees running time so far and benchmark identity for each run
5. user clicks into the run that needs inspection

Success condition:

- the cohort page behaves like a real operations surface rather than a dead catalog

## Loop 1: Inspect A Failed Run

User goal:

- understand what failed and why

Expected flow:

1. user sees a failed run in the runs list
2. user opens the run
3. graph highlights the failed task or tasks clearly
4. user selects the failed task
5. detail pane shows:
   - failure status
   - failure reason
   - last relevant actions
   - useful output or missing-output evidence
   - evaluation consequences if relevant

Success condition:

- the user does not need to guess which task failed or what evidence matters

## Loop 2: Watch A Run Progress Live

User goal:

- monitor execution confidently without manual refresh

Expected flow:

1. user opens a run that is pending or running
2. graph and summary show non-terminal state
3. task nodes update as the backend progresses
4. selected task detail updates if the selected task changes state
5. the run eventually transitions to completed or failed

Success condition:

- live updates feel ordered, trustworthy, and non-contradictory

Primary visible surfaces:

- runs list row or card updates run status
- run header updates overall status and timing
- graph updates node status and any topology changes
- selected task detail updates execution, actions, messages, outputs, and evaluation if they affect the selected task

## Loop 3: Inspect One Task In Detail

User goal:

- understand exactly what one task did

Expected flow:

1. user opens a run
2. user selects a task node
3. detail pane shows:
   - task identity
   - status
   - action history in order
   - outputs
   - errors
   - evaluation if present

Success condition:

- the detail pane acts like a useful task debugger

Primary visible surfaces:

- task overview for identity, attempt, and status
- outputs or artifacts as the primary evidence area when present
- action stream for completed or failed tool work
- outputs section for files and produced artifacts
- communication section for agent and stakeholder interaction
- evaluation section for task-level judgment

Default workspace rule:

- outputs and artifacts should be the primary pane when they exist
- when no outputs exist yet, the workspace should fall back dynamically based on task state

## Loop 4: Compare Graph Context To Detail Evidence

User goal:

- move between tasks without losing context

Expected flow:

1. user scans graph for problem area
2. user clicks task A and sees task A detail
3. user clicks task B and sees task B detail
4. the graph selection and detail pane remain synchronized

Success condition:

- there is no identity drift between selected node and displayed detail

Important live-update rule:

- if the selected task changes state while selected, the detail pane updates in place
- if another task changes state, the selected detail should remain stable while the graph still reflects the other task's new state

## Loop 5: Inspect Final Outputs And Evaluation

User goal:

- understand whether the run succeeded meaningfully, not just terminally

Expected flow:

1. user opens a completed run
2. UI shows final outputs and evaluation summary
3. user can inspect the relevant task and artifact
4. user can see whether evaluation aligns with visible outputs

Success condition:

- output and evaluation are visible enough to support judgment, not hidden behind implementation detail

## Loop 6: Recover From Partial Or Incomplete State

User goal:

- understand a run that is incomplete, delayed, or partially populated

Expected flow:

1. user opens a run with partial state
2. UI shows what exists and what is still missing
3. missing data is rendered as explicit absence, not silent breakage

Success condition:

- the UI degrades clearly instead of appearing broken or misleading

## Loop 7: Follow Execution Attempts And Retries

User goal:

- understand whether a task is on its first attempt, retrying, or has failed after one or more executions

Expected flow:

1. user selects a task
2. UI shows current execution attempt and status
3. if a retry occurs, the execution view shows a new attempt rather than overwriting history silently
4. the action stream remains attributable to the correct execution attempt

Success condition:

- retries and re-executions are visible and interpretable instead of being flattened into one ambiguous status

## Loop 8: Follow New Actions As They Complete

User goal:

- understand step-by-step what the worker is doing

Expected flow:

1. user selects a running task
2. new actions appear in time order
3. each action becomes visibly completed or failed
4. if an output is produced, the related artifact becomes visible from the same task detail context

Success condition:

- action progress reads like a trustworthy execution timeline rather than a vague spinner

## Loop 9: Follow Agent And Stakeholder Communication

User goal:

- understand when the system asked for clarification, received input, or emitted important agent-visible reasoning context

Expected flow:

1. user selects a task with communication activity
2. UI shows agent messages, stakeholder questions, and stakeholder answers in chronological order
3. communication items are visually distinct from tool actions
4. the user can tell which message changed task behavior

Success condition:

- communication is inspectable as part of task evidence, not hidden as an implementation detail

## Loop 10: Observe Topology Changes Safely

User goal:

- understand when the task graph itself changes during execution

Expected flow:

1. user opens a run whose graph can change over time
2. UI preserves stable identity for existing nodes
3. if a new node or edge appears, the graph updates without breaking selection
4. if the selected task still exists, detail stays bound to it
5. if the selected task becomes invalid, the UI resets selection explicitly

Success condition:

- topology changes are understandable and do not corrupt the user's mental model

## Loop 11: Inspect Raw Event Fidelity Without Leaving The Run

User goal:

- inspect exact chronological workflow events when graph and workspace summaries are not enough

Expected flow:

1. user opens a run page
2. user opens the raw events drawer or panel
3. UI shows filtered operator-relevant events by default
4. user can switch to a rawer event view if needed
5. user can filter the run event stream down to the selected task

Success condition:

- raw chronological evidence is available as a secondary debugging tool without becoming the main workflow

## Update Types The UI Must Handle

The frontend should explicitly expect these categories of incoming updates:

- run status updates
- task status updates
- task topology changes
- task execution attempt changes
- new actions starting, completing, or failing
- new outputs or resources becoming available
- new evaluation results becoming available
- agent and stakeholder communication updates
- connection or staleness state updates

Each of these should have:

- a defined visual home
- a defined visual treatment
- a defined merge rule with existing state
