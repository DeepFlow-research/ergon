from ergon_cli.domains.examples.models import ExampleDefinition, ExampleOption

DEFAULT_LLAMA_CPP_BASE_URL = "http://localhost:8080"
DEFAULT_MINIF2F_LIMIT = 3
DEFAULT_MINIF2F_MAX_ITERATIONS = 12

MINIF2F_LOCAL_LLAMACPP = ExampleDefinition(
    slug="minif2f-local-llamacpp",
    display_name="MiniF2F local llama.cpp",
    short_description=("Run three MiniF2F Lean proof tasks with a managed local llama.cpp server."),
    purpose=("Run three MiniF2F Lean proof tasks with local llama.cpp and an E2B Lean sandbox."),
    script_path="examples/getting_started/01_minif2f_local_llamacpp/submit.py",
    prerequisites=(
        "E2B_API_KEY is configured in Ergon's .env file or process environment.",
        "A local GGUF model path or Hugging Face GGUF ref is available for llama.cpp.",
        "llama-server is installed, or --llama-server-bin points to it.",
    ),
    options=(
        ExampleOption(
            flag="--base-model",
            description=(
                "Local GGUF path or Hugging Face '<repo-id>:<filename.gguf>' ref; "
                "starts a managed llama.cpp server for this run."
            ),
        ),
        ExampleOption(
            flag="--model-cache-dir",
            description="Directory for downloaded Hugging Face GGUF files.",
        ),
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
            flag="--llama-server-bin",
            description="llama.cpp server command to run with --base-model.",
            default="llama-server",
        ),
        ExampleOption(
            flag="--host",
            description="Host for the managed llama.cpp server.",
            default="127.0.0.1",
        ),
        ExampleOption(
            flag="--port",
            description="Port for the managed llama.cpp server.",
            default="8080",
        ),
        ExampleOption(
            flag="--startup-timeout",
            description="Seconds to wait for managed llama.cpp startup.",
            default="60",
        ),
        ExampleOption(
            flag="--keep-llama-server",
            description="Leave the managed llama.cpp server running after the example exits.",
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
