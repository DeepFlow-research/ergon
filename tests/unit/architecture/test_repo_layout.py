from pathlib import Path


REPO_ROOT = Path(__file__).parents[3]
OTEL_COLLECTOR_TEMPLATE = "ergon_infra/ergon_infra/templates/otel-collector.yaml"


def test_observability_config_lives_with_infra_templates() -> None:
    assert not (REPO_ROOT / "config").exists()
    assert (REPO_ROOT / OTEL_COLLECTOR_TEMPLATE).is_file()
    assert (
        f"./{OTEL_COLLECTOR_TEMPLATE}:/etc/otelcol-contrib/config.yaml"
        in (REPO_ROOT / "docker-compose.yml").read_text()
    )
