"""MiniF2F worker factories — one per agentic strategy.

Each factory bundles the MiniF2F sandbox, toolkit, and system
prompt with a chosen worker class (ReActWorker today; CoTWorker /
ReflexionWorker future).  Strategies vary independently; the
domain bundle is constant.

Legacy registry bridge (MiniF2FReactWorker) lives in
`_legacy_workers.py` and is deleted in PR 11.
"""

from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.workers.baselines.react_prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.workers.baselines.react_worker import ReActWorker


def make_minif2f_worker() -> ReActWorker:
    """Return a serializable ReActWorker for MiniF2F (v2 authoring shape)."""
    return ReActWorker(
        name="solver",
        model="openai:gpt-4o-mini",
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
        toolkit=MiniF2FToolkit(),
    )


def make_minif2f_rubric() -> MiniF2FRubric:
    """Return a serializable MiniF2FRubric for use as an inline evaluator."""
    return MiniF2FRubric(name="minif2f-rubric")
