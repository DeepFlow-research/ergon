"""Mock stakeholder for smoke testing that returns canned responses."""

from h_arcane.core._internal.agents.base import BaseStakeholder
from h_arcane.core._internal.communication.schemas import MessageResponse


class MockStakeholder(BaseStakeholder):
    """Mock stakeholder that returns canned responses for smoke testing.

    This stakeholder cycles through a list of predefined responses,
    enabling consistent and predictable behavior during pipeline validation.
    """

    CANNED_RESPONSES = [
        "Yes, please proceed with that approach. It looks good for the smoke test.",
        "The output should be in a simple text format for validation purposes.",
        "No special requirements - focus on completing the workflow correctly.",
        "That's correct. The smoke test just needs to verify the pipeline works.",
        "Please continue and complete the task as you see fit.",
    ]

    def __init__(self) -> None:
        """Initialize mock stakeholder with canned responses."""
        self._responses = self.CANNED_RESPONSES.copy()
        self._call_count = 0

    @property
    def model(self) -> str:
        """LLM model used by this stakeholder (mock - no actual LLM)."""
        return "mock"

    @property
    def system_prompt(self) -> str:
        """System prompt describing stakeholder behavior."""
        return "Mock stakeholder for smoke testing. Returns canned responses."

    async def answer(
        self,
        question: str,
        history: list[MessageResponse] | None = None,
    ) -> str:
        """
        Return a canned response, cycling through available responses.

        Args:
            question: The worker's question (acknowledged but response is predetermined)
            history: Previous Q&A pairs (ignored for mock stakeholder)

        Returns:
            A canned response string
        """
        response = self._responses[self._call_count % len(self._responses)]
        self._call_count += 1
        return response

    def reset(self) -> None:
        """Reset call count to restart response cycling."""
        self._call_count = 0
