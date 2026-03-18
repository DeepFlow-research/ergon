"""Pre-defined DAG workflow patterns for smoke testing.

This module provides factory functions to create test workflows of varying
complexity for validating the h_arcane execution pipeline.

Workflow Patterns:
- Single: One atomic task (simplest case)
- Linear: A -> B -> C (sequential dependencies)
- Parallel: A -> [B, C] -> D (fan-out and fan-in)
- Nested: L1 -> L2 -> L3 (hierarchical subtasks)
"""

from typing import TYPE_CHECKING

from h_arcane.core.task import Task
from h_arcane.benchmarks.smoke_test.rubric import SmokeTestRubric
from h_arcane.core._internal.evaluation.rules import CodeRule, LLMJudgeRule

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker


# Simple code rule that checks agent output contains text
SMOKE_TEST_CODE_RULE = '''
def evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> tuple[float, str]:
    """Check that agent produced non-empty output."""
    if not agent_reasoning or len(agent_reasoning.strip()) < 10:
        return 0.0, "Agent produced no meaningful output text"
    
    word_count = len(agent_reasoning.split())
    if word_count < 5:
        return 0.3, f"Agent output is very short ({word_count} words)"
    elif word_count < 20:
        return 0.7, f"Agent produced brief output ({word_count} words)"
    else:
        return 1.0, f"Agent produced sufficient output ({word_count} words)"
'''


def create_smoke_test_rubric(task_name: str) -> SmokeTestRubric:
    """Create a rubric for smoke test evaluation.

    Uses both CodeRule and LLMJudgeRule to test the full evaluation pipeline
    including sandbox code execution.

    Args:
        task_name: Name of the task being evaluated

    Returns:
        SmokeTestRubric with both rule types for comprehensive testing
    """
    return SmokeTestRubric(
        rules=[
            # CodeRule: Tests sandbox code execution path
            CodeRule(
                name="output_presence",
                description="Check that agent produced non-empty output text",
                weight=1.0,
                code=SMOKE_TEST_CODE_RULE,
            ),
            # LLMJudgeRule: Tests LLM judge evaluation path
            LLMJudgeRule(
                name="output_quality",
                description="Check if the agent produced a reasonable output",
                weight=1.0,
                judge_prompt=f"""Evaluate the agent's response for task '{task_name}'.

The agent was asked to complete a simple smoke test task. Evaluate whether:
1. The agent attempted to address the task
2. The response is coherent and relevant
3. The agent completed the task (even if with mock/simulated data)

This is a smoke test - we're checking if the pipeline works, not perfection.
Be lenient: give full credit if the agent made a reasonable attempt.

Return True if the agent made a reasonable attempt, False only for complete failures.""",
            ),
        ],
    )


def create_single_task_workflow(worker: "BaseWorker") -> Task:
    """Create a single-task workflow (simplest case).

    This is the minimal test case - one atomic task with no dependencies.

    Args:
        worker: The worker to assign to the task

    Returns:
        Task: A single standalone task
    """
    return Task(
        name="smoke_single",
        description=(
            "Read the data file and provide a brief summary of its contents. "
            "This is a simple single-step task for smoke testing."
        ),
        assigned_to=worker,
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_single"),
    )


def create_linear_chain_workflow(worker: "BaseWorker") -> Task:
    """Create a linear workflow: A -> B -> C (sequential dependencies).

    Tests that tasks execute in order when dependencies are specified.

    Args:
        worker: The worker to assign to all tasks

    Returns:
        Task: Root task containing the linear chain as children
    """
    # Task A: Read data
    task_a = Task(
        name="smoke_linear_read",
        description="Read the input data file and extract key information.",
        assigned_to=worker,
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_linear_read"),
    )

    # Task B: Analyze (depends on A)
    task_b = Task(
        name="smoke_linear_analyze",
        description=(
            "Based on the data from the previous step, analyze the information "
            "and identify key patterns."
        ),
        assigned_to=worker,
        depends_on=[task_a],
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_linear_analyze"),
    )

    # Task C: Report (depends on B)
    task_c = Task(
        name="smoke_linear_report",
        description=(
            "Generate a final summary report based on the analysis. "
            "Include the key findings from the previous steps."
        ),
        assigned_to=worker,
        depends_on=[task_b],
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_linear_report"),
    )

    # Root task containing the chain
    return Task(
        name="smoke_linear_workflow",
        description="Linear workflow: read -> analyze -> report",
        assigned_to=worker,
        children=[task_a, task_b, task_c],
    )


