"""Criteria evaluator for single criterion evaluation."""

import base64
import json
import re

from e2b_code_interpreter.models import Logs
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from uuid import UUID

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.db.models import CriterionResult, Resource
from h_arcane.schemas.staged_rubric_schema import (
    CodeRule,
    EvaluationStage,
    LLMJudgeRule,
)
from h_arcane.settings import settings


def _build_code_rule_evaluation_code(
    rule: CodeRule,
    task_input: str,
    agent_reasoning: str,
    agent_outputs: list[Resource],
    max_score: float,
) -> str:
    """Build Python code string for evaluating a code rule in sandbox."""
    evaluated_resource_ids = [str(r.id) for r in agent_outputs]

    # Build file loading code
    file_loading_code = "\n".join(
        f'with open("/evaluation/{resource.name}", "rb") as f:\n'
        f'    output_files["/evaluation/{resource.name}"] = f.read()'
        for resource in agent_outputs
    )

    code = f"""import json
import re
import pandas as pd
import numpy as np
import pdfplumber
from docx import Document
from io import BytesIO

{rule.code}

# Prepare output_files dict
output_files = {{}}
{file_loading_code}

# Execute evaluation
try:
    result = evaluate(
        task_input={json.dumps(task_input)},
        agent_reasoning={json.dumps(agent_reasoning)},
        output_files=output_files
    )
    
    if isinstance(result, tuple):
        score, feedback = result
    else:
        score = float(result)
        feedback = f"Code rule '{rule.name}' scored {{score}}/{{max_score}}"
    
    # Ensure score is in valid range
    score = max(0.0, min(score, {max_score}))
    
    print(json.dumps({{
        "score": score,
        "feedback": feedback,
        "evaluated_resource_ids": {json.dumps(evaluated_resource_ids)}
    }}))
except Exception as e:
    import traceback
    error_msg = str(e) + "\\n" + traceback.format_exc()
    print(json.dumps({{
        "score": 0.0,
        "feedback": f"Error executing code rule: {{error_msg}}",
        "evaluated_resource_ids": []
    }}))
"""
    return code


