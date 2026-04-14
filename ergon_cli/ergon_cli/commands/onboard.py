"""``ergon onboard`` — interactive environment setup wizard."""

from argparse import Namespace
from pathlib import Path

from ergon_cli.onboarding.env_writer import write_env
from ergon_cli.onboarding.installer import install_extras
from ergon_cli.onboarding.profile import (
    BENCHMARK_DEPS,
    GPUProvider,
    LLMProvider,
    OnboardProfile,
)
from ergon_cli.onboarding.prompts import ask_secret, confirm, select_multiple, select_one


def handle_onboard(args: Namespace) -> int:  # noqa: ARG001
    print("\nWelcome to Ergon!  Let's get your environment set up.\n")

    profile = OnboardProfile()

    # --- Q1: benchmarks -------------------------------------------------------
    profile.benchmarks = select_multiple(
        "Which benchmarks do you want to run?",
        [(slug, slug) for slug in BENCHMARK_DEPS],
    )

    # --- Q2: LLM providers ----------------------------------------------------
    profile.llm_providers = [
        LLMProvider(v)
        for v in select_multiple(
            "Which LLM providers will you use?",
            [(p.value, p.value) for p in LLMProvider],
        )
    ]

    # --- Q3: RL training -------------------------------------------------------
    if confirm("Will you be doing RL training?"):
        profile.training = True
        if confirm("Do you have a local GPU?"):
            profile.gpu_provider = GPUProvider.LOCAL
        else:
            cloud_providers = [(p.value, p.value) for p in GPUProvider if p != GPUProvider.LOCAL]
            profile.gpu_provider = GPUProvider(
                select_one(
                    "Which cloud GPU provider?",
                    cloud_providers,
                )
            )

    # --- Collect keys ----------------------------------------------------------
    required = profile.required_keys()
    if required:
        print(f"\nBased on your choices I need {len(required)} API key(s):\n")
        for env_var, reason in required.items():
            print(f"  {env_var} — {reason}")
        print()
        for env_var in required:
            profile.keys[env_var] = ask_secret(env_var)

    # --- Write .env ------------------------------------------------------------
    env_path = Path.cwd() / ".env"
    write_env(profile, env_path)
    print(f"\nWrote {env_path}")

    # --- Install extras --------------------------------------------------------
    extras = profile.required_extras()
    if extras:
        print(f"\nInstalling extras: {', '.join(extras)}")
        install_extras(extras)

    print("\nSetup complete!  Run `ergon doctor` anytime to verify your environment.")
    return 0
