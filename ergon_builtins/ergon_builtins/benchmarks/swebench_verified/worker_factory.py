"""SWE-Bench Verified worker factory helpers."""

from ergon_builtins.shared.workers.react_prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.shared.workers.react_worker import ReActWorker
from ergon_builtins.toolkits.swebench import SWEBenchReActToolkit


def make_swebench_react_worker(*, name: str, model: str | None) -> ReActWorker:
    return ReActWorker(
        name=name,
        model=model,
        toolkit=SWEBenchReActToolkit(),
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
    )
