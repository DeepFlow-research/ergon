from argparse import Namespace
from pathlib import Path

from ergon_cli.domains.onboarding.env_writer import write_env
from ergon_cli.domains.onboarding.installer import install_extras
from ergon_cli.domains.onboarding.profile import (
    GPUProvider,
    LLMProvider,
    OnboardProfile,
    available_environment_slugs,
)
from ergon_cli.domains.onboarding.prompts import ask_secret, confirm, select_multiple, select_one


def handle_onboard(args: Namespace) -> int:
    del args
    print("\nWelcome to Ergon!  Let's get your environment set up.\n")

    profile = OnboardProfile()
    profile.environments = select_multiple(
        "Which environments do you want to run?",
        [(slug, slug) for slug in available_environment_slugs()],
    )
    profile.llm_providers = [
        LLMProvider(value)
        for value in select_multiple(
            "Which LLM providers will you use?",
            [(provider.value, provider.value) for provider in LLMProvider],
        )
    ]

    if confirm("Will you be doing RL training?"):
        profile.training = True
        if confirm("Do you have a local GPU?"):
            profile.gpu_provider = GPUProvider.LOCAL
        else:
            cloud_providers = [
                (provider.value, provider.value)
                for provider in GPUProvider
                if provider != GPUProvider.LOCAL
            ]
            profile.gpu_provider = GPUProvider(
                select_one(
                    "Which cloud GPU provider?",
                    cloud_providers,
                )
            )

    required = profile.required_keys()
    if required:
        print(f"\nBased on your choices I need {len(required)} API key(s):\n")
        for env_var, reason in required.items():
            print(f"  {env_var} — {reason}")
        print()
        for env_var in required:
            profile.keys[env_var] = ask_secret(env_var)

    env_path = Path.cwd() / ".env"
    write_env(profile, env_path)
    print(f"\nWrote {env_path}")

    extras = profile.required_extras()
    if extras:
        print(f"\nInstalling extras: {', '.join(extras)}")
        install_extras(extras)

    print("\nSetup complete!  Run `ergon doctor` anytime to verify your environment.")
    return 0
