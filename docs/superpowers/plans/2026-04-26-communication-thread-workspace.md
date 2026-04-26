# Communication Thread Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make inter-agent communication a first-class, time-aware workspace view with agent-authored thread summaries, task anchoring, and a clickable WhatsApp-style thread trace.

**Architecture:** Extend the communication schema from agent tool request through persistence, dashboard DTOs, live events, run snapshots, and frontend rendering. Preserve the current `(run_id, topic)` thread identity and add nullable `summary` metadata so agents can set a human-readable thread summary when creating the first message. Frontend should work with summary absent, but prefer it when present.

**Tech Stack:** Python, SQLModel/Alembic, Pydantic DTOs, dashboard event contracts, React/TypeScript, Playwright.

---

## File Structure

- Modify `ergon_core/ergon_core/core/runtime/services/communication_schemas.py`: add nullable `thread_summary` to `CreateMessageRequest`, `ThreadSummary`, and `ThreadWithMessages`.
- Modify `ergon_core/ergon_core/core/persistence/telemetry/models.py`: add nullable `summary` column to `Thread`.
- Create migration under `ergon_core/migrations/versions/`: add nullable `summary` column to `threads`.
- Modify `ergon_core/ergon_core/core/runtime/services/communication_service.py`: persist `thread_summary` only when creating a thread or when an existing thread has no summary.
- Modify `ergon_core/ergon_core/core/api/schemas.py`: add nullable `summary` to `RunCommunicationThreadDto`.
- Modify `ergon_core/ergon_core/core/api/runs.py`: populate `thread.summary`, `thread.task_id`, and `message.task_id` in `_build_communication_threads`.
- Modify `ergon_core/ergon_core/core/dashboard/event_contracts.py` only if generated event contracts need explicit schema references refreshed.
- Modify `ergon-dashboard/src/generated/rest/contracts.ts` after schema generation or manually in lockstep if generation is not available in this branch.
- Modify `ergon-dashboard/src/lib/contracts/rest.ts`: ensure normalized `RunCommunicationThread` includes `summary: string | null`.
- Modify `ergon-dashboard/src/components/panels/CommunicationPanel.tsx`: replace always-expanded cards with thread list + selected chat trace.
- Modify `ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.ts`: keep existing time filtering, and ensure summaries/counts are based on visible messages at selected time.
- Test `tests/unit/smoke_base/test_leaf_sends_completion_message.py`: existing callers remain valid without summaries.
- Test `tests/unit/dashboard/test_event_contract_types.py`: DTO exposes `summary`, `task_id`, and `task_execution_id`.
- Add backend unit tests for communication summary persistence and task anchoring.
- Update Playwright tests in `ergon-dashboard/tests/e2e/run.snapshot.spec.ts` or `run.delta.spec.ts` for clickable thread list and chat bubbles.

---

## Task 1: Extend Communication Schema and Persistence

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/communication_schemas.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Create: `ergon_core/migrations/versions/<revision>_add_thread_summary.py`
- Test: `tests/unit/smoke_base/test_leaf_sends_completion_message.py`

- [ ] **Step 1: Write compatibility assertion for summary-optional requests**

Add to `tests/unit/smoke_base/test_leaf_sends_completion_message.py` inside `test_send_completion_message_posts_request`:

```python
assert req.thread_summary is None
```

- [ ] **Step 2: Run test to verify current schema fails**

Run:

```bash
pytest tests/unit/smoke_base/test_leaf_sends_completion_message.py::test_send_completion_message_posts_request -q
```

Expected: FAIL because `CreateMessageRequest` has no `thread_summary` attribute.

- [ ] **Step 3: Add nullable summary field to request/response schemas**

In `communication_schemas.py`, update `CreateMessageRequest`:

