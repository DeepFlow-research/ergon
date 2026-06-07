from uuid import uuid4

import pytest

from ergon_cli.main import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["experiment", "persist", "path/to/experiment.py"],
        ["experiment", "submit", str(uuid4())],
        ["experiment", "submit", str(uuid4()), "--k", "32"],
    ],
)
def test_cli_does_not_offer_generic_experiment_submit_or_persist(argv) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(argv)
