from collections.abc import AsyncGenerator

import pytest
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.application.jobs.worker_execute import _consume_worker_stream


async def _stream_with_terminal_output() -> AsyncGenerator[ContextPartChunk | WorkerOutput, None]:
    yield ContextPartChunk(part=AssistantTextPart(content="transcript"))
    yield WorkerOutput(output="final result", success=True)


async def _stream_without_terminal_output() -> AsyncGenerator[
    ContextPartChunk | WorkerOutput, None
]:
    yield ContextPartChunk(part=AssistantTextPart(content="transcript"))


async def _stream_after_terminal_output() -> AsyncGenerator[ContextPartChunk | WorkerOutput, None]:
    yield WorkerOutput(output="final result", success=True)
    yield ContextPartChunk(part=AssistantTextPart(content="late transcript"))


async def _stream_with_multiple_outputs() -> AsyncGenerator[ContextPartChunk | WorkerOutput, None]:
    yield WorkerOutput(output="first", success=True)
    yield WorkerOutput(output="second", success=True)


async def _stream_with_invalid_item() -> AsyncGenerator[object, None]:
    yield object()
    yield WorkerOutput(output="final result", success=True)


@pytest.mark.asyncio
async def test_consume_worker_stream_persists_chunks_and_returns_terminal_output() -> None:
    persisted: list[tuple[int, ContextPartChunk]] = []

    async def persist(chunk: ContextPartChunk, chunk_count: int) -> None:
        persisted.append((chunk_count, chunk))

    output, chunk_count = await _consume_worker_stream(_stream_with_terminal_output(), persist)

    assert output == WorkerOutput(output="final result", success=True)
    assert chunk_count == 1
    assert persisted == [
        (0, ContextPartChunk(part=AssistantTextPart(content="transcript"))),
    ]


@pytest.mark.asyncio
async def test_consume_worker_stream_requires_terminal_output() -> None:
    async def persist(chunk: ContextPartChunk, chunk_count: int) -> None:
        pass

    with pytest.raises(ContractViolationError, match="terminal WorkerOutput"):
        await _consume_worker_stream(_stream_without_terminal_output(), persist)


@pytest.mark.asyncio
async def test_consume_worker_stream_rejects_chunks_after_terminal_output() -> None:
    async def persist(chunk: ContextPartChunk, chunk_count: int) -> None:
        pass

    with pytest.raises(ContractViolationError, match="after terminal WorkerOutput"):
        await _consume_worker_stream(_stream_after_terminal_output(), persist)


@pytest.mark.asyncio
async def test_consume_worker_stream_rejects_multiple_terminal_outputs() -> None:
    async def persist(chunk: ContextPartChunk, chunk_count: int) -> None:
        pass

    with pytest.raises(ContractViolationError, match="multiple terminal WorkerOutput"):
        await _consume_worker_stream(_stream_with_multiple_outputs(), persist)


@pytest.mark.asyncio
async def test_consume_worker_stream_rejects_non_context_items() -> None:
    async def persist(chunk: ContextPartChunk, chunk_count: int) -> None:
        pass

    with pytest.raises(ContractViolationError, match="expected ContextPartChunk"):
        await _consume_worker_stream(_stream_with_invalid_item(), persist)
