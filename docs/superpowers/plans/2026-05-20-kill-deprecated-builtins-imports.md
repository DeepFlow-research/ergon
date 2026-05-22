# Kill Deprecated Builtins Imports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove deprecated `ergon_builtins.models.*`, `ergon_builtins.workers.*`, and selected `ergon_builtins.tools.*` compatibility modules after updating live imports to their canonical homes.

**Architecture:** The compatibility modules are one-line re-export shims over the newer `llm`, `agents`, and `toolkits` packages. Update live Python imports first, keep package-level supported imports like `from ergon_builtins.workers import ReActWorker`, then delete the deprecated module files and verify no Python source references the old paths.

**Tech Stack:** Python 3.13, uv workspace, pytest, ruff.

---

## Deprecated Module Map

Replace these module paths:

```text
ergon_builtins.models.resolution                   -> ergon_builtins.llm.resolution
ergon_builtins.models.openrouter_backend           -> ergon_builtins.llm.providers.openrouter
ergon_builtins.models.openrouter_responses_backend -> ergon_builtins.llm.providers.openrouter_responses
ergon_builtins.models.transformers_backend         -> ergon_builtins.llm.providers.transformers
ergon_builtins.models.vllm_backend                 -> ergon_builtins.llm.providers.vllm
ergon_builtins.workers.react_worker                -> ergon_builtins.agents.react.worker
ergon_builtins.workers.react_output                -> ergon_builtins.agents.react.output
ergon_builtins.workers.training_stub_worker        -> ergon_builtins.agents.training.synthetic_worker
ergon_builtins.workers.toolkit                     -> ergon_builtins.toolkits.common.base
ergon_builtins.workers.tool_budget                 -> ergon_builtins.toolkits.common.budgets
ergon_builtins.tools.bash_sandbox_tool             -> ergon_builtins.toolkits.subagents.sandbox_bash
ergon_builtins.tools.graph_toolkit                 -> ergon_builtins.toolkits.resources.toolkit
ergon_builtins.tools.graph_toolkit_types           -> ergon_builtins.toolkits.resources.models
ergon_builtins.tools.subtask_lifecycle_toolkit     -> ergon_builtins.toolkits.subagents.toolkit / ergon_builtins.toolkits.subagents.models
ergon_builtins.tools.workflow_cli_tool             -> ergon_builtins.toolkits.workflow_cli.tool
```

Live Python import hits found by:

```bash
rg -n "from ergon_builtins\.(models|workers|tools)\.(openrouter_responses_backend|resolution|transformers_backend|openrouter_backend|vllm_backend|react_worker|tool_budget|training_stub_worker|toolkit|react_output|bash_sandbox_tool|graph_toolkit_types|subtask_lifecycle_toolkit|workflow_cli_tool|graph_toolkit)" /Users/charliemasters/Desktop/synced_vm_002/ergon -g '*.py'
```

Expected current hits:

```text
ergon/tests/real_llm/spikes/openrouter_reasoning.py
ergon/ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py
ergon/ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py
ergon/ergon_builtins/tests/unit/tools/test_workflow_cli_tool.py
```

## Files

