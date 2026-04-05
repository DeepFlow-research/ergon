"""Text table output and run result formatting."""


def render_table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("(no entries)")
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    header_line = "  ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    separator = "  ".join("-" * w for w in col_widths)
    print(header_line)
    print(separator)
    for row in rows:
        line = "  ".join(
            str(cell).ljust(col_widths[i]) if i < len(col_widths) else str(cell)
            for i, cell in enumerate(row)
        )
        print(line)


def render_run_result(persisted) -> None:
    print(f"Definition ID: {persisted.definition_id}")
    print(f"Benchmark:     {persisted.benchmark_type}")
    print(f"Workers:       {persisted.worker_bindings}")
    print(f"Evaluators:    {persisted.evaluator_bindings}")
    print(f"Instances:     {persisted.instance_count}")
    print(f"Tasks:         {persisted.task_count}")
