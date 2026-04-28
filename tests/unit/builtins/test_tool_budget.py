from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetExhaustedResult,
    AgentToolBudgetState,
)


def test_tool_budget_exhausts_workflow_calls_with_structured_result() -> None:
    state = AgentToolBudgetState(
        max_workflow_tool_calls=1,
        max_other_tool_calls=2,
    )

    first = state.increment("workflow", "workflow")
    second = state.increment("workflow", "workflow")
    exhausted = state.exhausted_result("workflow tool budget reached")

    assert first == 1
    assert second == 2
    assert second > state.max_workflow_tool_calls
    assert isinstance(exhausted, AgentToolBudgetExhaustedResult)
    assert exhausted.status == "TOOL_BUDGET_EXHAUSTED"
    assert exhausted.reason == "workflow tool budget reached"
    assert exhausted.budget_state["workflow_tool_calls"] == 2


def test_tool_budget_allows_finalization_after_other_exhaustion() -> None:
    state = AgentToolBudgetState(
        max_workflow_tool_calls=1,
        max_other_tool_calls=1,
    )

    assert state.increment("exa_search", "other") == 1
    assert state.increment("list_child_resources", "other") == 2
    finalization_count = state.increment("write_report_draft", "finalization")

    assert state.other_tool_calls > state.max_other_tool_calls
    assert finalization_count == 1
    assert state.finalization_tool_calls == 1


def test_tool_budget_deps_wraps_mutable_state() -> None:
    state = AgentToolBudgetState(
        max_workflow_tool_calls=1,
        max_other_tool_calls=1,
    )
    deps = AgentToolBudgetDeps(tool_budget=state)

    deps.tool_budget.increment("exa_search", "other")

    assert deps.tool_budget.other_tool_calls == 1
