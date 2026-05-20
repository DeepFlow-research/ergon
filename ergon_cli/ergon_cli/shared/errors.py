from ergon_cli.shared import exit_codes


class CliError(Exception):
    def __init__(self, message: str, *, exit_code: int = exit_codes.RUNTIME_ERROR) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class CliUsageError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=exit_codes.USAGE)


class CliNotFoundError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=exit_codes.NOT_FOUND)


class CliDependencyError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=exit_codes.RUNTIME_ERROR)