```python
class CreateMessageRequest(BaseModel):
    run_id: UUID
    from_agent_id: str = Field(
        description="ID of the sending agent, e.g. '{run_id}:worker'",
    )
    to_agent_id: str = Field(
        description="ID of the receiving agent, e.g. '{run_id}:stakeholder'",
    )
    thread_topic: str
    thread_summary: str | None = Field(
        default=None,
        description="Optional human-readable summary set when the thread is first created.",
    )
    content: str
    task_execution_id: UUID | None = None
```

Also add `summary: str | None = None` to `ThreadSummary` and `ThreadWithMessages`.

- [ ] **Step 4: Add persistence field**

In `models.py`, add to `Thread`:

```python
summary: str | None = None
```

- [ ] **Step 5: Add migration**

Create an Alembic migration adding:

```python
op.add_column("threads", sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
```

Downgrade removes the column.

- [ ] **Step 6: Run schema compatibility test**

Run:

```bash
pytest tests/unit/smoke_base/test_leaf_sends_completion_message.py::test_send_completion_message_posts_request -q
```

Expected: PASS.

---

## Task 2: Persist Agent-Authored Thread Summary

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/communication_service.py`
- Test: add or extend communication service unit test near existing service tests

- [ ] **Step 1: Write failing service test**

Create a test that calls `communication_service.save_message` with:

```python
CreateMessageRequest(
    run_id=run_id,
    from_agent_id="leaf-l_1",
    to_agent_id="parent",
    thread_topic="smoke-completion",
    thread_summary="Leaf workers report completion artifacts and probe exit status.",
    content="l_1: done exit=0",
    task_execution_id=execution_id,
)
```

Assert the persisted `Thread.summary` equals the provided summary.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit -q -k "communication and summary"
```

Expected: FAIL because `CommunicationService` does not persist summary.

- [ ] **Step 3: Update thread creation/update semantics**

In `CommunicationService.save_message`, pass `thread_summary=request.thread_summary` into `_get_or_create_thread`.

Update `_get_or_create_thread` signature:

```python
def _get_or_create_thread(
    session,
    *,
    run_id: UUID,
    agent_a_id: str,
    agent_b_id: str,
    topic: str,
    thread_summary: str | None = None,
) -> Thread:
```

When an existing thread is found:

```python
if existing is not None:
    if existing.summary is None and thread_summary:
        existing.summary = thread_summary
        session.add(existing)
    return existing
```

When creating:

```python
thread = Thread(run_id=run_id, topic=topic, agent_a_id=a, agent_b_id=b, summary=thread_summary)
```

- [ ] **Step 4: Include summary in service response DTOs**

When building `RunCommunicationThreadDto`, `ThreadSummary`, and `ThreadWithMessages`, populate `summary=thread.summary`.

- [ ] **Step 5: Run service tests**

Run:

```bash
pytest tests/unit -q -k "communication"
```

Expected: PASS.

---

## Task 3: Populate Dashboard Thread DTOs and Task Anchors

**Files:**
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Test: `tests/unit/dashboard/test_event_contract_types.py`
- Test: add focused test for `_build_communication_threads`

- [ ] **Step 1: Extend DTO contract test**

Add to `test_event_contract_types.py`:

```python
def test_thread_dto_exposes_summary_and_task_identity() -> None:
    assert "summary" in RunCommunicationThreadDto.model_fields
    assert "task_id" in RunCommunicationThreadDto.model_fields
    assert "task_id" in RunCommunicationMessageDto.model_fields
```

- [ ] **Step 2: Run contract test to verify failure**

Run:

```bash
pytest tests/unit/dashboard/test_event_contract_types.py -q
```

Expected: FAIL until `summary` is added.

- [ ] **Step 3: Add summary field to API schema**

In `RunCommunicationThreadDto`:

```python
summary: str | None = None
```

- [ ] **Step 4: Populate message task IDs in snapshots**

Update `_build_communication_threads` to accept `execution_task_map: dict[UUID, UUID]`.

For each message:

```python
task_id = execution_task_map.get(m.task_execution_id) if m.task_execution_id else None
```

Set:

```python
task_id=str(task_id) if task_id else None
```

on `RunCommunicationMessageDto`.

