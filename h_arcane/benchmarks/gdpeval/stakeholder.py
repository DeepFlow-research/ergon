"""GDPEval stakeholder that answers questions based on ground truth rubric."""

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)

from h_arcane.benchmarks.common import format_conversation_history
from h_arcane.core.agents.base import BaseStakeholder
from h_arcane.core.communication.schemas import MessageResponse
from h_arcane.core.config.evaluation_config import evaluation_config
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
from h_arcane.settings import settings


class RubricStakeholder(BaseStakeholder):
    """Stakeholder that answers questions based on ground truth rubric."""

    ANSWER_PROMPT = """
You are a stakeholder with specific preferences for how a task should be done.

Your preferences (internal, don't reveal directly):
{rubric_summary}

Task context: {task_description}

{history_section}

A worker asks you: "{question}"

Answer helpfully and specifically based on your preferences.
Don't reveal your full rubric — just answer the specific question.
Be concise but complete.
"""

    def __init__(
        self,
        ground_truth_rubric: StagedRubric,
        task_description: str,
        model: str | None = None,
    ):
        """
        Initialize stakeholder with ground truth rubric.

        Args:
            ground_truth_rubric: The StagedRubric that defines ground truth preferences
            task_description: The task description for context
            model: LLM model to use for answering (None = use config default)
        """
        self.ground_truth_rubric = ground_truth_rubric
        self.task_description = task_description
        self._model = model or evaluation_config.llm_stakeholder.model
        self._rubric_summary = self._summarize_rubric(ground_truth_rubric)
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def model(self) -> str:
        """LLM model used by this stakeholder."""
        return self._model

    @property
    def system_prompt(self) -> str:
        """System prompt describing stakeholder behavior (for logging)."""
        return self.ANSWER_PROMPT

    async def answer(
        self,
        question: str,
        history: list[MessageResponse] | None = None,
    ) -> str:
        """
        Answer a question based on ground truth rubric.

        Args:
            question: The worker's question
            history: Previous Q&A pairs in this thread (oldest first)

        Returns:
            Answer string based on rubric preferences

        Example:
            ```python
            stakeholder = RubricStakeholder(rubric, task_description)
            answer = await stakeholder.answer("What format should the output be in?")
            # Returns: "The output should be a PDF document with..."
            ```
        """
        history_text = format_conversation_history(history)
        history_section = history_text if history_text else "This is the first question."

        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionUserMessageParam(
                role="user",
                content=self.ANSWER_PROMPT.format(
                    rubric_summary=self._rubric_summary,
                    question=question,
                    task_description=self.task_description,
                    history_section=history_section,
                ),
            )
        ]

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

    def _summarize_rubric(self, rubric: StagedRubric) -> str:
        """
        Create a summary of the rubric for the prompt.

        Args:
            rubric: The StagedRubric to summarize

        Returns:
            String summary of rubric stages and criteria
        """
        lines = [
            f"Category: {rubric.category_name}",
            f"Max total score: {rubric.max_total_score}",
            "",
            "Stages:",
        ]
        for stage in rubric.stages:
            lines.append(f"- {stage.name} ({stage.max_points} pts): {stage.description}")
            if stage.rules:
                lines.append(f"  Criteria: {', '.join(rule.name for rule in stage.rules)}")

        return "\n".join(lines)