def create_parallel_workflow(worker: "BaseWorker") -> Task:
    """Create a parallel workflow: A -> [B, C] -> D (fan-out and fan-in).

    Tests that independent tasks run in parallel, and a final task waits
    for all parallel tasks to complete.

    Args:
        worker: The worker to assign to all tasks

    Returns:
        Task: Root task containing the parallel workflow structure
    """
    # Task A: Initial data gathering
    task_a = Task(
        name="smoke_parallel_gather",
        description="Gather the initial data and prepare it for parallel processing.",
        assigned_to=worker,
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_parallel_gather"),
    )

    # Task B: Analysis branch 1 (depends on A, parallel with C)
    task_b = Task(
        name="smoke_parallel_analyze_1",
        description="Perform the first type of analysis on the gathered data.",
        assigned_to=worker,
        depends_on=[task_a],
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_parallel_analyze_1"),
    )

    # Task C: Analysis branch 2 (depends on A, parallel with B)
    task_c = Task(
        name="smoke_parallel_analyze_2",
        description="Perform the second type of analysis on the gathered data.",
        assigned_to=worker,
        depends_on=[task_a],
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_parallel_analyze_2"),
    )

    # Task D: Merge results (depends on both B and C)
    task_d = Task(
        name="smoke_parallel_merge",
        description=(
            "Combine the results from both analysis branches and produce a unified summary report."
        ),
        assigned_to=worker,
        depends_on=[task_b, task_c],
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_parallel_merge"),
    )

    # Root task containing the parallel structure
    return Task(
        name="smoke_parallel_workflow",
        description="Parallel workflow: gather -> [analyze_1, analyze_2] -> merge",
        assigned_to=worker,
        children=[task_a, task_b, task_c, task_d],
    )


def create_nested_hierarchy_workflow(worker: "BaseWorker") -> Task:
    """Create a nested hierarchy: L1 -> L2 -> L3 (hierarchical subtasks).

    Tests that nested task hierarchies (tasks containing subtasks
    that contain their own subtasks) execute correctly.

    Args:
        worker: The worker to assign to all tasks

    Returns:
        Task: Root task with deeply nested children
    """
    # Level 3 tasks (leaf tasks)
    task_l3_a = Task(
        name="smoke_nested_l3_read",
        description="Read the data file at the leaf level.",
        assigned_to=worker,
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_nested_l3_read"),
    )

    task_l3_b = Task(
        name="smoke_nested_l3_process",
        description="Process the data at the leaf level.",
        assigned_to=worker,
        depends_on=[task_l3_a],
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_nested_l3_process"),
    )

    # Level 2 task (contains L3 tasks)
    task_l2 = Task(
        name="smoke_nested_l2_stage",
        description="Mid-level processing stage containing leaf tasks.",
        assigned_to=worker,
        children=[task_l3_a, task_l3_b],
    )

    # Level 2 sibling (independent of task_l2)
    task_l2_sibling = Task(
        name="smoke_nested_l2_independent",
        description="Independent mid-level task that runs in parallel.",
        assigned_to=worker,
        resources=[],
        evaluator=create_smoke_test_rubric("smoke_nested_l2_independent"),
    )

    # Level 1 root
    return Task(
        name="smoke_nested_workflow",
        description="Nested hierarchy workflow with multiple levels of subtasks.",
        assigned_to=worker,
        children=[task_l2, task_l2_sibling],
    )


# Mapping of workflow names to factory functions
WORKFLOW_FACTORIES = {
    "single": create_single_task_workflow,
    "linear": create_linear_chain_workflow,
    "parallel": create_parallel_workflow,
    "nested": create_nested_hierarchy_workflow,
}


def create_workflow(workflow_name: str, worker: "BaseWorker") -> Task:
    """Create a workflow by name.

    Args:
        workflow_name: One of "single", "linear", "parallel", "nested"
        worker: The worker to assign to tasks

    Returns:
        Task: The created workflow

    Raises:
        ValueError: If workflow_name is not recognized
    """
    if workflow_name not in WORKFLOW_FACTORIES:
        available = ", ".join(WORKFLOW_FACTORIES.keys())
        raise ValueError(f"Unknown workflow '{workflow_name}'. Available: {available}")

    factory = WORKFLOW_FACTORIES[workflow_name]
    return factory(worker)


def list_workflows() -> list[str]:
    """List available workflow names.

    Returns:
        List of workflow names that can be passed to create_workflow()
    """
    return list(WORKFLOW_FACTORIES.keys())
