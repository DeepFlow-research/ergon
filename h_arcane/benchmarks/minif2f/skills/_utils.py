"""Utility functions for Lean proof verification in VM."""

import re


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
