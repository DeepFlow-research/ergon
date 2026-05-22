from pathlib import Path


ROOT = Path("ergon_builtins/ergon_builtins/benchmarks")


def test_tool_response_models_do_not_import_tool_builders() -> None:
    for path in ROOT.glob("*/tools/response_models.py"):
        text = path.read_text()
        assert ".tools.tool_builder import" not in text, path


def test_tool_builders_import_response_models() -> None:
    for path in ROOT.glob("*/tools/tool_builder.py"):
        text = path.read_text()
        assert ".tools.response_models import" in text, path


def test_empty_operations_modules_are_deleted() -> None:
    assert not list(ROOT.glob("*/tools/operations.py"))


def test_gdpeval_task_schemas_do_not_contain_tool_response_dtos() -> None:
    text = Path("ergon_builtins/ergon_builtins/benchmarks/gdpeval/task_schemas.py").read_text()
    assert "ReadPDFResponse" not in text
    assert "CreateDocxResponse" not in text
    assert "OcrImageResponse" not in text


def test_builtins_do_not_configure_logfire_observability() -> None:
    assert not Path("ergon_builtins/ergon_builtins/observability").exists()
    react_worker = Path("ergon_builtins/ergon_builtins/agents/react/worker.py").read_text()
    assert "configure_pydantic_ai_logfire" not in react_worker
    assert "logfire" not in react_worker.lower()
