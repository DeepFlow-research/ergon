"""PydanticAI transcript adapter."""

import json

from ergon_core.core.generation import (
    GenerationTurn,
    ModelRequestPart as ErgonModelRequestPart,
    ModelResponsePart as ErgonModelResponsePart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    TokenLogprob,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
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
    """Track how many turns have already been emitted from a growing transcript."""

    model_config = {"validate_assignment": True}

    emitted_turn_count: int = 0


class PydanticAITranscriptAdapter(TranscriptAdapter[list[ModelMessage], list[ModelMessage]]):
    """Convert complete PydanticAI message histories into Ergon turns."""

    def build_turns(
        self,
        transcript: list[ModelMessage],
        *,
        flush_pending: bool = True,
    ) -> list[GenerationTurn]:
        """Build turns from a complete PydanticAI message list."""
        return _build_turns_from_transcript(transcript, flush_pending=flush_pending)

    def build_new_turns(
        self,
        transcript: list[ModelMessage],
        cursor: TranscriptTurnCursor,
        *,
        flush_pending: bool = False,
    ) -> list[GenerationTurn]:
        """Return turns not previously emitted for a growing transcript."""
        turns = _build_turns_from_transcript(transcript, flush_pending=flush_pending)
        new_turns = turns[cursor.emitted_turn_count :]
        cursor.emitted_turn_count = len(turns)
        return new_turns

    def assemble_replay(self, events: list[RunContextEvent]) -> list[ModelMessage]:
        """Reconstruct PydanticAI messages from ordered context events."""
        messages: list[ModelMessage] = []
        current_request_parts: list[PydanticModelRequestPart] = []
        current_response_parts: list[PydanticModelResponsePart] = []

        for event in events:
            payload = event.parsed_payload()
            if request_part := _to_pydantic_request_part(payload):
                if isinstance(payload, ToolResultPayload) and current_response_parts:
                    messages.append(ModelResponse(parts=current_response_parts))
                    current_response_parts = []
                current_request_parts.append(request_part)
            elif response_part := _to_pydantic_response_part(payload):
                if current_request_parts and not current_response_parts:
                    messages.append(ModelRequest(parts=current_request_parts))
                    current_request_parts = []
                current_response_parts.append(response_part)

        if current_response_parts:
            messages.append(ModelResponse(parts=current_response_parts))

        return messages


def _build_turns_from_transcript(
    transcript: list[ModelMessage],
    *,
    flush_pending: bool,
) -> list[GenerationTurn]:
    turns: list[GenerationTurn] = []
    pending_response: ModelResponse | None = None
    pending_request_in: ModelRequest | None = None

    for message in transcript:
        if isinstance(message, ModelRequest):
            if pending_response is not None:
                turns.append(
                    _to_turn(
                        pending_request_in,
                        pending_response,
                        tool_result_request=message,
                    )
                )
                pending_response = None
                pending_request_in = None
            pending_request_in = message
        elif isinstance(message, ModelResponse):
            pending_response = message

    if pending_response is not None and flush_pending:
        turns.append(_to_turn(pending_request_in, pending_response, tool_result_request=None))

    return turns


def _to_turn(
    request_in: ModelRequest | None,
    response: ModelResponse,
    tool_result_request: ModelRequest | None,
) -> GenerationTurn:
    return GenerationTurn(
        messages_in=_extract_request_parts(request_in) if request_in else [],
        response_parts=_extract_response_parts(response),
        tool_results=_extract_tool_results(tool_result_request) if tool_result_request else [],
        turn_logprobs=extract_logprobs(response),
    )


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


def _extract_request_parts(request: ModelRequest) -> list[ErgonModelRequestPart]:
    parts: list[ErgonModelRequestPart] = []
    for part in request.parts:
        if isinstance(part, PydanticSystemPromptPart):
            parts.append(SystemPromptPart(content=part.content))
        elif isinstance(part, PydanticUserPromptPart) and isinstance(part.content, str):
            parts.append(UserPromptPart(content=part.content))
    return parts


def _extract_response_parts(response: ModelResponse) -> list[ErgonModelResponsePart]:
    parts: list[ErgonModelResponsePart] = []
    for part in response.parts:
        if isinstance(part, PydanticTextPart):
            parts.append(TextPart(content=part.content))
        elif isinstance(part, PydanticToolCallPart):
            parts.append(
                ToolCallPart(
                    tool_name=part.tool_name,
                    tool_call_id=part.tool_call_id,
                    args=part.args_as_dict(),
                )
            )
        elif isinstance(part, PydanticThinkingPart):
            parts.append(ThinkingPart(content=part.content))
    return parts


def _extract_tool_results(request: ModelRequest) -> list[ToolReturnPart]:
    results: list[ToolReturnPart] = []
    for part in request.parts:
        if isinstance(part, PydanticToolReturnPart):
            results.append(
                ToolReturnPart(
                    tool_call_id=part.tool_call_id,
                    tool_name=part.tool_name,
                    content=_serialize_tool_content(part.content),
                )
            )
    return results


def _serialize_tool_content(content: ToolReturnContent) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(to_jsonable_python(content))


def _to_pydantic_response_part(
    payload: AssistantTextPayload
    | ThinkingPayload
    | ToolCallPayload
    | SystemPromptPayload
    | UserMessagePayload
    | ToolResultPayload,
) -> PydanticModelResponsePart | None:
    if isinstance(payload, ThinkingPayload):
        return PydanticThinkingPart(content=payload.text)
    if isinstance(payload, AssistantTextPayload):
        return PydanticTextPart(content=payload.text)
    if isinstance(payload, ToolCallPayload):
        return PydanticToolCallPart(
            tool_name=payload.tool_name,
            tool_call_id=payload.tool_call_id,
            args=payload.args,
        )
    return None


def _to_pydantic_request_part(
    payload: AssistantTextPayload
    | ThinkingPayload
    | ToolCallPayload
    | SystemPromptPayload
    | UserMessagePayload
    | ToolResultPayload,
) -> PydanticModelRequestPart | None:
    if isinstance(payload, SystemPromptPayload):
        return PydanticSystemPromptPart(content=payload.text)
    if isinstance(payload, UserMessagePayload):
        return PydanticUserPromptPart(content=payload.text)
    if isinstance(payload, ToolResultPayload):
        return PydanticToolReturnPart(
            tool_call_id=payload.tool_call_id,
            tool_name=payload.tool_name,
            content=str(payload.result),
        )
    return None
