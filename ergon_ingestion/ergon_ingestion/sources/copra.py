"""COPRA theorem-result log parser."""

from collections.abc import Iterator
from pathlib import Path

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.copra import proved_failed_reducer, realised_search_cost_reducer


class CopraLogImporter:
    """Read local COPRA theorem-result logs without registry wiring."""

    info = ImporterInfo(
        slug="copra",
        display_name="COPRA theorem-result logs",
        schema_fit_class="artifact-only",
        supported_formats=["log", "txt"],
        export_claim="conditional",
        paper_result_ids=["rq1.copra.realised_search_cost"],
        default_reducers=["copra.proved_failed", "copra.realised_search_cost"],
    )

    def validate(self, source: ImportSource) -> ValidationReport:
        if not source.input_path.exists():
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"input path does not exist: {source.input_path}"],
            )
        return ValidationReport(
            dataset=self.info.slug,
            input_path=source.input_path,
            ok=True,
            planned_runs=_planned_runs(source.input_path),
            warnings=["copra has conditional export-claim status"],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        if source.input_path.is_dir():
            for path in sorted(p for p in source.input_path.iterdir() if p.is_file()):
                yield from parsed_runs_from_copra_text(path.read_text(), source_name=path.name)
            return
        yield from parsed_runs_from_copra_text(
            source.input_path.read_text(),
            source_name=source.input_path.name,
        )


def parsed_runs_from_copra_text(text: str, *, source_name: str) -> list[ParsedRun]:
    """Parse simple key-value COPRA log blocks into theorem-attempt runs."""
    records = _parse_copra_blocks(text)
    return [
        parsed_run_from_copra_record(
            record,
            source_run_id=f"{source_name}:{idx}",
            source_name=source_name,
        )
        for idx, record in enumerate(records, start=1)
    ]


def parsed_run_from_copra_record(
    record: dict[str, object],
    *,
    source_run_id: str | None = None,
    source_name: str | None = None,
) -> ParsedRun:
    """Convert one parsed theorem attempt into a database-independent run."""
    observed = _normalise_record(record)
    theorem = str(observed.get("Theorem") or observed.get("theorem") or source_run_id or "unknown")
    run_id = source_run_id or theorem
    resource_payload = _resource_payload(observed)
    return ParsedRun(
        source_run_id=run_id,
        instance_key=theorem,
        description=f"COPRA theorem attempt {theorem}",
        schema_fit_class="artifact-only",
        observed_fields=observed,
        missing_fields=["failed_proof_states", "failed_tactic_branches"],
        annotations=[
            ParsedAnnotation(
                namespace="copra.source",
                payload={"source_name": source_name, "theorem": theorem},
            )
        ],
        resources=[
            ParsedResource(
                name="proof-or-log.txt",
                kind="artifact",
                mime_type="text/plain",
                payload=resource_payload,
            )
        ],
        reducers=[proved_failed_reducer(observed), realised_search_cost_reducer(observed)],
    )


def _planned_runs(path: Path) -> int:
    if path.is_dir():
        return sum(_planned_runs(child) for child in path.iterdir() if child.is_file())
    return len(_parse_copra_blocks(path.read_text()))


def _parse_copra_blocks(text: str) -> list[dict[str, object]]:
    blocks = _split_blocks(text)
    return [_parse_block(block) for block in blocks if block.strip()]


def _split_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _parse_block(block: str) -> dict[str, object]:
    record: dict[str, object] = {}
    active_key: str | None = None
    active_lines: list[str] = []
    for line in block.splitlines():
        key, value = _split_key_value(line)
        if key is not None:
            _flush_multiline(record, active_key, active_lines)
            active_key = key
            active_lines = [value] if value else []
            continue
        if active_key is not None and line.strip():
            active_lines.append(line.strip())
    _flush_multiline(record, active_key, active_lines)
    return _normalise_record(record)


def _split_key_value(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if ":" not in stripped:
        return None, ""
    key, value = stripped.split(":", 1)
    if not key.replace("_", "").replace(" ", "").isalnum():
        return None, ""
    return key.strip(), value.strip()


def _flush_multiline(
    record: dict[str, object],
    active_key: str | None,
    active_lines: list[str],
) -> None:
    if active_key is None:
        return
    raw_value = "\n".join(line for line in active_lines if line).strip()
    record[active_key] = _coerce_value(raw_value)


def _normalise_record(record: dict[str, object]) -> dict[str, object]:
    observed = dict(record)
    if "theorem" in observed and "Theorem" not in observed:
        observed["Theorem"] = observed["theorem"]
    if "search_result" in observed and "SearchResult" not in observed:
        observed["SearchResult"] = observed["search_result"]
    if "steps_used" in observed and "StepsUsed" not in observed:
        observed["StepsUsed"] = observed["steps_used"]
    if "elapsed_seconds" not in observed:
        elapsed = (
            observed.get("ElapsedTime")
            or observed.get("ElapsedSeconds")
            or observed.get("elapsed_time")
        )
        if elapsed is not None:
            observed["elapsed_seconds"] = elapsed
    if "outcome" not in observed:
        observed["outcome"] = _outcome_from_search_result(observed.get("SearchResult"))
    return observed


def _resource_payload(observed: dict[str, object]) -> str:
    for key in ("Proof", "proof", "Log", "log"):
        value = observed.get(key)
        if value is not None:
            return str(value)
    return ""


def _outcome_from_search_result(value: object) -> str:
    result = str(value).upper() if value is not None else ""
    return "proved" if result in {"SUCCESS", "PROVED"} else "failed"


def _coerce_value(value: str) -> object:
    if value == "":
        return ""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
