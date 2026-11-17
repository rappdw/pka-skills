"""Exit codes and the one exception type the CLI turns into a message."""
from __future__ import annotations

EXIT_OK = 0
EXIT_FAIL = 1        # the operation was attempted and failed
EXIT_ENV = 2         # a prerequisite is missing (python, git, FTS5)
EXIT_NOT_READY = 3   # the workspace is not in the state the command needs
EXIT_USAGE = 64      # bad arguments; nothing was touched


class ToolError(Exception):
    """An expected failure. The CLI prints the message and exits with `code`."""

    def __init__(self, message: str, code: int = EXIT_FAIL):
        super().__init__(message)
        self.message = message
        self.code = code
