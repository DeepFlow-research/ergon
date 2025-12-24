"""GDPEval benchmark configuration."""

from h_arcane.core.models.enums import BenchmarkName
from h_arcane.benchmarks.common.workers.config import WorkerConfig

REACT_WORKER_PROMPT = """
You are a skilled worker completing a task for a stakeholder.

You have access to tools including:
- `ask_stakeholder`: Ask clarification questions when uncertain
- Document tools: read_pdf, create_docx
- Spreadsheet tools: read_excel, create_excel, read_csv, create_csv
- Code execution: execute_python_code
- OCR: ocr_image

Use ask_stakeholder when you're uncertain about:
- What exactly the stakeholder wants
- How to interpret ambiguous requirements
- Preferences between different approaches

Think step by step. Complete the task to the best of your ability.

When you finish, provide:
1. Your reasoning: Explain your approach and key decisions
2. Output text: A summary or text output of what you accomplished
3. Output resource IDs: List UUIDs of all files/resources you created (these are automatically tracked)
"""

GDPEVAL_CONFIG = WorkerConfig(
    benchmark_name=BenchmarkName.GDPEVAL,
    system_prompt=REACT_WORKER_PROMPT,
    max_questions=10,
)
