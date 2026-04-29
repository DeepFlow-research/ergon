"""Contract tests for the post-RFC `ReActWorker.__init__` signature."""

import inspect
from uuid import UUID

import ergon_builtins.workers.baselines.react_worker as react_worker_module
import pytest
from ergon_builtins.workers.baselines.react_worker import ReActWorker, _worker_output_from_chunks
from ergon_core.api.benchmark import EmptyTaskPayload, Task
from ergon_core.api.worker import WorkerContext, WorkerOutput
from ergon_core.core.domain.generation.context_parts import AssistantTextPart, ContextPartChunk, ToolCallPart
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart


def test_no_adapter_kwarg() -> None:
    sig = inspect.signature(ReActWorker.__init__)
    assert "adapter" not in sig.parameters, (
        "BenchmarkAdapter ABC is being deleted — ReActWorker must not accept an adapter kwarg."
    )


@pytest.mark.parametrize(
    "kwarg",
    ["name", "model", "task_id", "sandbox_id", "tools", "system_prompt", "max_iterations"],
)
def test_all_kwargs_required_and_keyword_only(kwarg: str) -> None:
    sig = inspect.signature(ReActWorker.__init__)
    param = sig.parameters[kwarg]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"`{kwarg}` must be keyword-only; got {param.kind}"
    )
    assert param.default is inspect.Parameter.empty, (
        f"`{kwarg}` must have no default (RFC 2026-04-22 forbids nullable-with-default); "
        f"got {param.default!r}"
    )


def test_construct_with_minimal_explicit_kwargs() -> None:
    """A ReActWorker can be built with explicit [] tools and None prompt."""
    # reason: RFC 2026-04-22 §1 — base ``Worker.__init__`` now requires
    # ``task_id`` and ``sandbox_id``; the registry factory supplies real
    # values at execute time, test fixture supplies placeholders that are
    # never dereferenced (execute() isn't called).
    worker = ReActWorker(
        name="unit",
        model=None,
        task_id=UUID(int=1),
        sandbox_id="test-sandbox",
        tools=[],
        system_prompt=None,
        max_iterations=1,
    )
    assert worker.name == "unit"
    assert worker.model is None
    assert worker.tools == []
    assert worker.system_prompt is None
    assert worker.max_iterations == 1


def test_pydantic_ai_transcript_adapter_lives_outside_worker() -> None:
    module_symbols = vars(react_worker_module)
    assert "_build_turns" not in module_symbols
    assert "_extract_request_parts" not in module_symbols
    assert "_extract_response_parts" not in module_symbols
    assert "_extract_tool_results" not in module_symbols


def test_worker_output_prefers_structured_final_result_over_prior_assistant_text() -> None:
    output = _worker_output_from_chunks(
        [
            ContextPartChunk(part=AssistantTextPart(content="intermediate answer")),
            ContextPartChunk(
                part=ToolCallPart(
                    tool_name="final_result",
                    tool_call_id="final-1",
                    args={"final_assistant_message": "structured final answer"},
                )
            ),
        ]
    )

    assert output == WorkerOutput(output="structured final answer", success=True)


class _FakeRunState:
    def __init__(self) -> None:
        self.message_history = [
            ModelRequest(parts=[UserPromptPart(content="question")]),
            ModelResponse(parts=[TextPart(content="partial answer")]),
        ]


class _FakeRunContext:
    def __init__(self) -> None:
        self.state = _FakeRunState()


class _FailingAgentRun:
    def __init__(self) -> None:
        self.ctx = _FakeRunContext()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise RuntimeError("tool validation failed")


class _FailingAgentIter:
    async def __aenter__(self):
        return _FailingAgentRun()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailingAgent:
    def __init__(self, **kwargs) -> None:
        pass

    def iter(self, *args, **kwargs):
        return _FailingAgentIter()


class _DepsAgentRun:
    def __init__(self) -> None:
        self.ctx = _FakeRunContext()
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return object()


class _DepsAgentIter:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return _DepsAgentRun()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DepsAgent:
    init_kwargs = None
    iter_kwargs = None

    def __init__(self, **kwargs) -> None:
        type(self).init_kwargs = kwargs

    def iter(self, *args, **kwargs):
        type(self).iter_kwargs = kwargs
        return _DepsAgentIter(**kwargs)


class _DepsWorker(ReActWorker):
    def build_agent_deps(self, context: WorkerContext):
        return {"execution_id": str(context.execution_id)}


def _minimal_task() -> Task:
    return Task(
        task_slug="unit-task",
        instance_key="unit-instance",
        description="Unit task",
        task_payload=EmptyTaskPayload(),
    )


def _minimal_context() -> WorkerContext:
    return WorkerContext(
        run_id=UUID(int=3),
        definition_id=UUID(int=4),
        task_id=UUID(int=2),
        execution_id=UUID(int=5),
        sandbox_id="test-sandbox",
        node_id=UUID(int=6),
    )


@pytest.mark.asyncio
async def test_react_worker_yields_partial_chunk_before_reraising_agent_iter_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(react_worker_module, "Agent", _FailingAgent)
    monkeypatch.setattr(
        react_worker_module,
        "resolve_model_target",
        lambda model: type(
            "Resolved",
            (),
            {"model": "stub:constant", "capture_model_settings": None},
        )(),
    )

    worker = ReActWorker(
        name="unit",
        model=None,
        task_id=UUID(int=1),
        sandbox_id="test-sandbox",
        tools=[],
        system_prompt=None,
        max_iterations=10,
    )

    chunks = []
    with pytest.raises(RuntimeError, match="tool validation failed"):
        async for chunk in worker.execute(_minimal_task(), context=_minimal_context()):
            chunks.append(chunk)

    assert [chunk.part.part_kind for chunk in chunks] == ["user_message", "assistant_text"]
    assert chunks[-1].part.content == "partial answer"


@pytest.mark.asyncio
async def test_react_worker_passes_agent_deps_to_pydantic_ai(monkeypatch) -> None:
    _DepsAgent.init_kwargs = None
    _DepsAgent.iter_kwargs = None
    monkeypatch.setattr(react_worker_module, "Agent", _DepsAgent)
    monkeypatch.setattr(
        react_worker_module,
        "resolve_model_target",
        lambda model: type(
            "Resolved",
            (),
            {"model": "stub:constant", "capture_model_settings": None},
        )(),
    )

    worker = _DepsWorker(
        name="unit",
        model=None,
        task_id=UUID(int=1),
        sandbox_id="test-sandbox",
        tools=[],
        system_prompt=None,
        max_iterations=10,
    )

    items = [item async for item in worker.execute(_minimal_task(), context=_minimal_context())]

    chunks = items[:-1]
    assert [chunk.part.part_kind for chunk in chunks] == ["user_message", "assistant_text"]
    assert items[-1] == WorkerOutput(output="partial answer", success=True)
    assert _DepsAgent.init_kwargs["deps_type"] is dict
    assert _DepsAgent.iter_kwargs["deps"] == {"execution_id": str(UUID(int=5))}
