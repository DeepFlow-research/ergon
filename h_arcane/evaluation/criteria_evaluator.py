"""Criteria evaluator for single criterion evaluation."""

import base64
import json
import logging
import re

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

import inngest

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.db.models import CriterionResult, Resource
from h_arcane.inngest.client import inngest_client
from h_arcane.inngest.events import CriterionEvaluationEvent
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

    # Build file loading code with error handling
    file_loading_code_parts = []
    for resource in agent_outputs:
        file_loading_code_parts.append(
            f"try:\n"
            f'    with open("/evaluation/{resource.name}", "rb") as f:\n'
            f'        output_files["/evaluation/{resource.name}"] = f.read()\n'
            f'        print(f"Loaded file: {resource.name} ({{len(output_files["/evaluation/{resource.name}"])}} bytes)")\n'
            f"except Exception as e:\n"
            f'    print(f"Warning: Failed to load {resource.name}: {{e}}", file=sys.stderr)\n'
        )
    file_loading_code = "\n".join(file_loading_code_parts)

    code = f"""import json
import re
import sys
import traceback
import pandas as pd
import numpy as np
import pdfplumber
from docx import Document
from io import BytesIO

# Set max_score for use in feedback messages
max_score = {max_score}

{rule.code}

# Prepare output_files dict
output_files = {{}}
print(f"Loading {{len({json.dumps([r.name for r in agent_outputs])})}} files into output_files...")
{file_loading_code}
print(f"Loaded {{len(output_files)}} files successfully")

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
    score = max(0.0, min(score, max_score))
    
    print(json.dumps({{
        "score": score,
        "feedback": feedback,
        "evaluated_resource_ids": {json.dumps(evaluated_resource_ids)}
    }}))
except Exception as e:
    error_msg = str(e)
    full_traceback = traceback.format_exc()
    print(json.dumps({{
        "score": 0.0,
        "feedback": f"Error executing code rule: {{error_msg}}\\n\\nFull traceback:\\n{{full_traceback}}",
        "evaluated_resource_ids": []
    }}))
"""
    return code


