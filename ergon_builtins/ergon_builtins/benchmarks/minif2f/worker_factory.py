"""MiniF2F worker factory helpers."""

from ergon_builtins.shared.workers.react_prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.shared.workers.react_worker import ReActWorker
from ergon_builtins.toolkits.minif2f import MiniF2FReActToolkit


def make_minif2f_react_worker(*, name: str, model: str | None) -> ReActWorker:
    return ReActWorker(
        name=name,
        model=model,
        toolkit=MiniF2FReActToolkit(),
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
    )
