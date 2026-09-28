"""Manager Agent Gym on Ergon: an LLM manager coordinating a simulated team.

Build a sample per episode with ``make_manager_gym_sample`` and submit it through
``Environment.from_records``; see ``examples/manager_gym`` and
``docs/architecture/09_manager_gym.md``.
"""

from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile
from ergon_builtins.benchmarks.manager_gym.manager import MAGManagerWorker
from ergon_builtins.benchmarks.manager_gym.rubric import MAGRubric
from ergon_builtins.benchmarks.manager_gym.sample import (
    make_manager_gym_sample,
    make_snapshot_reevaluation_sample,
)
from ergon_builtins.benchmarks.manager_gym.state import (
    BENCHMARK_VERSION,
    EpisodeConfig,
    EpisodeState,
)
from ergon_builtins.benchmarks.manager_gym.upstream import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.workers import (
    MAGHumanWorker,
    MAGStakeholderWorker,
    MAGWorkWorker,
)

__all__ = [
    "BENCHMARK_VERSION",
    "SCENARIOS",
    "EpisodeConfig",
    "EpisodeState",
    "InferenceProfile",
    "MAGHumanWorker",
    "MAGManagerWorker",
    "MAGRubric",
    "MAGStakeholderWorker",
    "MAGWorkWorker",
    "make_manager_gym_sample",
    "make_snapshot_reevaluation_sample",
]
