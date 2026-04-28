from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ToolBudgetKind = Literal["workflow", "other", "finalization"]
ToolBudgetExhaustedStatus = Literal["TOOL_BUDGET_EXHAUSTED"]


class AgentToolBudgetExhaustedResult(BaseModel):
    status: ToolBudgetExhaustedStatus = "TOOL_BUDGET_EXHAUSTED"
    reason: str
    message: str
    budget_state: dict[str, Any]  # slopcop: ignore[no-typing-any]


class AgentToolBudgetState(BaseModel):
    max_workflow_tool_calls: int = 12
    max_other_tool_calls: int = 12
    workflow_tool_calls: int = 0
    other_tool_calls: int = 0
    finalization_tool_calls: int = 0
    calls_by_tool: dict[str, int] = Field(default_factory=dict)

    def increment(self, tool_name: str, kind: ToolBudgetKind) -> int:
        self.calls_by_tool[tool_name] = self.calls_by_tool.get(tool_name, 0) + 1

        if kind == "workflow":
            self.workflow_tool_calls += 1
            return self.workflow_tool_calls
        if kind == "finalization":
            self.finalization_tool_calls += 1
            return self.finalization_tool_calls
        self.other_tool_calls += 1
        return self.other_tool_calls

    def snapshot(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        return {
            "workflow_tool_calls": self.workflow_tool_calls,
            "max_workflow_tool_calls": self.max_workflow_tool_calls,
            "other_tool_calls": self.other_tool_calls,
            "max_other_tool_calls": self.max_other_tool_calls,
            "finalization_tool_calls": self.finalization_tool_calls,
            "calls_by_tool": dict(sorted(self.calls_by_tool.items())),
        }

    def exhausted_result(self, reason: str) -> AgentToolBudgetExhaustedResult:
        return AgentToolBudgetExhaustedResult(
            reason=reason,
            message=(
                "Stop calling tools in this category. Use the context/resources already "
                "available and produce the best possible final output. If the output is "
                "incomplete, state what context or resource was missing."
            ),
            budget_state=self.snapshot(),
        )


class AgentToolBudgetDeps(BaseModel):
    tool_budget: AgentToolBudgetState
