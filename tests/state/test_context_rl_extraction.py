# tests/state/test_context_rl_extraction.py
"""RL trajectory extraction from RunContextEvent rows."""

import asyncio
from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.api.generation import (
    GenerationTurn,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.rl.extraction import AgentTrajectory, extract_agent_trajectories


class _FakeTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        return list(range(len(text)))  # 1 "token" per char


def _seed_events(session: Session, turns: list[GenerationTurn], worker_key: str = "agent"):
    repo = ContextEventRepository()
    run_id = uuid4()
    exec_id = uuid4()
    for turn in turns:
        asyncio.run(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key=worker_key,
                turn=turn,
            )
        )
    events = repo.get_for_run(session, run_id)
    return events, run_id, exec_id


class TestExtractAgentTrajectories:
    def test_text_only_turn(self, session: Session):
        turns = [
            GenerationTurn(
                messages_in=[
                    SystemPromptPart(content="sys"),
                    UserPromptPart(content="task"),
                ],
                response_parts=[TextPart(content="done")],
                tool_results=[],
            )
        ]
        events, run_id, exec_id = _seed_events(session, turns)

        trajectories = extract_agent_trajectories(
            events, eval_scores={str(exec_id): 1.0}, tokenizer=_FakeTokenizer()
        )
        assert len(trajectories) == 1
        t = trajectories[0]
        assert t.agent_id == "agent"
        assert len(t.completion_ids) == len("done")
        assert all(m == 1 for m in t.env_mask)

    def test_tool_result_has_env_mask_zero(self, session: Session):
        # Turn 1: tool call
        # Turn 2: tool result in messages_in (how the framework builds follow-up turns)
        turns = [
            GenerationTurn(
                messages_in=[UserPromptPart(content="search")],
                response_parts=[
                    ToolCallPart(tool_name="search", tool_call_id="c1", args={"q": "x"})
                ],
                tool_results=[],
            ),
            GenerationTurn(
                messages_in=[
                    UserPromptPart(content="search"),
                    ToolReturnPart(tool_call_id="c1", tool_name="search", content="result"),
                ],
                response_parts=[TextPart(content="ok")],
                tool_results=[],
            ),
        ]
        events, run_id, exec_id = _seed_events(session, turns)

        trajectories = extract_agent_trajectories(
            events, eval_scores={str(exec_id): 1.0}, tokenizer=_FakeTokenizer()
        )
        t = trajectories[0]
        assert 0 in t.env_mask
        assert 1 in t.env_mask

    def test_prompt_reconstructed_from_events(self, session: Session):
        turns = [
            GenerationTurn(
                messages_in=[
                    SystemPromptPart(content="You are helpful."),
                    UserPromptPart(content="Solve it."),
                ],
                response_parts=[TextPart(content="ok")],
                tool_results=[],
            )
        ]
        events, run_id, exec_id = _seed_events(session, turns)

        trajectories = extract_agent_trajectories(
            events, eval_scores={str(exec_id): 0.5}, tokenizer=_FakeTokenizer()
        )
        t = trajectories[0]
        assert len(t.prompt_ids) > 0

    def test_reward_assigned(self, session: Session):
        turns = [
            GenerationTurn(
                messages_in=[UserPromptPart(content="task")],
                response_parts=[TextPart(content="answer")],
                tool_results=[],
            )
        ]
        events, run_id, exec_id = _seed_events(session, turns)

        trajectories = extract_agent_trajectories(
            events, eval_scores={str(exec_id): 0.75}, tokenizer=_FakeTokenizer()
        )
        assert trajectories[0].reward == pytest.approx(0.75)
