"""Errors raised to the notebook."""

from __future__ import annotations

from .models import CommandResult


class CommandFailed(RuntimeError):
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        tail = result.output[-4000:]
        super().__init__(f"exit code {result.returncode}: {' '.join(result.argv)}\n{tail}")
