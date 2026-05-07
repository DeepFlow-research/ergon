"""Registry for named public artifact importers."""

from ergon_ingestion.models import DatasetImporter, ImporterInfo
from ergon_ingestion.sources.agent_reward_bench import AgentRewardBenchImporter
from ergon_ingestion.sources.agentharm import AgentHarmImporter
from ergon_ingestion.sources.atbench import AtBenchImporter
from ergon_ingestion.sources.bfcl import BfclImporter
from ergon_ingestion.sources.browsecomp import BrowseCompImporter
from ergon_ingestion.sources.copra import CopraLogImporter
from ergon_ingestion.sources.debate_mallm import DebateMallmImporter
from ergon_ingestion.sources.gap import GapImporter
from ergon_ingestion.sources.gpqa import GpqaImporter
from ergon_ingestion.sources.gsm8k import Gsm8kImporter
from ergon_ingestion.sources.humaneval import HumanEvalImporter
from ergon_ingestion.sources.maestro import MaestroImporter
from ergon_ingestion.sources.math import MathImporter
from ergon_ingestion.sources.miniwob import MiniWobImporter
from ergon_ingestion.sources.mle_bench import MleBenchImporter
from ergon_ingestion.sources.mmlu import MmluImporter
from ergon_ingestion.sources.openhands_swe_rebench import OpenHandsSweRebenchImporter
from ergon_ingestion.sources.stabletoolbench import StableToolBenchImporter
from ergon_ingestion.sources.swe_lancer import SweLancerImporter
from ergon_ingestion.sources.swe_smith import SweSmithImporter
from ergon_ingestion.sources.swebench_cross_harness import SwebenchCrossHarnessImporter
from ergon_ingestion.sources.tau_bench import TauBenchImporter
from ergon_ingestion.sources.tot_crosswords import TotCrosswordsImporter
from ergon_ingestion.sources.tot_game24 import TotGame24Importer
from ergon_ingestion.sources.weblinx import WebLinxImporter


REGISTERED_IMPORTERS: dict[str, DatasetImporter] = {
    "gap": GapImporter(),
    "maestro": MaestroImporter(),
    "copra": CopraLogImporter(),
    "tot_crosswords": TotCrosswordsImporter(),
    "tot_game24": TotGame24Importer(),
    "tau_bench": TauBenchImporter(),
    "agentharm": AgentHarmImporter(),
    "openhands_swe_rebench": OpenHandsSweRebenchImporter(),
    "swe_smith": SweSmithImporter(),
    "weblinx": WebLinxImporter(),
    "agent_reward_bench": AgentRewardBenchImporter(),
    "stabletoolbench": StableToolBenchImporter(),
    "atbench": AtBenchImporter(),
    "bfcl": BfclImporter(),
    "debate_mallm": DebateMallmImporter(),
    "miniwob": MiniWobImporter(),
    "math": MathImporter(),
    "gsm8k": Gsm8kImporter(),
    "humaneval": HumanEvalImporter(),
    "gpqa": GpqaImporter(),
    "mmlu": MmluImporter(),
    "swebench_cross_harness": SwebenchCrossHarnessImporter(),
    "mle_bench": MleBenchImporter(),
    "swe_lancer": SweLancerImporter(),
    "browsecomp": BrowseCompImporter(),
}


def list_importers() -> list[ImporterInfo]:
    return [importer.info for importer in REGISTERED_IMPORTERS.values()]


def get_importer(slug: str) -> DatasetImporter:
    try:
        return REGISTERED_IMPORTERS[slug]
    except KeyError as exc:
        available = ", ".join(sorted(REGISTERED_IMPORTERS))
        raise KeyError(f"unknown dataset importer {slug!r}; available: {available}") from exc
