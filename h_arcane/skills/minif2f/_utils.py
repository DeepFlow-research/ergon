"""Utility functions for Lean proof verification in VM."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from e2b_code_interpreter.code_interpreter_async import AsyncSandbox


async def ensure_lean_installed(sandbox: "AsyncSandbox") -> bool:
    """Install Lean on-demand. Returns True if installed successfully.

    TODO: For performance, consider pre-baking Lean into sandbox Docker image.
    Current approach installs fresh each sandbox (~2-5 min first run).

    Args:
        sandbox: E2B sandbox instance

    Returns:
        True if Lean is installed successfully, False otherwise
    """
    # Check if elan exists
    check_result = await sandbox.commands.run("which elan", timeout=5)
    if check_result.exit_code == 0:
        # Verify Lean is actually available
        lean_check = await sandbox.commands.run(
            "export PATH=$HOME/.elan/bin:$PATH && lean --version", timeout=10
        )
        if lean_check.exit_code == 0:
            return True

    # Install elan (Lean version manager)
    install_result = await sandbox.commands.run(
        "curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y",
        timeout=120,
    )
    if install_result.exit_code != 0:
        return False

    # Install stable Lean toolchain
    toolchain_result = await sandbox.commands.run(
        "export PATH=$HOME/.elan/bin:$PATH && elan toolchain install stable",
        timeout=300,  # Can take a while
    )

    if toolchain_result.exit_code != 0:
        return False

    # Verify installation
    verify_result = await sandbox.commands.run(
        "export PATH=$HOME/.elan/bin:$PATH && lean --version", timeout=10
    )
    return verify_result.exit_code == 0


def parse_lean_output(output: str) -> tuple[list[str], list[str]]:
    """Parse Lean compiler output to extract errors and goals.

    Args:
        output: Combined stdout and stderr from Lean compiler

    Returns:
        Tuple of (errors, goals_remaining)
        - errors: List of error messages
        - goals_remaining: List of goal statements (from sorry placeholders)
    """
    errors: list[str] = []
    goals: list[str] = []

    # Split output into lines
    lines = output.split("\n")

    # Pattern for Lean errors (usually start with file:line:error:)
    error_pattern = re.compile(r"^.*:\d+:\d+:\s*(error|warning):\s*(.+)$")

    # Pattern for goals (usually contain ⊢ symbol)
    goal_pattern = re.compile(r"⊢\s*(.+)$")

    current_error: list[str] = []
    in_error = False

    for line in lines:
        line = line.strip()

        # Check for error/warning
        error_match = error_pattern.match(line)
        if error_match:
            if current_error:
                errors.append("\n".join(current_error))
            current_error = [line]
            in_error = True
            continue

        # Check for goal (from sorry)
        goal_match = goal_pattern.search(line)
        if goal_match:
            goal_text = goal_match.group(1).strip()
            if goal_text:
                goals.append(goal_text)

        # Continue collecting error lines
        if in_error and line:
            current_error.append(line)
        elif in_error and not line:
            # Empty line ends error block
            if current_error:
                errors.append("\n".join(current_error))
            current_error = []
            in_error = False

    # Add final error if exists
    if current_error:
        errors.append("\n".join(current_error))

    return errors, goals

