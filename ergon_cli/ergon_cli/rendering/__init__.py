"""Text table output and run result formatting."""

from ergon_cli.shared.output import render_table as format_table


def render_table(headers: list[str], rows: list[list[str]]) -> None:
    print(format_table(headers, rows))
