"""Reducers for WebLINX web interaction traces."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

SUCCESS_FIELDS = ["success", "outcome", "eval"]
ACTION_PATH_FIELDS = ["actions", "utterances", "messages"]


def success_reducer(record: Record) -> ParsedReducer:
    """Preserve source success and evaluation labels."""

    return ParsedReducer(
        name="weblinx.success",
        kind="original",
        output={
            "success": record.get("success"),
            "outcome": record.get("outcome"),
            "eval": record.get("eval"),
        },
        implementation_ref="ergon_ingestion.reducers.weblinx.success_reducer",
        fields_read=SUCCESS_FIELDS,
        drops=_browser_caveats("weblinx.success"),
    )


def action_path_reducer(record: Record) -> ParsedReducer:
    """Recover compact browser action and chat path features."""

    actions = _actions(record)
    utterances = _utterances(record)
    return ParsedReducer(
        name="weblinx.action_path",
        kind="recovered",
        output={
            "action_count": len(actions),
            "utterance_count": len(utterances),
            "action_names": [_action_name(action) for action in actions],
            "target_refs": [_target_ref(action) for action in actions],
            "utterance_roles": [_utterance_role(utterance) for utterance in utterances],
        },
        implementation_ref="ergon_ingestion.reducers.weblinx.action_path_reducer",
        fields_read=ACTION_PATH_FIELDS,
        drops=_browser_caveats("weblinx.action_path"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [success_reducer(record), action_path_reducer(record)]


def _actions(record: Record) -> list[Record]:
    value = record.get("actions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _utterances(record: Record) -> list[Record]:
    value = record.get("utterances")
    if not isinstance(value, list):
        value = record.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _action_name(action: Record) -> str:
    return str(action.get("type") or action.get("action") or action.get("name") or "unknown")


def _target_ref(action: Record) -> object:
    return action.get("target") or action.get("element") or action.get("target_ref")


def _utterance_role(utterance: Record) -> str:
    return str(utterance.get("role") or utterance.get("speaker") or "unknown")


def _browser_caveats(affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="external_artifact_unavailable",
            reason="dom_snapshots_are_referenced_but_not_imported_as_bytes",
            dropped_field_path="dom_snapshots",
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
            reason="browser_replay_environment_is_not_available_during_import",
            dropped_field_path="browser_replay_environment",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
    ]
