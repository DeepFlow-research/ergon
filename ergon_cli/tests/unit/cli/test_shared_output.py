from pydantic import BaseModel

from ergon_cli.shared.output import render_json, render_table, render_text


class _Payload(BaseModel):
    name: str


def test_render_table_returns_text_without_printing() -> None:
    output = render_table(["Slug", "Name"], [["react-v1", "ReActWorker"]])

    assert "Slug" in output
    assert "react-v1" in output


def test_render_table_handles_empty_rows() -> None:
    assert render_table(["Slug"], []) == "(no entries)"


def test_render_json_accepts_models_and_mappings() -> None:
    assert '"name": "ergon"' in render_json(_Payload(name="ergon"))
    assert '"ok": true' in render_json({"ok": True})


def test_render_text_joins_lines() -> None:
    assert render_text(["a", 2]) == "a\n2"
