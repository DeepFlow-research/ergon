"""Compatibility wrappers for experiment CLI commands."""

from argparse import Namespace

from ergon_cli.domains.experiments.commands import (
    handle_experiment,
    handle_experiment_by_tag,
    handle_experiment_list,
    handle_experiment_show,
    handle_experiment_tags,
)
from ergon_core.core.views.experiments.models import (
    ExperimentTagDefinitionDto as ExperimentTagDefinitionRow,
)
from ergon_core.core.views.experiments.service import ExperimentReadService


class ExperimentTagService(ExperimentReadService):
    pass