def _parse_code_rule_result(
    execution_logs: Logs,
    max_score: float,
) -> tuple[float, str, list[str]]:
    """Parse result from code rule execution."""
    stdout_parts = []
    for log in execution_logs.stdout:
        stdout_parts.append(log)

    output = "\n".join(stdout_parts)

    try:
        # Find JSON in stdout
        lines = output.strip().split("\n")
        json_line = None
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") or line.startswith("["):
                json_line = line
                break

        if json_line:
            result_data = json.loads(json_line)
            score = min(max(float(result_data["score"]), 0.0), max_score)
            feedback = result_data["feedback"]
            evaluated_resource_ids = result_data.get("evaluated_resource_ids", [])
            return score, feedback, evaluated_resource_ids
        else:
            raise json.JSONDecodeError("No JSON found", output, 0)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        stderr_parts = []
        for log in execution_logs.stderr:
            stderr_parts.append(log)
        error_msg = "\n".join(stderr_parts) if stderr_parts else str(e)
        return 0.0, f"Error evaluating code rule: {error_msg}", []


def _build_llm_judge_text_content(
    task_input: str,
    agent_reasoning: str,
    rule: LLMJudgeRule,
    max_score: float,
) -> str:
    """Build text content for LLM judge evaluation prompt."""
    expectation_text = f"\nExpectation: {rule.expectation}" if rule.expectation else ""
    return f"""Task Input: {task_input}

Agent Reasoning/Output: {agent_reasoning}

Criterion: {rule.description}{expectation_text}

Please evaluate this output and provide:
1. A score from 0 to {max_score}
2. Detailed feedback explaining your score

Format your response as:
Score: <number>
Feedback: <your feedback>
"""


def _build_llm_judge_content_parts(
    text_content: str,
    agent_outputs: list[Resource],
) -> list[ChatCompletionContentPartParam]:
    """Build content parts for LLM judge evaluation with multimodal support."""
    content_parts: list[ChatCompletionContentPartParam] = [
        ChatCompletionContentPartTextParam(
            type="text",
            text=text_content,
        )
    ]

    # Add file content as images (for PDFs, Excel, images)
    for resource in agent_outputs:
        if resource.mime_type.startswith("image/"):
            content_bytes = resource.load_content()
            base64_content = base64.b64encode(content_bytes).decode()
            content_parts.append(
                ChatCompletionContentPartImageParam(
                    type="image_url",
                    image_url={"url": f"data:{resource.mime_type};base64,{base64_content}"},
                )
            )
        elif resource.mime_type in [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]:
            # For PDFs and Office docs, include text preview in the prompt
            try:
                preview = resource.preview_text or resource.load_text()[:500]
                if len(content_parts) > 0:
                    first_part = content_parts[0]
                    # TypedDict can be accessed as dict
                    if isinstance(first_part, dict) and first_part.get("type") == "text":
                        current_text = first_part.get("text", "")
                        content_parts[0] = ChatCompletionContentPartTextParam(
                            type="text",
                            text=current_text + f"\n\nFile: {resource.name}\nPreview: {preview}...",
                        )
            except Exception:
                if len(content_parts) > 0:
                    first_part = content_parts[0]
                    if isinstance(first_part, dict) and first_part.get("type") == "text":
                        current_text = first_part.get("text", "")
                        content_parts[0] = ChatCompletionContentPartTextParam(
                            type="text",
                            text=current_text + f"\n\nFile: {resource.name} (binary file)",
                        )

    return content_parts


def _build_llm_judge_messages(
    judge_prompt: str,
    content_parts: list[ChatCompletionContentPartParam],
) -> list[ChatCompletionMessageParam]:
    """Build messages list for LLM judge evaluation."""
    return [
        ChatCompletionSystemMessageParam(
            role="system",
            content=judge_prompt,
        ),
        ChatCompletionUserMessageParam(
            role="user",
            content=content_parts,
        ),
    ]


def _parse_llm_judge_score(content: str, max_score: float) -> float:
    """Parse score from LLM judge response."""
    score_match = re.search(r"Score:\s*([\d.]+)", content, re.IGNORECASE)
    if score_match:
        return min(max(float(score_match.group(1)), 0.0), max_score)

    # Try to find any number in the response
    numbers = re.findall(r"[\d.]+", content)
    if numbers:
        return min(max(float(numbers[0]), 0.0), max_score)

    # Default to midpoint if parsing fails
    return max_score * 0.5


async def evaluate_criterion(
    run_id: UUID,
    agent_reasoning: str,
    agent_outputs: list[Resource],
    stage: EvaluationStage,
    rule: CodeRule | LLMJudgeRule,
    stage_idx: int,
    rule_idx: int,
    task_input: str,
    sandbox_manager: SandboxManager | None = None,
) -> CriterionResult:
    """
    Evaluate a single criterion against task outputs.

    Args:
        run_id: The run ID
        agent_reasoning: Worker's reasoning/output text
        agent_outputs: Output files/resources
        stage: The stage containing this criterion
        rule: The rule/criterion to evaluate (CodeRule or LLMJudgeRule)
        stage_idx: Stage index (0, 1, 2, ...)
        rule_idx: Rule index within stage (0, 1, 2, ...)
        task_input: Original task description
        sandbox_manager: Optional sandbox for code rule execution

    Returns:
        CriterionResult with score, feedback, and evaluated references

    Example:
        ```python
        result = await evaluate_criterion(
            run_id=run_id,
            agent_reasoning="I created a PDF report...",
            agent_outputs=[resource1, resource2],
            stage=stage,
            rule=code_rule,
            stage_idx=0,
            rule_idx=0,
            task_input="Create a report",
            sandbox_manager=sandbox_manager
        )
        print(f"Score: {result.score}/{result.max_score}")
        ```
    """
    max_score = rule.weight * stage.max_points

    match rule.type:
        case "code":
            return await _evaluate_code_rule(
                run_id=run_id,
                agent_reasoning=agent_reasoning,
                agent_outputs=agent_outputs,
                rule=rule,
                stage=stage,
                stage_idx=stage_idx,
                rule_idx=rule_idx,
                task_input=task_input,
                sandbox_manager=sandbox_manager,
                max_score=max_score,
            )
        case "llm_judge":
            return await _evaluate_llm_judge(
                run_id=run_id,
                agent_reasoning=agent_reasoning,
                agent_outputs=agent_outputs,
                rule=rule,
                stage=stage,
                stage_idx=stage_idx,
                rule_idx=rule_idx,
                task_input=task_input,
                max_score=max_score,
            )
        case _:
            raise ValueError(f"Unknown rule type: {rule.type}")


async def _evaluate_code_rule(
    run_id: UUID,
    agent_reasoning: str,
    agent_outputs: list[Resource],
    rule: CodeRule,
    stage: EvaluationStage,
    stage_idx: int,
    rule_idx: int,
    task_input: str,
    sandbox_manager: SandboxManager | None,
    max_score: float,
) -> CriterionResult:
    """Execute code rule in sandbox."""
    sandbox_manager = SandboxManager()

    if sandbox_manager is None:
        # Create temporary sandbox for evaluation
        await sandbox_manager.create(run_id)
        should_terminate = True
    else:
        # Use existing sandbox - ensure it exists
        sandbox = sandbox_manager.get_sandbox(run_id)
        if not sandbox:
            await sandbox_manager.create(run_id)
            should_terminate = True  # We created it, so we should terminate it
        else:
            should_terminate = False  # Using existing sandbox, don't terminate

    try:
        # Upload output files to sandbox
        sandbox = sandbox_manager.get_sandbox(run_id)
        if not sandbox:
            raise RuntimeError("Sandbox not created")
        for resource in agent_outputs:
            sandbox_path = f"/evaluation/{resource.name}"
            content = resource.load_content()
            await sandbox.files.write(sandbox_path, content)

        # Prepare evaluation context
        # Code rules expect: evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> float | tuple[float, str]
        code = _build_code_rule_evaluation_code(
            rule=rule,
            task_input=task_input,
            agent_reasoning=agent_reasoning,
            agent_outputs=agent_outputs,
            max_score=max_score,
        )

        sandbox = sandbox_manager.get_sandbox(run_id)
        if not sandbox:
            raise RuntimeError("Sandbox not created")
        execution = await sandbox.run_code(code, language="python", timeout=30)

        # Parse result
        score, feedback, evaluated_resource_ids = _parse_code_rule_result(
            execution_logs=execution.logs,
            max_score=max_score,
        )

        return CriterionResult(
            run_id=run_id,
            stage_num=stage_idx,
            stage_name=stage.name,
            criterion_num=rule_idx,
            criterion_type="code_rule",
            criterion_description=rule.description,
            score=score,
            max_score=max_score,
            feedback=feedback,
            evaluated_action_ids=[],
            evaluated_resource_ids=evaluated_resource_ids,
        )

    finally:
        if should_terminate:
            await sandbox_manager.terminate(run_id)


async def _evaluate_llm_judge(
    run_id: UUID,
    agent_reasoning: str,
    agent_outputs: list[Resource],
    rule: LLMJudgeRule,
    stage: EvaluationStage,
    stage_idx: int,
    rule_idx: int,
    task_input: str,
    max_score: float,
) -> CriterionResult:
    """Execute LLM judge evaluation."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Build messages with multimodal content using OpenAI types
    text_content = _build_llm_judge_text_content(
        task_input=task_input,
        agent_reasoning=agent_reasoning,
        rule=rule,
        max_score=max_score,
    )

    content_parts = _build_llm_judge_content_parts(
        text_content=text_content,
        agent_outputs=agent_outputs,
    )

    messages = _build_llm_judge_messages(
        judge_prompt=rule.judge_prompt,
        content_parts=content_parts,
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=500,
        temperature=0.0,  # Deterministic scoring
    )

    # Parse LLM response (expects score and feedback)
    content = response.choices[0].message.content
    if content is None:
        content = "No response from LLM judge"

    score = _parse_llm_judge_score(content=content, max_score=max_score)
    feedback = content

    return CriterionResult(
        run_id=run_id,
        stage_num=stage_idx,
        stage_name=stage.name,
        criterion_num=rule_idx,
        criterion_type="llm_judge",
        criterion_description=rule.description,
        score=score,
        max_score=max_score,
        feedback=feedback,
        evaluated_action_ids=[],
        evaluated_resource_ids=[str(r.id) for r in agent_outputs],
    )
