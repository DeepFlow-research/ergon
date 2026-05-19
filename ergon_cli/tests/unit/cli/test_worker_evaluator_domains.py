from argparse import Namespace

from ergon_cli.domains.evaluators.commands import handle_evaluator
from ergon_cli.domains.workers.commands import handle_worker
from ergon_cli.shared import exit_codes


def test_worker_missing_action_returns_usage_error(capsys) -> None:
    rc = handle_worker(Namespace(worker_action=None))

    assert rc == exit_codes.USAGE
    assert "Usage: ergon worker list" in capsys.readouterr().out


def test_evaluator_missing_action_returns_usage_error(capsys) -> None:
    rc = handle_evaluator(Namespace(evaluator_action=None))

    assert rc == exit_codes.USAGE
    assert "Usage: ergon evaluator list" in capsys.readouterr().out
