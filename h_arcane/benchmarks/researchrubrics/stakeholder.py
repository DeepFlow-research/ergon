"""ResearchRubrics stakeholder that answers based on rubric criteria."""

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from h_arcane.core.agents.base import BaseStakeholder
from h_arcane.core.communication.schemas import MessageResponse
from h_arcane.core.config.evaluation_config import evaluation_config
from h_arcane.core.db.models import Experiment
from h_arcane.settings import settings


class RubricAwareStakeholder(BaseStakeholder):
    """Stakeholder that knows rubric criteria + ablated prompt.

    This stakeholder simulates a research client who has specific preferences
    encoded in the rubric criteria. When asked questions, it answers based on
    what the criteria expect without revealing the full rubric.

    Behavior:
    - Answers based on what rubric criteria expect
    - Doesn't reveal full rubric, just answers questions naturally
    - Responds "I don't have a preference" for out-of-scope questions
    """

    SYSTEM_PROMPT_TEMPLATE = """You are a stakeholder who commissioned a research report.

You know exactly what you want based on these evaluation criteria:
{criteria}

When the researcher asks questions:
- Answer based on what the criteria expect
- Be helpful but don't reveal the full rubric or that you have specific evaluation criteria
- Say "I don't have a strong preference on that" for questions unrelated to the criteria
- Be natural and conversational, as if you're a real client

Research request: {task_prompt}
"""

    def __init__(
        self,
        experiment: Experiment,
        model: str | None = None,
    ):
        """
        Initialize stakeholder with experiment data.

        Args:
            experiment: The Experiment containing task_description (ablated prompt)
                       and ground_truth_rubric (criteria)
            model: LLM model to use for answering (None = use config default)
        """
        self._model = model or evaluation_config.llm_stakeholder.model
        self._task_prompt = experiment.task_description  # ablated prompt
        self._rubric_criteria = experiment.ground_truth_rubric.get("criteria", [])
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def model(self) -> str:
        """LLM model used by this stakeholder."""
        return self._model

    @property
    def system_prompt(self) -> str:
        """System prompt describing stakeholder behavior (for logging)."""
        return self.SYSTEM_PROMPT_TEMPLATE.format(
            criteria=self._format_criteria(),
            task_prompt=self._task_prompt,
        )

    def _format_criteria(self) -> str:
        """Format criteria for the system prompt.

        Groups criteria by axis for better organization.

        Returns:
            Formatted string with all criteria
        """
        if not self._rubric_criteria:
            return "No specific criteria provided."

        # Group by axis
        by_axis: dict[str, list[dict]] = {}
        for criterion in self._rubric_criteria:
            axis = criterion.get("axis", "Other")
            if axis not in by_axis:
                by_axis[axis] = []
            by_axis[axis].append(criterion)

        lines = []
        for axis, criteria in sorted(by_axis.items()):
            lines.append(f"\n{axis}:")
            for c in criteria:
                weight = c.get("weight", 1.0)
                criterion_text = c.get("criterion", "")
                weight_indicator = f"(weight: {weight})" if weight != 1.0 else ""
                lines.append(f"  - {criterion_text} {weight_indicator}".strip())

        return "\n".join(lines)

    async def answer(
        self,
        question: str,
        history: list[MessageResponse] | None = None,
    ) -> str:
        """
        Answer a question based on rubric criteria.

        Args:
            question: The worker's question about the research task
            history: Previous Q&A pairs in this thread (oldest first)

        Returns:
            Answer string based on rubric preferences

        Example:
            ```python
            stakeholder = RubricAwareStakeholder(experiment)
            answer = await stakeholder.answer("What format should the report be in?")
            # Returns: "I'd prefer a well-structured document with clear sections..."
            ```
        """
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=self.system_prompt,
            ),
        ]

        # Add history as actual chat turns
        if history:
            for msg in history:
                if msg.from_agent_id.endswith(":worker"):
                    messages.append(
                        ChatCompletionUserMessageParam(role="user", content=msg.content)
                    )
                else:
                    messages.append(
                        ChatCompletionAssistantMessageParam(role="assistant", content=msg.content)
                    )

        # Add current question
        messages.append(ChatCompletionUserMessageParam(role="user", content=question))

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=evaluation_config.llm_stakeholder.max_tokens,
            temperature=evaluation_config.llm_stakeholder.temperature,
        )

        content = response.choices[0].message.content
        if content is None:
            return "I'm unable to provide an answer at this time."
        return content
