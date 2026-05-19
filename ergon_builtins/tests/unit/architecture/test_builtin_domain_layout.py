from pathlib import Path


def test_react_implementation_lives_under_agents_react() -> None:
    assert Path("ergon_builtins/ergon_builtins/agents/react/worker.py").exists()
    assert Path("ergon_builtins/ergon_builtins/agents/react/output.py").exists()


def test_training_stub_lives_under_agents_training() -> None:
    assert Path("ergon_builtins/ergon_builtins/agents/training/synthetic_worker.py").exists()


def test_toolkit_base_lives_under_toolkits_common() -> None:
    assert Path("ergon_builtins/ergon_builtins/toolkits/common/base.py").exists()


def test_old_worker_modules_are_compatibility_shims_only() -> None:
    for path in [
        Path("ergon_builtins/ergon_builtins/workers/react_worker.py"),
        Path("ergon_builtins/ergon_builtins/workers/react_output.py"),
        Path("ergon_builtins/ergon_builtins/workers/toolkit.py"),
        Path("ergon_builtins/ergon_builtins/workers/training_stub_worker.py"),
    ]:
        text = path.read_text()
        assert "compatibility import" in text
        assert "\nclass " not in text
        assert "\ndef " not in text


def test_toolkit_implementations_live_under_named_toolkit_packages() -> None:
    for rel in [
        "toolkits/common/budgets.py",
        "toolkits/subagents/toolkit.py",
        "toolkits/subagents/models.py",
        "toolkits/subagents/sandbox_bash.py",
        "toolkits/workflow_cli/tool.py",
        "toolkits/resources/toolkit.py",
        "toolkits/resources/models.py",
    ]:
        assert Path(f"ergon_builtins/ergon_builtins/{rel}").exists()


def test_old_tool_modules_are_compatibility_shims_only() -> None:
    for path in [
        Path("ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py"),
        Path("ergon_builtins/ergon_builtins/tools/graph_toolkit.py"),
        Path("ergon_builtins/ergon_builtins/tools/graph_toolkit_types.py"),
        Path("ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py"),
        Path("ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py"),
        Path("ergon_builtins/ergon_builtins/workers/tool_budget.py"),
    ]:
        text = path.read_text()
        assert "compatibility import" in text
        assert "\nclass " not in text
        assert "\ndef " not in text


def test_llm_provider_implementation_lives_under_llm_package() -> None:
    for rel in [
        "llm/resolution.py",
        "llm/capture_settings.py",
        "llm/providers/openrouter.py",
        "llm/providers/openrouter_responses.py",
        "llm/providers/transformers.py",
        "llm/providers/vllm.py",
    ]:
        assert Path(f"ergon_builtins/ergon_builtins/{rel}").exists()


def test_old_models_modules_are_compatibility_shims_only() -> None:
    for path in [
        Path("ergon_builtins/ergon_builtins/models/resolution.py"),
        Path("ergon_builtins/ergon_builtins/models/openrouter_backend.py"),
        Path("ergon_builtins/ergon_builtins/models/openrouter_responses_backend.py"),
        Path("ergon_builtins/ergon_builtins/models/transformers_backend.py"),
        Path("ergon_builtins/ergon_builtins/models/vllm_backend.py"),
    ]:
        text = path.read_text()
        assert "compatibility import" in text
        assert "\nclass " not in text
        assert "\ndef " not in text
