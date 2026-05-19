"""Evidence loading for ResearchRubrics criteria."""

from pathlib import Path

from ergon_core.api.criterion import CriterionContext
from ergon_core.core.application.resources import RunResourceView
from pydantic import BaseModel


class ResourceEvidence(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    resource: RunResourceView
    text: str


async def load_researchrubrics_evidence(
    context: CriterionContext,
) -> tuple[list[ResourceEvidence], list[ResourceEvidence]]:
    resources = context.metadata.get("resources", ())
    evidence: list[ResourceEvidence] = []
    for resource in resources:
        if not isinstance(resource, RunResourceView):
            continue
        evidence.append(ResourceEvidence(resource=resource, text=_read_resource_text(resource)))

    final_outputs = [item for item in evidence if _is_final_output_resource(item.resource)]
    scratch_outputs = [item for item in evidence if not _is_final_output_resource(item.resource)]
    return final_outputs, scratch_outputs


def _read_resource_text(resource: RunResourceView) -> str:
    try:
        raw_content = Path(resource.file_path).read_bytes()
    except OSError as exc:
        return f"[Unable to read resource {resource.id}: {exc}]"
    return raw_content.decode("utf-8", errors="replace")


def _is_final_output_resource(resource: RunResourceView) -> bool:
    sandbox_origin = str(resource.metadata.get("sandbox_origin") or "")
    return resource.kind.value == "report" or sandbox_origin.startswith("/workspace/final_output/")
