from ergon_cli.domains.examples.models import ExampleDefinition, ExampleOption

DEFAULT_LLAMA_CPP_BASE_URL = "http://localhost:8080"
DEFAULT_MINIF2F_LIMIT = 3
DEFAULT_MINIF2F_MAX_ITERATIONS = 12

MINIF2F_LOCAL_LLAMACPP = ExampleDefinition(
    slug="minif2f-local-llamacpp",
    display_name="MiniF2F local llama.cpp",
    short_description=(
        "Run three MiniF2F Lean proof tasks with a local llama.cpp OpenAI-compatible server."
    ),
    purpose=("Run three MiniF2F Lean proof tasks with local llama.cpp and an E2B Lean sandbox."),
    script_path="examples/getting_started/01_minif2f_local_llamacpp/run.py",
    prerequisites=(
        "E2B_API_KEY is set for Lean sandbox creation.",
        "A llama.cpp OpenAI-compatible server is reachable at /v1/models.",
        "Example template: llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 8080",
    ),
    options=(
        ExampleOption(
            flag="--limit",
            description="Number of MiniF2F tasks to launch.",
            default=str(DEFAULT_MINIF2F_LIMIT),
        ),
        ExampleOption(
            flag="--base-url",
            description="Base URL for the llama.cpp OpenAI-compatible server.",
            default=DEFAULT_LLAMA_CPP_BASE_URL,
        ),
        ExampleOption(
            flag="--model",
            description="Optional llama.cpp model name; encoded as #<model> on the target.",
        ),
        ExampleOption(
            flag="--model-target",
            description="Optional full Ergon model target. Overrides --base-url and --model.",
        ),
        ExampleOption(
            flag="--max-iterations",
            description="Maximum ReAct tool iterations per MiniF2F task.",
            default=str(DEFAULT_MINIF2F_MAX_ITERATIONS),
        ),
    ),
)

EXAMPLES: dict[str, ExampleDefinition] = {
    MINIF2F_LOCAL_LLAMACPP.slug: MINIF2F_LOCAL_LLAMACPP,
}


def list_examples() -> tuple[ExampleDefinition, ...]:
    return tuple(EXAMPLES[slug] for slug in sorted(EXAMPLES))


def get_example(slug: str) -> ExampleDefinition | None:
    return EXAMPLES.get(slug)
