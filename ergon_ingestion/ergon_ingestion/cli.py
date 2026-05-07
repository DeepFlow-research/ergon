"""Command handlers for ``ergon ingest``."""

from argparse import Namespace
from pathlib import Path

from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_ingestion.exports.models import ShardedExportConfig
from ergon_ingestion.exports.sharded import export_dataset_from_config
from ergon_ingestion.exports.verify import verify_export
from ergon_ingestion.models import ImportSource
from ergon_ingestion.registry import get_importer, list_importers
from ergon_ingestion.writers.external_run_writer import ExternalRunWriter


def handle_ingest(args: Namespace) -> int:
    if args.ingest_action == "list":
        return _handle_list()
    if args.ingest_action == "describe":
        return _handle_describe(args.dataset_slug)
    if args.ingest_action == "validate":
        return _handle_validate(args)
    if args.ingest_action == "plan":
        return _handle_validate(args)
    if args.ingest_action == "run":
        return _handle_run(args)
    if args.ingest_action == "recipe":
        return _handle_recipe(args)
    if args.ingest_action == "export":
        return _handle_export(args)
    if args.ingest_action == "verify-export":
        return _handle_verify_export(args)
    print("Usage: ergon ingest {list|describe|validate|plan|run|recipe|export|verify-export}")
    return 1


def _handle_list() -> int:
    for info in list_importers():
        print(f"{info.slug}\t{info.schema_fit_class}\t{info.export_claim}\t{info.display_name}")
    return 0


def _handle_describe(dataset_slug: str) -> int:
    info = get_importer(dataset_slug).info
    print(f"slug: {info.slug}")
    print(f"name: {info.display_name}")
    print(f"schema_fit_class: {info.schema_fit_class}")
    print(f"supported_formats: {', '.join(info.supported_formats)}")
    print(f"export_claim: {info.export_claim}")
    if info.default_reducers:
        print(f"default_reducers: {', '.join(info.default_reducers)}")
    return 0


def _source_from_args(args: Namespace) -> ImportSource:
    return ImportSource(
        dataset=args.dataset,
        input_path=Path(args.input),
        batch_id=getattr(args, "batch", "validation"),
    )


def _handle_validate(args: Namespace) -> int:
    importer = get_importer(args.dataset)
    report = importer.validate(_source_from_args(args))
    print(f"dataset: {report.dataset}")
    print(f"input: {report.input_path}")
    print(f"ok: {report.ok}")
    if report.planned_runs is not None:
        print(f"planned_runs: {report.planned_runs}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")
    return 0 if report.ok else 1


def _handle_run(args: Namespace) -> int:
    importer = get_importer(args.dataset)
    source = _source_from_args(args)
    report = importer.validate(source)
    if not report.ok:
        for error in report.errors:
            print(f"error: {error}")
        return 1
    if args.dry_run:
        count = sum(1 for _ in importer.iter_runs(source))
        print(f"dry_run: true")
        print(f"dataset: {args.dataset}")
        print(f"parsed_runs: {count}")
        return 0
    ensure_db()
    written = 0
    with get_session() as session:
        writer = ExternalRunWriter(session=session, source=source, blob_root=Path(args.blob_root))
        for parsed in importer.iter_runs(source):
            if args.limit is not None and written >= args.limit:
                break
            writer.write_run(parsed)
            written += 1
        session.commit()
    print(f"dataset: {args.dataset}")
    print(f"batch: {args.batch}")
    print(f"written_runs: {written}")
    return 0


def _handle_recipe(args: Namespace) -> int:
    print(f"recipe: {args.recipe}")
    print(f"input_root: {args.input_root}")
    print(f"batch: {args.batch}")
    if args.dry_run:
        print("dry_run: true")
    raise NotImplementedError("recipe execution will be added after single-dataset ingestion")


def _handle_export(args: Namespace) -> int:
    manifest = export_dataset_from_config(
        ShardedExportConfig(
            dataset=args.dataset,
            batch=args.batch,
            output_dir=Path(args.output),
            page_size=args.page_size,
            shard_size_mb=args.shard_size_mb,
            resume=args.resume,
            resource_policy=args.resource_policy,
            format=args.format,
            source_url=args.source_url,
            source_version_ref=args.source_version_ref,
        )
    )
    print(f"dataset: {manifest.dataset}")
    print(f"batch: {manifest.batch}")
    print(f"run_count: {manifest.run_count}")
    print(f"reducer_count: {manifest.reducer_count}")
    print(f"drop_count: {manifest.drop_count}")
    print(f"resource_count: {manifest.resource_count}")
    print(f"output: {args.output}")
    return 0


def _handle_verify_export(args: Namespace) -> int:
    try:
        result = verify_export(Path(args.output))
    except RuntimeError as exc:
        print(f"ok: false")
        print(f"error: {exc}")
        return 1
    print(f"ok: {str(result['ok']).lower()}")
    print(f"run_count: {result['run_count']}")
    print(f"reducer_count: {result['reducer_count']}")
    print(f"drop_count: {result['drop_count']}")
    print(f"resource_count: {result['resource_count']}")
    return 0