def _parse_code_rule_result(
    stdout: list[str],
    stderr: list[str],
    max_score: float,
) -> tuple[float, str, list[str]]:
    """Parse result from code rule execution.

    Args:
        stdout: List of stdout log lines
        stderr: List of stderr log lines
        max_score: Maximum score for validation
    """
    output = "\n".join(stdout)
    stderr_output = "\n".join(stderr) if stderr else ""

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

            # Include stderr in feedback if present (for debugging)
            if stderr_output and "Error" not in feedback:
                feedback = f"{feedback}\n\n[Debug stderr: {stderr_output[:200]}]"

            return score, feedback, evaluated_resource_ids
        else:
            # No JSON found - return error with full context
            error_msg = f"No JSON output found. Stdout: {output[:500]}"
            if stderr_output:
                error_msg += f"\nStderr: {stderr_output[:500]}"
            raise json.JSONDecodeError(error_msg, output, 0)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # Return detailed error information
        error_msg = stderr_output if stderr_output else str(e)
        if not error_msg:
            error_msg = f"Parse error: {e}\nStdout: {output[:500]}"
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
                if content_parts:
                    first_part = content_parts[0]
                    # Access text field from TypedDict
                    if isinstance(first_part, dict) and first_part.get("type") == "text":
                        existing_text_value = first_part.get("text")
                        existing_text = (
                            existing_text_value if isinstance(existing_text_value, str) else ""
                        )
                        content_parts[0] = ChatCompletionContentPartTextParam(
                            type="text",
                            text=existing_text
                            + f"\n\nFile: {resource.name}\nPreview: {preview}...",
                        )
            except Exception:
                if content_parts:
                    first_part = content_parts[0]
                    if isinstance(first_part, dict) and first_part.get("type") == "text":
                        existing_text_value = first_part.get("text")
                        existing_text = (
                            existing_text_value if isinstance(existing_text_value, str) else ""
                        )
                        content_parts[0] = ChatCompletionContentPartTextParam(
                            type="text",
                            text=existing_text + f"\n\nFile: {resource.name} (binary file)",
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
    # First try to find explicit "Score: X" pattern
    score_match = re.search(r"Score:\s*(\d+\.?\d*)", content, re.IGNORECASE)
    if score_match:
        try:
            return min(max(float(score_match.group(1)), 0.0), max_score)
        except ValueError:
            pass

    # Try to find any valid number in the response (must have at least one digit)
    # Pattern: digits optionally followed by dot and more digits, or dot followed by digits
    numbers = re.findall(r"\d+\.?\d*|\.\d+", content)
    if numbers:
        try:
            return min(max(float(numbers[0]), 0.0), max_score)
        except ValueError:
            pass

    # Default to midpoint if parsing fails
    return max_score * 0.5


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="evaluate-criterion",
    trigger=inngest.TriggerEvent(event="criterion/evaluate"),
    retries=2,
    concurrency=[inngest.Concurrency(limit=20, scope="fn")],
    output_type=CriterionResult,
)
async def evaluate_criterion_fn(
    ctx: inngest.Context,
) -> CriterionResult:
    """
    Evaluate a single criterion against task outputs.

    This is an Inngest function that provides detailed tracing for criterion evaluation.
    """
    event_data = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)
    task_input = event_data.task_input
    agent_reasoning = event_data.agent_reasoning
    stage_idx = event_data.stage_idx
    rule_idx = event_data.rule_idx

    # Extract objects directly (Pydantic handles deserialization)
    stage = event_data.stage
    rule = event_data.rule
    agent_outputs = event_data.agent_outputs

    # Calculate max_score directly (simple multiplication doesn't need a step)
    max_score = rule.weight * stage.max_points

    # Evaluate based on rule type
    if isinstance(rule, CodeRule):
        # Evaluate code rule
        # Ensure sandbox exists (step for idempotency)
        async def ensure_sandbox():
            sandbox_manager = SandboxManager()
            sandbox = sandbox_manager.get_sandbox(run_id)
            if not sandbox:
                await sandbox_manager.create(run_id)
                should_terminate = True
            else:
                should_terminate = False
            return {"sandbox_ready": True, "should_terminate": should_terminate}

        sandbox_info = await ctx.step.run("ensure-sandbox", ensure_sandbox)

        # Upload files to sandbox (step for observability and retry)
        async def upload_files():
            sandbox_manager = SandboxManager()
            sandbox = sandbox_manager.get_sandbox(run_id)
            if not sandbox:
                raise RuntimeError("Sandbox not created")

            uploaded_files = []
            failed_files = []
            for resource in agent_outputs:
                sandbox_path = f"/evaluation/{resource.name}"
                try:
                    content = resource.load_content()
                    if not isinstance(content, bytes):
                        content = (
                            bytes(content)
                            if hasattr(content, "__bytes__")
                            else str(content).encode("utf-8")
                        )
                    await sandbox.files.write(sandbox_path, content)
                    uploaded_files.append(resource.name)
                except Exception as e:
                    failed_files.append((resource.name, str(e)))

            if not uploaded_files:
                raise RuntimeError(
                    f"No files were successfully uploaded to sandbox. Failed: {failed_files}"
                )

            return {
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
            }

        await ctx.step.run("upload-files", upload_files)

        # Build evaluation code (no step needed - just string building)
        evaluation_code = _build_code_rule_evaluation_code(
            rule=rule,
            task_input=task_input,
            agent_reasoning=agent_reasoning,
            agent_outputs=agent_outputs,
            max_score=max_score,
        )

        async def execute_code():
            sandbox_manager = SandboxManager()
            sandbox = sandbox_manager.get_sandbox(run_id)
            if not sandbox:
                raise RuntimeError("Sandbox not created")

            try:
                execution = await sandbox.run_code(evaluation_code, language="python", timeout=30)
                # Serialize logs for storage
                return {
                    "execution_logs": {
                        "stdout": list(execution.logs.stdout),
                        "stderr": list(execution.logs.stderr),
                    },
                    "code": evaluation_code,
                }
            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower() or "sandbox was not found" in error_msg.lower():
                    raise RuntimeError(
                        f"Sandbox execution failed (likely timeout): {error_msg}. "
                        f"This may indicate the code rule took too long (>30s) or the sandbox was terminated."
                    ) from e
                raise

        execution_result = await ctx.step.run("execute-code", execute_code)

        async def parse_code_result():
            score, feedback, evaluated_resource_ids = _parse_code_rule_result(
                stdout=execution_result["execution_logs"]["stdout"],
                stderr=execution_result["execution_logs"]["stderr"],
                max_score=max_score,
            )
            return {
                "score": float(score),
                "feedback": feedback,
                "evaluated_resource_ids": evaluated_resource_ids,
            }

        code_result = await ctx.step.run("parse-code-result", parse_code_result)

        # Cleanup sandbox if we created it
        if sandbox_info["should_terminate"]:

            async def cleanup_sandbox():
                sandbox_manager = SandboxManager()
                await sandbox_manager.terminate(run_id)
                return {"cleaned_up": True}

            await ctx.step.run("cleanup-sandbox", cleanup_sandbox)

        evaluation_result = {
            "score": code_result["score"],
            "feedback": code_result["feedback"],
            "evaluated_resource_ids": code_result["evaluated_resource_ids"],
            "evaluation_input": evaluation_code,
        }

    else:
        # Evaluate LLM judge
        # Build prompt and content parts directly (no step needed - just string building)
        if not isinstance(rule, LLMJudgeRule):
            raise ValueError("Rule must be LLMJudgeRule in this branch")
        llm_judge_rule = rule

        judge_prompt_text = _build_llm_judge_text_content(
            task_input=task_input,
            agent_reasoning=agent_reasoning,
            rule=llm_judge_rule,
            max_score=max_score,
        )

        content_parts = _build_llm_judge_content_parts(
            text_content=judge_prompt_text,
            agent_outputs=agent_outputs,
        )

        messages = _build_llm_judge_messages(
            judge_prompt=llm_judge_rule.judge_prompt,
            content_parts=content_parts,
        )

        # Call LLM API (step for observability and retry)
        async def call_llm_api():
            client = AsyncOpenAI(api_key=settings.openai_api_key)

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=5000,
                temperature=0.0,
            )

            content = response.choices[0].message.content
            if content is None:
                content = "No response from LLM judge"

            return {
                "content": content,
                "model": "gpt-4o",
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            }

        llm_result = await ctx.step.run("call-llm-api", call_llm_api)

        async def parse_llm_result():
            score = _parse_llm_judge_score(content=llm_result["content"], max_score=max_score)
            feedback = llm_result["content"]
            return {
                "score": float(score),
                "feedback": feedback,
            }

        llm_parse_result = await ctx.step.run("parse-llm-result", parse_llm_result)

        evaluation_result = {
            "score": llm_parse_result["score"],
            "feedback": llm_parse_result["feedback"],
            "evaluated_resource_ids": [str(r.id) for r in agent_outputs],
            "evaluation_input": str(messages),
        }

    # Build and return criterion result (no step needed - just object construction)
    rule_type = "code_rule" if isinstance(rule, CodeRule) else "llm_judge"
    return CriterionResult(
        run_id=run_id,
        stage_num=stage_idx,
        stage_name=stage.name,
        criterion_num=rule_idx,
        criterion_type=rule_type,
        criterion_description=rule.description,
        score=evaluation_result["score"],
        max_score=max_score,
        feedback=evaluation_result["feedback"],
        evaluation_input=evaluation_result["evaluation_input"],
        evaluated_action_ids=[],
        evaluated_resource_ids=evaluation_result["evaluated_resource_ids"],
    )


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

    # Use isinstance for proper type narrowing
    if isinstance(rule, CodeRule):
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
    elif isinstance(rule, LLMJudgeRule):
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
    else:
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
    if sandbox_manager is None:
        # Create temporary sandbox for evaluation
        sandbox_manager = SandboxManager()
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

        uploaded_files = []
        failed_files = []
        for resource in agent_outputs:
            sandbox_path = f"/evaluation/{resource.name}"
            try:
                content = resource.load_content()
                # Ensure content is bytes (E2B requires bytes for binary files)
                if not isinstance(content, bytes):
                    content = (
                        bytes(content)
                        if hasattr(content, "__bytes__")
                        else str(content).encode("utf-8")
                    )
                await sandbox.files.write(sandbox_path, content)
                uploaded_files.append(resource.name)
                logger = logging.getLogger(__name__)
                logger.debug(f"Uploaded {resource.name} ({len(content)} bytes) to {sandbox_path}")
            except Exception as e:
                # Log error but continue - some resources might be missing
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Failed to load/upload resource {resource.id} ({resource.name}): {e}"
                )
                failed_files.append((resource.name, str(e)))

        if failed_files:
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to upload {len(failed_files)}/{len(agent_outputs)} files: {failed_files}"
            )

        if not uploaded_files:
            raise RuntimeError(
                f"No files were successfully uploaded to sandbox. Failed: {failed_files}"
            )

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

        # Execute code with timeout handling
        try:
            execution = await sandbox.run_code(code, language="python", timeout=30)
        except Exception as e:
            # If sandbox times out or fails, check if it was auto-terminated
            # and provide better error message
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "sandbox was not found" in error_msg.lower():
                # Sandbox may have been auto-terminated by E2B
                # Try to clean up gracefully
                if should_terminate:
                    # Don't try to terminate again - sandbox is already gone
                    should_terminate = False
                raise RuntimeError(
                    f"Sandbox execution failed (likely timeout): {error_msg}. "
                    f"This may indicate the code rule took too long (>30s) or the sandbox was terminated."
                ) from e
            raise

        # Parse result
        print("CODE AND ITS EXECUTION: ", code, execution)
        score, feedback, evaluated_resource_ids = _parse_code_rule_result(
            stdout=list(execution.logs.stdout),
            stderr=list(execution.logs.stderr),
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
            evaluation_input=code,  # Store full generated code
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

    # Store messages as string for debugging
    evaluation_input = str(messages)

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
        evaluation_input=evaluation_input,  # Store serialized prompt/messages
        evaluated_action_ids=[],
        evaluated_resource_ids=[str(r.id) for r in agent_outputs],
    )