- Modify: `/Users/charliemasters/Desktop/synced_vm_002/ergon/tests/real_llm/spikes/openrouter_reasoning.py`
- Modify: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py`
- Modify: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`
- Modify: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/tests/unit/tools/test_workflow_cli_tool.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/models/openrouter_backend.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/models/openrouter_responses_backend.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/models/resolution.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/models/transformers_backend.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/models/vllm_backend.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/workers/react_output.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/workers/react_worker.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/workers/tool_budget.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/workers/toolkit.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/workers/training_stub_worker.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/tools/graph_toolkit.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/tools/graph_toolkit_types.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`
- Delete: `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`

### Task 1: Update Live Imports

- [ ] **Step 1: Update spike model imports**

In `/Users/charliemasters/Desktop/synced_vm_002/ergon/tests/real_llm/spikes/openrouter_reasoning.py`, replace:

```python
from ergon_builtins.models.cloud_passthrough import resolve_cloud
from ergon_builtins.models.openrouter_backend import resolve_openrouter
from ergon_builtins.models.openrouter_responses_backend import resolve_openrouter_responses
from ergon_builtins.models.resolution import register_model_backend, resolve_model_target
```

with:

```python
from ergon_builtins.llm.providers.openrouter import resolve_openrouter
from ergon_builtins.llm.providers.openrouter_responses import resolve_openrouter_responses
from ergon_builtins.llm.resolution import register_model_backend, resolve_model_target
```

Then resolve the currently stale `resolve_cloud` import separately. There is no `ergon_builtins.models.cloud_passthrough.py` source file, only a stale `__pycache__`; either restore the canonical cloud provider source if it exists elsewhere, or remove the three cloud registrations from this spike script if the script is only for OpenRouter reasoning.

- [ ] **Step 2: Update subtask lifecycle test imports**

In `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py`, replace:

```python
from ergon_builtins.tools.subtask_lifecycle_toolkit import (
    SubtaskLifecycleToolkit,
    ToolFailure,
)
```

with:

```python
from ergon_builtins.toolkits.subagents.models import ToolFailure
from ergon_builtins.toolkits.subagents.toolkit import SubtaskLifecycleToolkit
```

- [ ] **Step 3: Update workflow CLI test imports**

In `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`, replace:

```python
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
```

with:

```python
from ergon_builtins.toolkits.workflow_cli.tool import make_workflow_cli_tool
```

In `/Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/tests/unit/tools/test_workflow_cli_tool.py`, replace:

```python
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_builtins.workers.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetState,
)
```

with:

```python
from ergon_builtins.toolkits.common.budgets import (
    AgentToolBudgetDeps,
    AgentToolBudgetState,
)
from ergon_builtins.toolkits.workflow_cli.tool import make_workflow_cli_tool
```

- [ ] **Step 4: Verify no live Python imports remain**

Run:

```bash
rg -n "from ergon_builtins\.(models|workers|tools)\.(openrouter_responses_backend|resolution|transformers_backend|openrouter_backend|vllm_backend|react_worker|tool_budget|training_stub_worker|toolkit|react_output|bash_sandbox_tool|graph_toolkit_types|subtask_lifecycle_toolkit|workflow_cli_tool|graph_toolkit)" /Users/charliemasters/Desktop/synced_vm_002/ergon -g '*.py'
```

Expected: no output.

### Task 2: Delete Deprecated Compatibility Modules

- [ ] **Step 1: Remove the deprecated shim files**

Delete the fifteen files listed in the Files section whose first line is `Deprecated compatibility import`.

- [ ] **Step 2: Verify no deprecated shim docs remain in source**

Run:

```bash
rg -n "Deprecated compatibility import" /Users/charliemasters/Desktop/synced_vm_002/ergon/ergon_builtins/ergon_builtins -g '*.py'
```

Expected: no output.

- [ ] **Step 3: Verify imports resolve through canonical modules**

Run:

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
uv run python - <<'PY'
from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.agents.training.synthetic_worker import TrainingStubWorker
from ergon_builtins.llm.providers.openrouter import resolve_openrouter
from ergon_builtins.llm.providers.openrouter_responses import resolve_openrouter_responses
from ergon_builtins.llm.providers.transformers import resolve_transformers
from ergon_builtins.llm.providers.vllm import resolve_vllm
from ergon_builtins.llm.resolution import register_model_backend, resolve_model_target
from ergon_builtins.toolkits.common.base import Toolkit
from ergon_builtins.toolkits.common.budgets import AgentToolBudgetState
from ergon_builtins.toolkits.resources.models import ResourceRef, TaskExecutionRef
from ergon_builtins.toolkits.resources.toolkit import ResearchGraphToolkit
from ergon_builtins.toolkits.subagents.models import ToolFailure
from ergon_builtins.toolkits.subagents.sandbox_bash import make_sandbox_bash_tool
from ergon_builtins.toolkits.subagents.toolkit import SubtaskLifecycleToolkit
from ergon_builtins.toolkits.workflow_cli.tool import make_workflow_cli_tool

assert ReActWorker
assert TrainingStubWorker
assert resolve_openrouter
assert resolve_openrouter_responses
assert resolve_transformers
assert resolve_vllm
assert register_model_backend
assert resolve_model_target
assert Toolkit
assert AgentToolBudgetState
assert ResourceRef
assert TaskExecutionRef
assert ResearchGraphToolkit
assert ToolFailure
assert make_sandbox_bash_tool
assert SubtaskLifecycleToolkit
assert make_workflow_cli_tool
PY
```

Expected: exits 0.

### Task 3: Run Focused Tests

- [ ] **Step 1: Run affected tests**

Run:

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
uv run pytest \
  ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py \
  ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py \
  ergon_builtins/tests/unit/tools/test_workflow_cli_tool.py
```

Expected: all tests pass.

- [ ] **Step 2: Run lint on touched Python files**

Run:

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
uv run ruff check \
  tests/real_llm/spikes/openrouter_reasoning.py \
  ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py \
  ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py \
  ergon_builtins/tests/unit/tools/test_workflow_cli_tool.py
```

Expected: exits 0.

- [ ] **Step 3: Run a targeted import grep across Python source**

Run:

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
rg -n "ergon_builtins\.(models|workers|tools)\.(openrouter_responses_backend|resolution|transformers_backend|openrouter_backend|vllm_backend|react_worker|tool_budget|training_stub_worker|toolkit|react_output|bash_sandbox_tool|graph_toolkit_types|subtask_lifecycle_toolkit|workflow_cli_tool|graph_toolkit)" -g '*.py'
```

Expected: no output.

### Task 4: Optional Documentation Sweep

- [ ] **Step 1: Decide whether old plan/RFC docs should be historical**

Most old-path hits outside Python are historical plans and RFCs. Do not rewrite accepted or historical docs unless the team wants them updated; changing them can make old decision records misleading.

- [ ] **Step 2: Update only active docs if desired**

If active docs must avoid deprecated paths, run:

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
rg -n "ergon_builtins\.(models|workers|tools)\.(openrouter_responses_backend|resolution|transformers_backend|openrouter_backend|vllm_backend|react_worker|tool_budget|training_stub_worker|toolkit|react_output|bash_sandbox_tool|graph_toolkit_types|subtask_lifecycle_toolkit|workflow_cli_tool|graph_toolkit)" docs/rfcs/active docs/superpowers/plans
```

Then update only non-historical active design docs that describe the current public surface.
