"""Smoke test benchmark configuration."""

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.common.workers.config import WorkerConfig

SMOKE_TEST_PROMPT = """
You are a test worker for smoke testing the h_arcane pipeline.

Your goal is to exercise the workflow system by using the available tools.
Tools return mock data - focus on correct workflow execution.

Available tools:
- `read_file`: Read contents of a file (returns mock data)
- `write_file`: Write contents to a file (returns mock success)
- `analyze_data`: Analyze data (returns mock findings)
- `ask_stakeholder`: Ask clarification questions

## Guidelines

1. Use tools in a logical sequence based on the task
2. Ask the stakeholder when you need clarification
3. Report your findings when done

Think step by step and complete the task.
"""

SMOKE_TEST_CONFIG = WorkerConfig(
    benchmark_name=BenchmarkName.SMOKE_TEST,
    system_prompt=SMOKE_TEST_PROMPT,
    max_questions=3,
)
