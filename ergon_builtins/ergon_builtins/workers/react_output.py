"""Final-output extraction for ReAct workers."""

from ergon_core.api import WorkerOutput
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ToolCallPart,
)


def worker_output_from_chunks(chunks: list[ContextPartChunk]) -> WorkerOutput:
    """Build the terminal worker output from transcript chunks."""
    structured_output = _latest_final_result_message(chunks)
    if structured_output:
        return WorkerOutput(
            output=structured_output,
            success=True,
            metadata={"output_source": "final_result_tool"},
        )

    text_parts = [
        chunk.part.content for chunk in chunks if isinstance(chunk.part, AssistantTextPart)
    ]
    if text_parts:
        return WorkerOutput(
            output=text_parts[-1],
            success=True,
            metadata={"output_source": "assistant_text_fallback"},
        )

    return WorkerOutput(
        output="",
        success=False,
        metadata={"output_source": "missing"},
    )


def _latest_final_result_message(chunks: list[ContextPartChunk]) -> str:
    """Extract fallback text from the latest ``final_result`` tool call."""
    messages: list[str] = []
    for chunk in chunks:
        part = chunk.part
        if not isinstance(part, ToolCallPart) or part.tool_name != "final_result":
            continue
        messages.append(str(part.args.get("final_assistant_message", "")))
    return messages[-1] if messages else ""