- [ ] **Step 5: Populate thread task ID**

For each thread, collect message task IDs. If exactly one unique non-null task ID exists, set `RunCommunicationThreadDto.task_id` to that ID. Otherwise set it to `None`.

- [ ] **Step 6: Pass execution map from run read service**

In `run_read_service.py`, change:

```python
threads=run_api_helpers._build_communication_threads(threads, thread_messages),
```

to:

```python
threads=run_api_helpers._build_communication_threads(
    threads,
    thread_messages,
    execution_task_map,
),
```

- [ ] **Step 7: Run backend contract tests**

Run:

```bash
pytest tests/unit/dashboard/test_event_contract_types.py -q
```

Expected: PASS.

---

## Task 4: Carry Summary and Anchors Through Live Events

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/communication_service.py`
- Modify: dashboard event contract tests if needed
- Test: add or extend dashboard event contract/unit test

- [ ] **Step 1: Write failing live event assertion**

In a communication service test, patch `dashboard_emitter.thread_message_created` and assert the emitted `thread.summary` equals the request `thread_summary`, and emitted `message.task_execution_id` equals request `task_execution_id`.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/unit -q -k "thread_message_created"
```

Expected: FAIL because live DTO currently omits summary and task execution identity in the emitted message.

- [ ] **Step 3: Populate live DTO fields**

In `CommunicationService.save_message`, set:

```python
thread_dto = RunCommunicationThreadDto(
    id=str(thread.id),
    run_id=str(thread.run_id),
    topic=thread.topic,
    summary=thread.summary,
    agent_a_id=thread.agent_a_id,
    agent_b_id=thread.agent_b_id,
    created_at=thread.created_at,
    updated_at=thread.updated_at,
    messages=[],
)
```

Set on `message_dto`:

```python
task_execution_id=str(message.task_execution_id) if message.task_execution_id else None,
```

If task ID derivation is available in this service path, also set `task_id`. If not, leave `task_id=None` and rely on snapshot enrichment until the service has an execution lookup helper.

- [ ] **Step 4: Run live event test**

Run:

```bash
pytest tests/unit -q -k "thread_message_created"
```

Expected: PASS.

---

## Task 5: Update Frontend Contracts

**Files:**
- Modify: `ergon-dashboard/src/generated/rest/contracts.ts`
- Modify: `ergon-dashboard/src/lib/contracts/rest.ts`
- Test: `ergon-dashboard/tests/contracts/contracts.test.ts`

- [ ] **Step 1: Write frontend contract assertion**

In `tests/contracts/contracts.test.ts`, assert a thread fixture can contain:

```ts
summary: "Leaf workers report completion artifacts and probe exit status."
```

