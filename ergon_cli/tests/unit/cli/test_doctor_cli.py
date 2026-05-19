import pytest

from ergon_cli.main import build_parser


def test_doctor_verbose_flag_is_not_parsed() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["doctor", "--verbose"])

    assert exc_info.value.code == 2
