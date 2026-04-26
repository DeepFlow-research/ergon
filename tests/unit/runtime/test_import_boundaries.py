def test_telemetry_models_import_before_run_resource_api() -> None:
    from ergon_core.core.persistence.telemetry.models import RunResource

    from ergon_core.api.run_resource import RunResourceView

    assert RunResource.__tablename__ == "run_resources"
    assert RunResourceView.__name__ == "RunResourceView"
