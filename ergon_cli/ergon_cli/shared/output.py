import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from pydantic import BaseModel


def render_json(payload: BaseModel | Mapping[str, object]) -> str:
    if isinstance(payload, BaseModel):
        value = payload.model_dump(mode="json")
    else:
        value = dict(payload)
    return json.dumps(value, indent=2, sort_keys=True)


def render_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    if not rows:
        return "(no entries)"

    col_widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            if index < len(col_widths):
                col_widths[index] = max(col_widths[index], len(str(cell)))

    lines = [
        "  ".join(header.ljust(col_widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in col_widths),
    ]
    lines.extend(
        "  ".join(
            str(cell).ljust(col_widths[index]) if index < len(col_widths) else str(cell)
            for index, cell in enumerate(row)
        )
        for row in rows
    )
    return "\n".join(lines)


def render_text(lines: Sequence[object]) -> str:
    return "\n".join(str(line) for line in lines)


def dump_model(value: BaseModel) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    return cast(dict[str, Any], value.model_dump(mode="json"))
