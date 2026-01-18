"""Common benchmark components shared across benchmarks."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from h_arcane.core._internal.communication.schemas import MessageResponse


def format_conversation_history(history: list["MessageResponse"] | None) -> str:
    """Format message history as conversation text for prompt injection.

    Args:
        history: List of previous messages in the thread (oldest first)

    Returns:
        Formatted conversation text, or empty string if no history
    """
    if not history:
        return ""

    lines = ["Previous conversation:"]
    for msg in history:
        role = "Worker" if msg.from_agent_id.endswith(":worker") else "Stakeholder"
        lines.append(f"{role}: {msg.content}")

    return "\n".join(lines)
