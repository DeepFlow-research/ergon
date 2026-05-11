from ergon_cli.main import build_parser


def test_ingest_subcommands_are_registered_in_main_parser() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["ingest", "list"])
    describe_args = parser.parse_args(["ingest", "describe", "gap"])
    validate_args = parser.parse_args(
        ["ingest", "validate", "--dataset", "gap", "--input", "data/gap.parquet"]
    )
    run_args = parser.parse_args(
        [
            "ingest",
            "run",
            "--dataset",
            "gap",
            "--input",
            "data/gap.parquet",
            "--batch",
            "paper-rq1-v1",
            "--dry-run",
        ]
    )
    recipe_args = parser.parse_args(
        [
            "ingest",
            "recipe",
            "paper-rq1-v1",
            "--input-root",
            "data/prepared",
            "--batch",
            "paper-rq1-v1",
        ]
    )

    assert list_args.ingest_action == "list"
    assert describe_args.ingest_action == "describe"
    assert describe_args.dataset_slug == "gap"
    assert validate_args.ingest_action == "validate"
    assert validate_args.dataset == "gap"
    assert validate_args.input == "data/gap.parquet"
    assert run_args.ingest_action == "run"
    assert run_args.batch == "paper-rq1-v1"
    assert run_args.dry_run is True
    assert recipe_args.ingest_action == "recipe"
    assert recipe_args.recipe == "paper-rq1-v1"