and parsing preserves `thread.summary`.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pnpm exec vitest run tests/contracts/contracts.test.ts
```

Expected: FAIL if generated contract does not include `summary`.

- [ ] **Step 3: Update generated/rest contract**

Add `summary: z.string().nullable().optional()` to `RunCommunicationThreadDto` schema if codegen is not run in this task.

- [ ] **Step 4: Normalize summary**

Ensure `RunCommunicationThread` exposes:

```ts
summary: string | null;
```

and normalization defaults missing `summary` to `null`.

- [ ] **Step 5: Run frontend contract test**

Run:

```bash
pnpm exec vitest run tests/contracts/contracts.test.ts
```

Expected: PASS.

---

## Task 6: Restyle Communication Panel as Thread List + Chat Trace

**Files:**
- Modify: `ergon-dashboard/src/components/panels/CommunicationPanel.tsx`
- Test: `ergon-dashboard/tests/e2e/run.snapshot.spec.ts`

- [ ] **Step 1: Add E2E assertions for clickable thread list**

In `run.snapshot.spec.ts`, after opening communication tab, assert:

```ts
await expect(page.getByTestId("communication-thread-list")).toBeVisible();
await expect(page.getByTestId("communication-thread-card").first()).toContainText("smoke-completion");
await page.getByTestId("communication-thread-card").first().click();
await expect(page.getByTestId("communication-chat-trace")).toBeVisible();
await expect(page.getByTestId("communication-chat-message").first()).toBeVisible();
```

- [ ] **Step 2: Run E2E test to verify failure**

Run:

```bash
pnpm exec playwright test tests/e2e/run.snapshot.spec.ts --project=chromium -g "graph selection opens workspace evidence sections"
```

Expected: FAIL because the current panel has no thread-list/chat-trace test IDs.

- [ ] **Step 3: Implement selected thread state**

In `CommunicationPanel.tsx`, add:

```ts
const [selectedThreadId, setSelectedThreadId] = useState<string | null>(threads[0]?.id ?? null);
const selectedThread = threads.find((thread) => thread.id === selectedThreadId) ?? threads[0] ?? null;
```

Use `useEffect` to reset selection when `threads[0]?.id` changes.

- [ ] **Step 4: Render thread list**

For each thread, render a button card with:

- topic
- `thread.summary ?? summarizeThread(thread)`
- message count
- created/updated time
- participant chips derived from `messages[].fromAgentId` plus `agentAId`/`agentBId`

- [ ] **Step 5: Render WhatsApp-style chat trace**

For selected thread, render messages sorted by `sequenceNum` with:

- sender label from `fromAgentId`
- timestamp from `createdAt`
- content as wrapped text
- bubble alignment keyed by sender
- small metadata row: `#${sequenceNum}` and `taskId` when available

- [ ] **Step 6: Keep empty state clear**

If no threads are visible at time `t`, show:

```tsx
No communication threads yet at this point in the run.
```

- [ ] **Step 7: Run E2E test**

Run:

```bash
pnpm exec playwright test tests/e2e/run.snapshot.spec.ts --project=chromium -g "graph selection opens workspace evidence sections"
```

Expected: PASS.

---

## Task 7: Ensure Time-Step Filtering Reads Correctly

**Files:**
- Modify: `ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.ts` if needed
- Test: `ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.test.ts`

- [ ] **Step 1: Add test for visible-at-time thread summaries**

Create a test where:

- thread exists at 10:00
- messages exist at 10:01 and 10:02
- selected time is 10:01:30

Assert returned thread contains only the first message.

- [ ] **Step 2: Run test**

Run:

```bash
pnpm exec tsx --test src/components/workspace/filterTaskEvidenceForTime.test.ts
```

Expected: PASS if current filtering already handles this. If it fails, patch only filtering logic.

---

## Task 8: Final Verification

**Files:**
- All touched files

- [ ] **Step 1: Run backend unit tests**

Run:

```bash
pytest tests/unit/smoke_base/test_leaf_sends_completion_message.py tests/unit/dashboard/test_event_contract_types.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend typecheck**

Run from `ergon-dashboard`:

```bash
pnpm exec tsc --noEmit
```

Expected: exit 0.

- [ ] **Step 3: Run frontend E2E tests sequentially**

Run from `ergon-dashboard`:

```bash
pnpm exec playwright test tests/e2e/run.snapshot.spec.ts --project=chromium
pnpm exec playwright test tests/e2e/run.delta.spec.ts --project=chromium
```

Expected: both pass. Run sequentially to avoid shared dev-server port collisions.

- [ ] **Step 4: Lint recently edited files**

Use the IDE linter diagnostics for:

- `CommunicationPanel.tsx`
- `filterTaskEvidenceForTime.ts`
- generated/normalized contract files
- backend communication service/schema files

Expected: no new linter errors.

---

## Self-Review

- Spec coverage: covers agent-authored nullable thread summary, first-message creation path, backend summary/task anchoring, live event DTOs, frontend clickable thread list, chat trace, and time-step filtering.
- Placeholder scan: no `TBD`/`TODO` placeholders; migration revision filename remains intentionally parameterized because Alembic generates revision IDs.
- Type consistency: backend uses `thread_summary` for request input and `summary` for persisted/output thread metadata; frontend uses `summary`.
