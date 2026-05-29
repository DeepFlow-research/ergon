"""Immutable topology + slug constants for the canonical smoke DAG.

One place. ``SmokeWorkerBase``, ``SmokeCriterionBase``, every pytest driver,
and every Playwright spec import from here. Changing this tuple is the only
way to change smoke topology.

Shape: 4-node diamond + 3-node line + 2 singletons = 9 direct children.

    source-review -> handoff-verify  -.
                  `> primary-artifact -> artifact-summary

    metadata-review -> environment-probe -> metadata-validate

    evidence-artifact         completion-marker
"""

from collections.abc import Sequence
from dataclasses import dataclass

SOURCE_REVIEW_SLUG = "source-review"
HANDOFF_VERIFY_SLUG = "handoff-verify"
PRIMARY_ARTIFACT_SLUG = "primary-artifact"
ARTIFACT_SUMMARY_SLUG = "artifact-summary"
METADATA_REVIEW_SLUG = "metadata-review"
ENV_PROBE_SLUG = "environment-probe"
METADATA_VALIDATE_SLUG = "metadata-validate"
EVIDENCE_ARTIFACT_SLUG = "evidence-artifact"
COMPLETION_MARKER_SLUG = "completion-marker"

NESTED_INSPECT_SLUG = "nested-input-review"
NESTED_VERIFY_SLUG = "nested-verification"
NESTED_LINE_SLUGS: tuple[str, ...] = (NESTED_INSPECT_SLUG, NESTED_VERIFY_SLUG)

EXPECTED_SUBTASK_SLUGS: tuple[str, ...] = (
    SOURCE_REVIEW_SLUG,
    HANDOFF_VERIFY_SLUG,
    PRIMARY_ARTIFACT_SLUG,
    ARTIFACT_SUMMARY_SLUG,
    METADATA_REVIEW_SLUG,
    ENV_PROBE_SLUG,
    METADATA_VALIDATE_SLUG,
    EVIDENCE_ARTIFACT_SLUG,
    COMPLETION_MARKER_SLUG,
)

# (slug, depends_on_slugs, description) - shape of the DAG in one place.
# Order is authoritative: ``SmokeWorkerBase.execute`` iterates this tuple
# in-order when spawning object-bound child tasks. Leaves appear before anything
# that depends on them so slug-level forward refs are avoided.
SUBTASK_GRAPH: Sequence[tuple[str, tuple[str, ...], str]] = (
    (
        SOURCE_REVIEW_SLUG,
        (),
        "Review the seeded source brief and publish the handoff JSON.",
    ),
    (
        HANDOFF_VERIFY_SLUG,
        (SOURCE_REVIEW_SLUG,),
        "Read the source-review handoff, confirm the coordination thread, and validate the resource.",
    ),
    (
        PRIMARY_ARTIFACT_SLUG,
        (SOURCE_REVIEW_SLUG,),
        "Produce the primary benchmark artifact from the reviewed source brief.",
    ),
    (
        ARTIFACT_SUMMARY_SLUG,
        (HANDOFF_VERIFY_SLUG, PRIMARY_ARTIFACT_SLUG),
        "Summarise the verified handoff and primary artifact after both parents finish.",
    ),
    (
        METADATA_REVIEW_SLUG,
        (),
        "Inspect sample metadata and record the expected smoke annotations.",
    ),
    (
        ENV_PROBE_SLUG,
        (METADATA_REVIEW_SLUG,),
        "Run the recursive environment probe and plan nested sandbox checks.",
    ),
    (
        METADATA_VALIDATE_SLUG,
        (ENV_PROBE_SLUG,),
        "Validate metadata after the recursive environment probe completes.",
    ),
    (
        EVIDENCE_ARTIFACT_SLUG,
        (),
        "Write an independent evidence artifact for resource persistence.",
    ),
    (
        COMPLETION_MARKER_SLUG,
        (),
        "Emit a final independent completion marker artifact.",
    ),
)

SEEDED_SOURCE_DOC_NAME = "smoke_source_brief.md"
SMOKE_THREAD_TOPIC = "smoke-coordination"
SMOKE_COMPLETION_THREAD_TOPIC = "smoke-completion"
HANDOFF_RESOURCE_NAME = "handoff_source_review.json"
SMOKE_OUTPUT_DIR = "/workspace/final_output"
SMOKE_WORKSPACE_DIR = "/workspace"
SMOKE_REPO_DIR = "/workspace/repo"
SMOKE_HANDOFF_PRODUCER_SLUG = SOURCE_REVIEW_SLUG
SMOKE_HANDOFF_CONSUMER_SLUG = HANDOFF_VERIFY_SLUG

EXPECTED_SMOKE_TOKEN_IDS: list[int] = [101, 202, 303]
EXPECTED_SMOKE_LOGPROBS: list[float] = [-0.10, -0.20, -0.30]
EXPECTED_SUBAGENT_INTERNAL_MARKER = "SMOKE_CHILD_INTERNAL_THINKING"
EXPECTED_PARENT_VISIBLE_CHILD_RESULT = "SMOKE_CHILD_RESULT_PARENT_VISIBLE"


@dataclass(frozen=True)
class ExpectedResourceHandoff:
    producer_slug: str
    consumer_slug: str
    resource_name: str


EXPECTED_RESOURCE_HANDOFF = ExpectedResourceHandoff(
    producer_slug=SOURCE_REVIEW_SLUG,
    consumer_slug=HANDOFF_VERIFY_SLUG,
    resource_name=HANDOFF_RESOURCE_NAME,
)
