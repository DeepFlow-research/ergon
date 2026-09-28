"""Identifiers and paths shared across the Manager Gym adapter."""

# Upstream parity: MAG addresses the manager as this agent id in messages and prompts.
MANAGER_ACTOR_ID = "manager_agent"

# Requested E2B sandbox lifetime for every task; the whole episode, including
# grading, must finish within the manager's sandbox.
SANDBOX_TIMEOUT_SECONDS = 3600

OUTPUT_DIR = "/workspace/final_output"
SNAPSHOT_FILENAME = "manager-gym-snapshot.json"
SNAPSHOT_PATH = f"{OUTPUT_DIR}/{SNAPSHOT_FILENAME}"

PROVIDER = "ergon-builtin:manager-gym"
RUBRIC_NAME = "MAG terminal utility"
