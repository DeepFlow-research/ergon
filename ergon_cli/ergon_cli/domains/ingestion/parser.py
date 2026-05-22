import argparse

from ergon_ingestion.cli import handle_ingest


def register_ingest_parser(subparsers: argparse._SubParsersAction) -> None:
    ingest = subparsers.add_parser("ingest", help="Import public artifacts into Ergon")
    ingest.set_defaults(handler=handle_ingest)
    ingest_sub = ingest.add_subparsers(dest="ingest_action")
    ingest_sub.add_parser("list", help="List available public artifact importers")
    ingest_describe = ingest_sub.add_parser("describe", help="Describe a dataset importer")
    ingest_describe.add_argument("dataset_slug", help="Dataset importer slug")
    ingest_validate = ingest_sub.add_parser("validate", help="Validate a local source path")
    ingest_validate.add_argument("--dataset", required=True, help="Dataset importer slug")
    ingest_validate.add_argument("--input", required=True, help="Local source path")
    ingest_validate.add_argument("--strict", action="store_true", help="Fail on warnings")
    ingest_plan = ingest_sub.add_parser("plan", help="Preview an import without writing")
    ingest_plan.add_argument("--dataset", required=True, help="Dataset importer slug")
    ingest_plan.add_argument("--input", required=True, help="Local source path")
    ingest_plan.add_argument("--batch", required=True, help="Import batch id")
    ingest_run = ingest_sub.add_parser("run", help="Import a local public artifact source")
    ingest_run.add_argument("--dataset", required=True, help="Dataset importer slug")
    ingest_run.add_argument("--input", required=True, help="Local source path")
    ingest_run.add_argument("--batch", required=True, help="Import batch id")
    ingest_run.add_argument("--limit", type=int, default=None, help="Maximum records to import")
    ingest_run.add_argument("--dry-run", action="store_true", help="Parse without writing")
    ingest_run.add_argument(
        "--blob-root",
        default=".ergon/import_blobs",
        help="Directory for materialized imported resource blobs",
    )
    ingest_recipe = ingest_sub.add_parser("recipe", help="Run a named ingestion recipe")
    ingest_recipe.add_argument("recipe", help="Recipe slug")
    ingest_recipe.add_argument("--input-root", required=True, help="Prepared source root")
    ingest_recipe.add_argument("--batch", required=True, help="Import batch id")
    ingest_recipe.add_argument("--dry-run", action="store_true", help="Parse without writing")
    ingest_export = ingest_sub.add_parser("export", help="Export imported runs as sharded files")
    ingest_export.add_argument("--dataset", required=True, help="Dataset importer slug")
    ingest_export.add_argument("--batch", required=True, help="Import batch id")
    ingest_export.add_argument("--output", required=True, help="Dataset export directory")
    ingest_export.add_argument(
        "--format", choices=["parquet"], default="parquet", help="Shard format"
    )
    ingest_export.add_argument("--page-size", type=int, default=1000, help="DB page size")
    ingest_export.add_argument(
        "--shard-size-mb", type=float, default=256, help="Target shard size in MiB"
    )
    ingest_export.add_argument("--resume", action="store_true", help="Resume completed shards")
    ingest_export.add_argument(
        "--resource-policy",
        choices=["copy", "hardlink"],
        default="copy",
        help="How resource blobs are materialized into the export",
    )
    ingest_export.add_argument("--source-url", default=None, help="Source dataset URL")
    ingest_export.add_argument("--source-version-ref", default=None, help="Source dataset version")
    ingest_verify_export = ingest_sub.add_parser(
        "verify-export", help="Verify a sharded imported-run export"
    )
    ingest_verify_export.add_argument("--output", required=True, help="Dataset export directory")
