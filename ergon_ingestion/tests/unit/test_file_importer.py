import json
from pathlib import Path

from ergon_ingestion.models import ImportSource, ImporterInfo
from ergon_ingestion.sources.generic import FileDatasetImporter


def test_file_dataset_importer_reads_jsonl_records(tmp_path: Path) -> None:
    source_path = tmp_path / "records.jsonl"
    source_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "source_run_id": "row-1",
                        "instance_key": "instance-1",
                        "description": "first row",
                        "t_safe": True,
                    }
                ),
                json.dumps({"id": "row-2", "value": 2}),
            ]
        )
    )
    importer = FileDatasetImporter(
        ImporterInfo(
            slug="fixture",
            display_name="Fixture",
            schema_fit_class="row-record",
            supported_formats=["jsonl"],
            export_claim="safe",
            default_reducers=["fixture.original"],
        )
    )

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="fixture", input_path=source_path, batch_id="test-batch")
        )
    )

    assert [run.source_run_id for run in runs] == ["row-1", "row-2"]
    assert runs[0].instance_key == "instance-1"
    assert runs[0].resources[0].name == "source-record.json"
    assert runs[0].reducers[0].name == "fixture.original"
    assert runs[1].description == "Imported fixture record row-2"


def test_file_dataset_importer_reads_each_file_in_directory(tmp_path: Path) -> None:
    (tmp_path / "a.log").write_text("SearchResult: SUCCESS")
    (tmp_path / "b.log").write_text("SearchResult: FAILURE")
    importer = FileDatasetImporter(
        ImporterInfo(
            slug="logs",
            display_name="Logs",
            schema_fit_class="artifact-only",
            supported_formats=["log"],
            export_claim="conditional",
        )
    )

    report = importer.validate(ImportSource(dataset="logs", input_path=tmp_path, batch_id="batch"))
    runs = list(importer.iter_runs(ImportSource(dataset="logs", input_path=tmp_path, batch_id="batch")))

    assert report.ok is True
    assert report.planned_runs == 2
    assert [run.source_run_id for run in runs] == ["a", "b"]
    assert runs[0].resources[0].mime_type == "text/plain"
