from ergon_builtins.environments.catalog import environment_cli_metadata


def test_environment_cli_metadata_exposes_setup_templates() -> None:
    metadata = environment_cli_metadata()

    assert metadata["minif2f"].sandbox_template is not None
    assert metadata["minif2f"].supports_setup is True
    assert metadata["swebench-verified"].sandbox_template is not None


def test_environment_cli_metadata_exposes_onboarding_requirements() -> None:
    metadata = environment_cli_metadata()

    assert "E2B_API_KEY" in metadata["gdpeval"].env_keys
    assert "EXA_API_KEY" in metadata["researchrubrics"].env_keys
    assert "ergon-builtins[data]" in metadata["swebench-verified"].required_packages
