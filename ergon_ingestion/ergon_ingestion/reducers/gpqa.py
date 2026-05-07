"""Reducer helpers for GPQA generated-output row records."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

EXTRACTED_ACCURACY_FIELDS = ["gold_answer", "extracted_answer", "correct", "passed"]
DRIVER_VARIANT_FIELDS = ["driver_mode", "extractor_mode", "generation", "extracted_answer"]


def extracted_accuracy_reducer(record: Record) -> ParsedReducer:
    """Preserve GPQA's extracted-answer correctness labels."""

    return ParsedReducer(
        name="gpqa.extracted_accuracy",
        kind="original",
        output={
            "gold_answer": record.get("gold_answer"),
            "extracted_answer": record.get("extracted_answer"),
            "correct": record.get("correct"),
            "passed": record.get("passed"),
        },
        implementation_ref="ergon_ingestion.reducers.gpqa.extracted_accuracy_reducer",
        fields_read=EXTRACTED_ACCURACY_FIELDS,
        drops=[_extraction_registry_mismatch_drop("gpqa.extracted_accuracy")],
    )


def driver_variant_reducer(record: Record) -> ParsedReducer:
    """Expose driver/extractor variant fields for near-null calibration checks."""

    return ParsedReducer(
        name="gpqa.driver_variant",
        kind="diagnostic",
        output={
            "driver_mode": record.get("driver_mode"),
            "extractor_mode": record.get("extractor_mode"),
            "generation": record.get("generation"),
            "extracted_answer": record.get("extracted_answer"),
        },
        implementation_ref="ergon_ingestion.reducers.gpqa.driver_variant_reducer",
        fields_read=DRIVER_VARIANT_FIELDS,
        drops=[_extraction_registry_mismatch_drop("gpqa.driver_variant")],
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [extracted_accuracy_reducer(record), driver_variant_reducer(record)]


def _extraction_registry_mismatch_drop(affected_analysis: str) -> ParsedDrop:
    return ParsedDrop(
        loss_class="calibration_caveat",
        reason="extraction_registry_mismatch_caveat",
        dropped_field_path="extraction.registry_match",
        affected_analysis=affected_analysis,
        declaration_kind="source_missing",
        evidence={
            "note": "GPQA rows preserve generated and extracted answers, but not a resolved "
            "extractor-vs-registry equivalence proof.",
        },
    )
