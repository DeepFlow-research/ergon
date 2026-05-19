"""PydanticAI transcript adapter."""

import json

from ergon_core.core.domain.generation.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    TokenLogprob,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolReturnContent
from pydantic_ai.messages import ModelRequestPart as PydanticModelRequestPart
from pydantic_ai.messages import ModelResponsePart as PydanticModelResponsePart
from pydantic_ai.messages import SystemPromptPart as PydanticSystemPromptPart
from pydantic_ai.messages import TextPart as PydanticTextPart
from pydantic_ai.messages import ThinkingPart as PydanticThinkingPart
from pydantic_ai.messages import ToolCallPart as PydanticToolCallPart
from pydantic_ai.messages import ToolReturnPart as PydanticToolReturnPart
from pydantic_ai.messages import UserPromptPart as PydanticUserPromptPart
from pydantic_core import to_jsonable_python

from ergon_builtins.common.llm_context.adapters.base import TranscriptAdapter


class TranscriptTurnCursor(BaseModel):
    """Track how many chunks have already been emitted from a growing transcript."""

    model_config = {"validate_assignment": True}

    emitted_chunk_count: int = 0


class PydanticAITranscriptAdapter(TranscriptAdapter[list[ModelMessage], list[ModelMessage]]):
    """Convert PydanticAI message histories into Ergon context stream chunks."""

    def build_chunks(
        self,
        transcript: list[ModelMessage],
        *,
        flush_pending: bool = True,
    ) -> list[ContextPartChunk]:
        """Build context stream chunks from a complete PydanticAI message list."""
        return _build_chunks_from_transcript(transcript, flush_pending=flush_pending)

    def build_new_chunks(
        self,
        transcript: list[ModelMessage],
        cursor: TranscriptTurnCursor,
        *,
        flush_pending: bool = False,
    ) -> list[ContextPartChunk]:
        """Return chunks not previously emitted for a growing transcript."""
        chunks = _build_chunks_from_transcript(transcript, flush_pending=flush_pending)
        new_chunks = chunks[cursor.emitted_chunk_count :]
        cursor.emitted_chunk_count = len(chunks)
        return new_chunks


def _build_chunks_from_transcript(
    transcript: list[ModelMessage],
    *,
    flush_pending: bool,
) -> list[ContextPartChunk]:
    chunks: list[ContextPartChunk] = []
    pending_response: ModelResponse | None = None

    for message in transcript:
        if isinstance(message, ModelRequest):
            if pending_response is not None:
                chunks.extend(_chunks_from_response(pending_response))
                pending_response = None
            chunks.extend(_chunks_from_request(message))
        elif isinstance(message, ModelResponse):
            pending_response = message

    if pending_response is not None and flush_pending:
        chunks.extend(_chunks_from_response(pending_response))

    return chunks


def extract_logprobs(response: ModelResponse) -> list[TokenLogprob] | None:
    """Extract per-token logprobs from PydanticAI provider metadata."""
    details = response.provider_details
    if details is None:
        return None
    raw_logprobs = details.get("logprobs")
    if not isinstance(raw_logprobs, list) or not raw_logprobs:
        return None
    logprobs: list[TokenLogprob] = []
    for entry in raw_logprobs:
        if not isinstance(entry, dict):
            continue
        token = entry.get("token")
        logprob = entry.get("logprob")
        top_logprobs = entry.get("top_logprobs", [])
        if (
            isinstance(token, str)
            and isinstance(logprob, int | float)
            and isinstance(top_logprobs, list)
        ):
            logprobs.append(
                TokenLogprob(
                    token=token,
                    logprob=float(logprob),
                    top_logprobs=[item for item in top_logprobs if isinstance(item, dict)],
                )
            )
    return logprobs or None


def _serialize_tool_content(content: ToolReturnContent) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(to_jsonable_python(content))


def _chunks_from_request(request: ModelRequest) -> list[ContextPartChunk]:
    chunks: list[ContextPartChunk] = []
    for part in request.parts:
        if isinstance(part, PydanticSystemPromptPart):
            chunks.append(ContextPartChunk(part=SystemPromptPart(content=part.content)))
        elif isinstance(part, PydanticUserPromptPart) and isinstance(part.content, str):
            chunks.append(ContextPartChunk(part=UserMessagePart(content=part.content)))
        elif isinstance(part, PydanticToolReturnPart):
            chunks.append(
                ContextPartChunk(
                    part=ToolResultPart(
                        tool_call_id=part.tool_call_id,
                        tool_name=part.tool_name,
                        content=_serialize_tool_content(part.content),
                    )
                )
            )
    return chunks


def _chunks_from_response(response: ModelResponse) -> list[ContextPartChunk]:
    logprobs = extract_logprobs(response)
    chunks: list[ContextPartChunk] = []
    for part in response.parts:
        if isinstance(part, PydanticTextPart):
            chunks.append(
                ContextPartChunk(part=AssistantTextPart(content=part.content), logprobs=logprobs)
            )
            logprobs = None
        elif isinstance(part, PydanticToolCallPart):
            chunks.append(
                ContextPartChunk(
                    part=ToolCallPart(
                        tool_name=part.tool_name,
                        tool_call_id=part.tool_call_id,
                        args=part.args_as_dict(),
                    ),
                    logprobs=logprobs,
                )
            )
            logprobs = None
        elif isinstance(part, PydanticThinkingPart):
            chunks.append(
                ContextPartChunk(part=ThinkingPart(content=part.content), logprobs=logprobs)
            )
            logprobs = None
    return chunks


def _to_pydantic_response_part(
    payload: ContextPartChunkLog,
) -> PydanticModelResponsePart | None:
    part = payload.part
    if isinstance(part, ThinkingPart):
        return PydanticThinkingPart(content=part.content)
    if isinstance(part, AssistantTextPart):
        return PydanticTextPart(content=part.content)
    if isinstance(part, ToolCallPart):
        return PydanticToolCallPart(
            tool_name=part.tool_name,
            tool_call_id=part.tool_call_id,
            args=part.args,
        )
    return None


def _to_pydantic_request_part(
    payload: ContextPartChunkLog,
) -> PydanticModelRequestPart | None:
    part = payload.part
    if isinstance(part, SystemPromptPart):
        return PydanticSystemPromptPart(content=part.content)
    if isinstance(part, UserMessagePart):
        return PydanticUserPromptPart(content=part.content)
    if isinstance(part, ToolResultPart):
        return PydanticToolReturnPart(
            tool_call_id=part.tool_call_id,
            tool_name=part.tool_name,
            content=part.content,
        )
    return None
