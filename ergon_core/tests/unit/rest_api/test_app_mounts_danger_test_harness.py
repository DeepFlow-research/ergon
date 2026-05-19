from ergon_core.core.infrastructure.http.app import app


def test_app_mounts_danger_test_harness_routes() -> None:
    routes = {route.path for route in app.routes}
    assert "/api/__danger__/test-harness/read/run/{run_id}/state" in routes
