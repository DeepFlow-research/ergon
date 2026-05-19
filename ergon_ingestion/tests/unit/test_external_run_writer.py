import math
from pathlib import Path

import numpy as np
from sqlmodel import SQLModel, Session, create_engine, select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphAnnotation, RunGraphNode
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskExecution,
)
from ergon_ingestion.models import (
    ImportSource,
    ParsedAnnotation,
    ParsedDrop,
    ParsedReducer,
    ParsedResource,
    ParsedRun,
)
from ergon_ingestion.writers.external_run_writer import ExternalRunWriter


def test_external_run_writer_persists_import_spine_without_reducer_tables(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    parsed = ParsedRun(
        source_run_id="gap-row-1",
        instance_key="gap-row-1",
        description="Imported GAP row 1",
        schema_fit_class="row-record",
        observed_fields={"t_safe": True, "tc_safe": False},
        missing_fields=["full_runtime_environment"],
        annotations=[
            ParsedAnnotation(namespace="gap.labels", payload={"t_safe": True, "tc_safe": False})
        ],
        resources=[
            ParsedResource(
                name="source-row.json",
                kind="import",
                mime_type="application/json",
                payload={"row": 1},
            )
        ],
        reducers=[
            ParsedReducer(
                name="gap.text_safety",
                kind="original",
                output={"safe": True},
                implementation_ref="ergon_ingestion.reducers.gap:text_safety",
                fields_read=["t_safe"],
                filters=["t_safe == true"],
                aggregation={"operation": "identity"},
                drops=[
                    ParsedDrop(
                        loss_class="tool_channel_erasure",
                        reason="not_read",
                        dropped_field_path="tc_safe",
                        affected_analysis="tool_call_safety",
                    )
                ],
            )
        ],
    )

    with Session(engine) as session:
        writer = ExternalRunWriter(
            session=session,
            source=ImportSource(dataset="gap", input_path=tmp_path, batch_id="paper-rq1-v1"),
            blob_root=tmp_path / "blobs",
        )
        result = writer.write_run(parsed)
        session.commit()

        assert result.run_id is not None
        definition = session.exec(select(ExperimentDefinition)).one()
        assert definition.benchmark_type == "imported:gap"
        assert definition.metadata_json["import_batch_id"] == "paper-rq1-v1"
        assert session.exec(select(RunRecord)).one().instance_key == "gap-row-1"
        assert session.exec(select(RunGraphNode)).one().task_slug == "imported-root"
        assert (
            session.exec(select(RunTaskExecution)).one().output_json["source_run_id"] == "gap-row-1"
        )
        assert session.exec(select(RunGraphAnnotation)).one().namespace == "gap.labels"
        assert session.exec(select(RunResource)).one().name == "source-row.json"


def test_external_run_writer_sanitizes_non_finite_json_values(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    parsed = ParsedRun(
        source_run_id="gap-row-nan",
        instance_key="gap-row-nan",
        description="Imported GAP row with NaN",
        schema_fit_class="row-record",
        observed_fields={"thinking_budget": math.nan, "nested": {"temperature": math.inf}},
        resources=[
            ParsedResource(
                name="source-row.json",
                kind="import",
                mime_type="application/json",
                payload={"thinking_budget": math.nan},
            )
        ],
    )

    with Session(engine) as session:
        writer = ExternalRunWriter(
            session=session,
            source=ImportSource(dataset="gap", input_path=tmp_path, batch_id="paper-rq1-v1"),
            blob_root=tmp_path / "blobs",
        )
        writer.write_run(parsed)
        session.commit()

        run = session.exec(select(RunRecord)).one()
        assert run.summary_json["observed_fields"]["thinking_budget"] is None
        assert run.summary_json["observed_fields"]["nested"]["temperature"] is None


def test_external_run_writer_materializes_numpy_array_payloads(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    parsed = ParsedRun(
        source_run_id="maestro-row-array",
        instance_key="maestro-row-array",
        description="Imported row with ndarray payload",
        schema_fit_class="trace-record",
        observed_fields={"scores": np.array([1.0, math.nan])},
        resources=[
            ParsedResource(
                name="source-row.json",
                kind="import",
                mime_type="application/json",
                payload={"scores": np.array([1.0, math.nan])},
            )
        ],
    )

    with Session(engine) as session:
        writer = ExternalRunWriter(
            session=session,
            source=ImportSource(dataset="maestro", input_path=tmp_path, batch_id="paper-rq1-v1"),
            blob_root=tmp_path / "blobs",
        )
        writer.write_run(parsed)
        session.commit()

        run = session.exec(select(RunRecord)).one()
        resource = session.exec(select(RunResource)).one()
        assert run.summary_json["observed_fields"]["scores"] == [1.0, None]
        assert resource.file_path.endswith(".json")


def test_external_run_writer_compacts_oversized_db_metadata(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    large_trace = [{"content": "x" * 4_500_000}, {"content": "y" * 4_500_000}]
    parsed = ParsedRun(
        source_run_id="agent-reward-large",
        instance_key="agent-reward-large",
        description="Imported row with oversized trace metadata",
        schema_fit_class="full-trace",
        observed_fields={"trajectory_id": "agent-reward-large", "process_trace": large_trace},
        resources=[
            ParsedResource(
                name="process-trace.json",
                kind="artifact",
                mime_type="application/json",
                payload={"process_trace": large_trace},
            )
        ],
        reducers=[
            ParsedReducer(
                name="agent_reward_bench.process_trace",
                kind="recovered",
                output={"process_trace": large_trace},
            )
        ],
    )

    with Session(engine) as session:
        writer = ExternalRunWriter(
            session=session,
            source=ImportSource(
                dataset="agent_reward_bench",
                input_path=tmp_path,
                batch_id="paper-rq1-v1",
            ),
            blob_root=tmp_path / "blobs",
        )
        writer.write_run(parsed)
        session.commit()

        run = session.exec(select(RunRecord)).one()
        resource = session.exec(select(RunResource)).one()
        assert run.summary_json["observed_fields"]["trajectory_id"] == "agent-reward-large"
        assert run.summary_json["observed_fields"]["process_trace"]["_ergon_compacted"] is True
        assert Path(resource.file_path).read_text().count("x") == 4_500_000
