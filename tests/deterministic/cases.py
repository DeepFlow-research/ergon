"""Canonical deterministic benchmark cases for the first PG-state suite."""

from __future__ import annotations

from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion
from h_arcane.core.task import Resource
from tests.deterministic.schemas import (
    DeterministicCase,
    ScriptedJudgeResponse,
    ScriptedToolCall,
    SkillResponseSequence,
)


def minif2f_two_pass_proof_case() -> DeterministicCase:
    """Happy-path MiniF2F deterministic golden case."""
    theorem_statement = "Theorem: forall n : nat, n + 0 = n"
    return DeterministicCase(
        name="minif2f_two_pass_proof_case",
        benchmark_name="minif2f",
        task_name="minif2f_two_pass_proof_case",
        task_description=theorem_statement,
        resources=[
            Resource(
                name="problem.txt",
                content=(
                    f"{theorem_statement}\n"
                    "Write the final proof to /workspace/final_output/final_solution.lean"
                ),
            )
        ],
        evaluator=MiniF2FRubric(max_score=1.0, partial_credit_for_syntax=0.2),
        stakeholder_answers=[
            "Yes. Prefer a short direct proof if a standard lemma closes the theorem cleanly."
        ],
        scripted_steps=[
            ScriptedToolCall(
                tool_name="ask_stakeholder",
                arguments={"question": "Should I prefer a short direct proof if one exists?"},
            ),
            ScriptedToolCall(
                tool_name="write_lean_file",
                arguments={
                    "file_path": "/workspace/scratchpad/solution.lean",
                    "content": (
                        "import data.nat.basic\n\n"
                        "theorem add_zero_test (n : nat) : n + 0 = n := by\n"
                        "  sorry\n"
                    ),
                },
            ),
            ScriptedToolCall(
                tool_name="check_lean_file",
                arguments={"file_path": "/workspace/scratchpad/solution.lean"},
            ),
            ScriptedToolCall(
                tool_name="search_lemmas",
                arguments={"query": "#check nat.add_zero"},
            ),
            ScriptedToolCall(
                tool_name="write_lean_file",
                arguments={
                    "file_path": "/workspace/final_output/final_solution.lean",
                    "content": (
                        "import data.nat.basic\n\n"
                        "theorem add_zero_test (n : nat) : n + 0 = n := by\n"
                        "  exact nat.add_zero n\n"
                    ),
                },
            ),
            ScriptedToolCall(
                tool_name="verify_lean_proof",
                arguments={"file_path": "/workspace/final_output/final_solution.lean"},
            ),
        ],
        final_output_text="Proof verified and final solution written.",
        expected_action_names=[
            "ask_stakeholder",
            "write_lean_file",
            "check_lean_file",
            "search_lemmas",
            "write_lean_file",
            "verify_lean_proof",
        ],
        expected_output_names=["final_solution.lean"],
        expected_questions_asked=1,
        expected_total_cost_usd=0.0,
    )


