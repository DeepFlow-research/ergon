"""Shared helpers for lightweight dataset importers."""

from collections.abc import Iterator

from ergon_ingestion.models import ImporterInfo, ImportSource, ParsedRun, ValidationReport


class SourceUnavailableError(RuntimeError):
    """Raised when a source cannot be parsed in the current installation."""


class StubImporter:
    """Importer metadata plus conservative local-path validation.

    Source-specific modules start with this implementation so every planned
    dataset is addressable through the CLI. Parsers override ``iter_runs`` as
    each source is implemented.
    """

    def __init__(self, info: ImporterInfo) -> None:
        self.info = info

    def validate(self, source: ImportSource) -> ValidationReport:
        exists = source.input_path.exists()
        errors = [] if exists else [f"input path does not exist: {source.input_path}"]
        return ValidationReport(
            dataset=self.info.slug,
            input_path=source.input_path,
            ok=exists,
            planned_runs=None,
            warnings=[],
            errors=errors,
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise SourceUnavailableError("; ".join(report.errors))
        raise SourceUnavailableError(
            f"{self.info.slug} parser is registered but not implemented yet"
        )
