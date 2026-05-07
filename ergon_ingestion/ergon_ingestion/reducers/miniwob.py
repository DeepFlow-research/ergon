"""Reducers for MiniWoB++ conditional web/UI traces."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

SUCCESS_FIELDS = ["success", "reward", "outcome"]
ACTION_PATH_FIELDS = ["actions", "instruction", "utterance"]


def success_reducer(record: Record) -> ParsedReducer:
    """Preserve source reward and success labels without regrading."""

    return ParsedReducer(
        name="miniwob.success",
        kind="original",
        output={
            "success": record.get("success"),
            "reward": record.get("reward"),
            "outcome": record.get("outcome"),
        },
        implementation_ref="ergon_ingestion.reducers.miniwob.success_reducer",
        fields_read=SUCCESS_FIELDS,
        drops=_ui_artifact_caveats("miniwob.success"),
    )


def action_path_reducer(record: Record) -> ParsedReducer:
    """Recover compact MiniWoB++ UI action path features."""

    actions = _actions(record)
    return ParsedReducer(
        name="miniwob.action_path",
        kind="recovered",
        output={
            "instruction": _instruction(record),
            "action_count": len(actions),
            "action_names": [_action_name(action) for action in actions],
            "target_refs": [_target_ref(action) for action in actions],
            "typed_text": [text for action in actions if (text := action.get("text")) is not None],
            "key_events": [key for action in actions if (key := action.get("key")) is not None],
        },
        implementation_ref="ergon_ingestion.reducers.miniwob.action_path_reducer",
        fields_read=ACTION_PATH_FIELDS,
        drops=_ui_artifact_caveats("miniwob.action_path"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [success_reducer(record), action_path_reducer(record)]


def _actions(record: Record) -> list[Record]:
    value = record.get("actions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _instruction(record: Record) -> object:
    return record.get("instruction") or record.get("utterance")


def _action_name(action: Record) -> str:
    return str(action.get("type") or action.get("action") or action.get("name") or "unknown")


def _target_ref(action: Record) -> object:
    target = action.get("target")
    if isinstance(target, dict) and "ref" in target:
        return target.get("ref")
    return target or action.get("target_ref") or action.get("element_ref")


def _ui_artifact_caveats(affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="external_artifact_unavailable",
            reason="dom_state_is_referenced_but_not_imported_as_bytes",
            dropped_field_path="dom/state",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="external_artifact_unavailable",
            reason="screenshots_are_referenced_but_not_imported_as_bytes",
            dropped_field_path="screenshots",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="execution_environment_unavailable",
            reason="miniwob_replay_environment_is_not_available_during_import",
            dropped_field_path="replay_environment",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
    ]