def researchrubrics_search_synthesize_report_case() -> DeterministicCase:
    """Happy-path ResearchRubrics deterministic golden case."""
    return DeterministicCase(
        name="researchrubrics_search_synthesize_report_case",
        benchmark_name="researchrubrics",
        task_name="researchrubrics_search_synthesize_report_case",
        task_description=(
            "Research AI chip supply chain concentration risks and produce a concise markdown report."
        ),
        resources=[],
        evaluator=ResearchRubricsRubric(
            rubric_criteria=[
                RubricCriterion(
                    axis="Explicit Criteria",
                    criterion="The report prioritizes supply chain risks over generic market commentary.",
                    weight=3.0,
                ),
                RubricCriterion(
                    axis="Communication Quality",
                    criterion="The report cites at least two concrete sources and ends with a concise recommendation.",
                    weight=2.0,
                ),
            ]
        ),
        stakeholder_answers=[
            "Prioritize risks first, then mention opportunities briefly at the end."
        ],
        scripted_steps=[
            ScriptedToolCall(
                tool_name="ask_stakeholder_tool",
                arguments={"question": "Should I prioritize risks or opportunities in the report?"},
            ),
            ScriptedToolCall(
                tool_name="exa_search_tool",
                arguments={
                    "query": "AI chip supply chain concentration risks",
                    "num_results": 3,
                    "category": None,
                },
            ),
            ScriptedToolCall(
                tool_name="exa_qa_tool",
                arguments={
                    "question": "What are the main risks of AI chip supply chain concentration?",
                    "num_results": 3,
                },
            ),
            ScriptedToolCall(
                tool_name="exa_get_content_tool",
                arguments={"url": "https://example.com/source-1"},
            ),
            ScriptedToolCall(
                tool_name="exa_get_content_tool",
                arguments={"url": "https://example.com/source-2"},
            ),
            ScriptedToolCall(
                tool_name="write_report_draft_tool",
                arguments={
                    "content": (
                        "# AI Chip Supply Chain\n\n"
                        "Initial draft: concentration risk is rising because advanced packaging and leading-edge fabrication remain concentrated.\n"
                        "- Source 1: example.com/source-1\n"
                        "- Source 2: example.com/source-2\n"
                    ),
                    "file_path": "/workspace/final_output/report.md",
                },
            ),
            ScriptedToolCall(
                tool_name="edit_report_draft_tool",
                arguments={
                    "old_string": "Initial draft:",
                    "new_string": "Revised synthesis:",
                    "file_path": "/workspace/final_output/report.md",
                },
            ),
            ScriptedToolCall(
                tool_name="read_report_draft_tool",
                arguments={"file_path": "/workspace/final_output/report.md"},
            ),
        ],
        scripted_skill_responses=[
            SkillResponseSequence(
                skill_name="exa_search",
                responses=[
                    {
                        "success": True,
                        "error": None,
                        "query": "AI chip supply chain concentration risks",
                        "results": [
                            {
                                "title": "Source 1",
                                "url": "https://example.com/source-1",
                                "summary": "Packaging concentration risk summary",
                                "content": "Advanced packaging remains concentrated among a few suppliers.",
                            },
                            {
                                "title": "Source 2",
                                "url": "https://example.com/source-2",
                                "summary": "Fab concentration risk summary",
                                "content": "Leading-edge fabrication remains geographically concentrated.",
                            },
                        ],
                    }
                ],
            ),
            SkillResponseSequence(
                skill_name="exa_qa",
                responses=[
                    {
                        "success": True,
                        "error": None,
                        "question": "What are the main risks of AI chip supply chain concentration?",
                        "answer": "The main risks are fabrication bottlenecks, advanced packaging concentration, and geopolitical shocks.",
                        "sources": [
                            {"url": "https://example.com/source-1", "title": "Source 1"},
                            {"url": "https://example.com/source-2", "title": "Source 2"},
                        ],
                    }
                ],
            ),
            SkillResponseSequence(
                skill_name="exa_get_content",
                responses=[
                    {
                        "success": True,
                        "error": None,
                        "url": "https://example.com/source-1",
                        "title": "Source 1",
                        "content": "Source 1 explains packaging concentration and supplier dependency.",
                    },
                    {
                        "success": True,
                        "error": None,
                        "url": "https://example.com/source-2",
                        "title": "Source 2",
                        "content": "Source 2 explains leading-edge fab concentration and geographic exposure.",
                    },
                ],
            ),
        ],
        scripted_judge_responses=[
            ScriptedJudgeResponse(
                reasoning="The report foregrounds concentration risk in fabrication and packaging.",
                final_verdict=True,
            ),
            ScriptedJudgeResponse(
                reasoning="The report cites both scripted sources and ends with a concise recommendation.",
                final_verdict=True,
            ),
        ],
        final_output_text="Report drafted, revised, and confirmed in final_output/report.md.",
        expected_action_names=[
            "ask_stakeholder_tool",
            "exa_search_tool",
            "exa_qa_tool",
            "exa_get_content_tool",
            "exa_get_content_tool",
            "write_report_draft_tool",
            "edit_report_draft_tool",
            "read_report_draft_tool",
        ],
        expected_output_names=["report.md"],
        expected_questions_asked=1,
        expected_total_cost_usd=0.0,
    )
