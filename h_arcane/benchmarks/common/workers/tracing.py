"""Tracing utilities for agent execution."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from litellm.cost_calculator import cost_per_token

from agents.items import (
    MessageOutputItem,
    ReasoningItem,
    RunItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.result import RunResult
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputText

from h_arcane.core._internal.db.models import Action, ExecutionError
from h_arcane.core._internal.db.queries import queries


def _extract_error_from_output(output: Any) -> dict | None:
    """
    Extract error information from tool output if present.

    Tool outputs are typically Pydantic models or dicts with:
    - success: bool
    - error: str | None (error message)
    - exception_type: str | None (optional)
    - stack_trace: str | None (optional)

    Returns:
        ExecutionError as dict if error detected, None otherwise.
    """
    # Convert to dict if it's a Pydantic model
    if isinstance(output, BaseModel):
        output_dict = output.model_dump()
    elif isinstance(output, dict):
        output_dict = output
    else:
        return None

    # Check for failure indicators
    success = output_dict.get("success")
    error_message = output_dict.get("error")

    # If success is explicitly False or there's an error message
    if success is False or (error_message and success is not True):
        return ExecutionError(
            message=error_message or "Unknown error",
            exception_type=output_dict.get("exception_type"),
            stack_trace=output_dict.get("stack_trace"),
            details=None,
        ).model_dump()

    return None


def log_actions_from_result(
    result: RunResult,
    agent_id: UUID,
    run_id: UUID,
    model_name: str = "gpt-4o",
) -> list[UUID]:
    """
    Process RunResult.new_items and log all actions to database.

    Handles all item types:
    - MessageOutputItem: LLM text responses
    - ToolCallItem + ToolCallOutputItem: Tool calls with inputs/outputs
    - ReasoningItem: Reasoning/thinking steps
    - Other item types: Logged generically

    Args:
        result: The RunResult from Runner.run()
        agent_id: UUID of the AgentConfig that executed this run
        run_id: UUID of the Run
        model_name: Name of the model used (for cost calculation)

    Returns:
        List of created action IDs
    """
    action_ids = []
    action_num = 0

    # Step 1: Build map of call_id -> ToolCallItem for matching
    tool_calls: dict[str, ToolCallItem] = {}
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            raw = item.raw_item
            if isinstance(raw, ResponseFunctionToolCall):
                tool_calls[raw.call_id] = item

    # Step 2: Calculate costs from usage (run-level, not per-action)
    usage = result.context_wrapper.usage
    agent_total_tokens = usage.input_tokens + usage.output_tokens
    agent_total_cost_usd = _calculate_cost(usage, model_name)

    # Step 3: Process all items in order
    for item in result.new_items:
        action = _process_item(
            item, tool_calls, action_num, agent_id, run_id, agent_total_tokens, agent_total_cost_usd
        )
        if action:
            created = queries.actions.create(action)
            action_ids.append(created.id)
            action_num += 1

    return action_ids


def _process_item(
    item: RunItem,
    tool_calls: dict[str, ToolCallItem],
    action_num: int,
    agent_id: UUID,
    run_id: UUID,
    agent_total_tokens: int,
    agent_total_cost_usd: float,
) -> Action | None:
    """Process a single RunItem and return Action object, or None to skip."""

    now = datetime.now(timezone.utc)

    match item:
        case MessageOutputItem():
            return _extract_message(
                item, run_id, agent_id, action_num, now, agent_total_tokens, agent_total_cost_usd
            )
        case ToolCallOutputItem():
            return _extract_tool_call_output(
                item,
                tool_calls,
                run_id,
                agent_id,
                action_num,
                now,
                agent_total_tokens,
                agent_total_cost_usd,
            )
        case ReasoningItem():
            return _extract_reasoning(
                item, run_id, agent_id, action_num, now, agent_total_tokens, agent_total_cost_usd
            )
        case ToolCallItem():
            # Skip - we handle these when processing ToolCallOutputItem
            return None
        case _:
            return _extract_generic(
                item, run_id, agent_id, action_num, now, agent_total_tokens, agent_total_cost_usd
            )


def _extract_message(
    item: MessageOutputItem,
    run_id: UUID,
    agent_id: UUID,
    action_num: int,
    now: datetime,
    agent_total_tokens: int,
    agent_total_cost_usd: float,
) -> Action:
    """Extract action record from MessageOutputItem."""
    text = _extract_message_text(item)
    return Action(
        run_id=run_id,
        agent_id=agent_id,
        action_num=action_num,
        started_at=now,
        completed_at=now,
        agent_total_tokens=agent_total_tokens,
        agent_total_cost_usd=agent_total_cost_usd,
        action_type="message",
        input=json.dumps({"type": "message"}),
        output=text,
    )


def _extract_tool_call_output(
    item: ToolCallOutputItem,
    tool_calls: dict[str, ToolCallItem],
    run_id: UUID,
    agent_id: UUID,
    action_num: int,
    now: datetime,
    agent_total_tokens: int,
    agent_total_cost_usd: float,
) -> Action:
    """Extract action record from ToolCallOutputItem."""
    raw = item.raw_item
    call_id = raw.get("call_id") if isinstance(raw, dict) else None

    if call_id and isinstance(call_id, str) and call_id in tool_calls:
        tool_call_item = tool_calls[call_id]
        tool_raw = tool_call_item.raw_item

        if isinstance(tool_raw, ResponseFunctionToolCall):
            # Format output
            output = item.output
            if isinstance(output, str):
                output_str = output
            elif isinstance(output, BaseModel):
                # Pydantic models
                output_str = json.dumps(output.model_dump(), indent=2, default=str)
            else:
                # Other types (dicts, lists, etc.)
                output_str = json.dumps(output, indent=2, default=str)

            # Extract error if present in output
            error_dict = _extract_error_from_output(output)

            return Action(
                run_id=run_id,
                agent_id=agent_id,
                action_num=action_num,
                started_at=now,
                completed_at=now,
                agent_total_tokens=agent_total_tokens,
                agent_total_cost_usd=agent_total_cost_usd,
                action_type=tool_raw.name,
                input=tool_raw.arguments,  # Already JSON string from OpenAI
                output=output_str,
                error=error_dict,
            )

    # Orphan output - log anyway
    return Action(
        run_id=run_id,
        agent_id=agent_id,
        action_num=action_num,
        started_at=now,
        completed_at=now,
        agent_total_tokens=agent_total_tokens,
        agent_total_cost_usd=agent_total_cost_usd,
        action_type="tool_output",
        input=json.dumps({"call_id": call_id}),
        output=str(item.output),
    )


def _extract_reasoning(
    item: ReasoningItem,
    run_id: UUID,
    agent_id: UUID,
    action_num: int,
    now: datetime,
    agent_total_tokens: int,
    agent_total_cost_usd: float,
) -> Action:
    """Extract action record from ReasoningItem."""
    text = ""
    if item.raw_item.summary:
        for summary in item.raw_item.summary:
            text += summary.text + "\n"

    return Action(
        run_id=run_id,
        agent_id=agent_id,
        action_num=action_num,
        started_at=now,
        completed_at=now,
        agent_total_tokens=agent_total_tokens,
        agent_total_cost_usd=agent_total_cost_usd,
        action_type="reasoning",
        input=json.dumps({"type": "reasoning"}),
        output=text.strip(),
    )


def _extract_generic(
    item: RunItem,
    run_id: UUID,
    agent_id: UUID,
    action_num: int,
    now: datetime,
    agent_total_tokens: int,
    agent_total_cost_usd: float,
) -> Action:
    """Extract action record from generic/unknown item types."""
    return Action(
        run_id=run_id,
        agent_id=agent_id,
        action_num=action_num,
        started_at=now,
        completed_at=now,
        agent_total_tokens=agent_total_tokens,
        agent_total_cost_usd=agent_total_cost_usd,
        action_type=item.type,
        input=json.dumps({"type": item.type}),
        output=str(item.raw_item),
    )


def _extract_message_text(item: MessageOutputItem) -> str:
    """Extract text content from MessageOutputItem."""
    text_parts = []
    for content in item.raw_item.content:
        if isinstance(content, ResponseOutputText):
            text_parts.append(content.text)
    return "\n".join(text_parts)


def _calculate_cost(usage: Usage, model_name: str) -> float:
    """Calculate cost from usage."""

    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    cache_read = usage.input_tokens_details.cached_tokens
    cache_creation = usage.input_tokens - cache_read

    prompt_cost, completion_cost = cost_per_token(
        model=model_name,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation - cache_read,
    )
    return prompt_cost + completion_cost
