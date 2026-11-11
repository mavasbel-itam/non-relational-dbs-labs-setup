"""Value objects of a command run."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    output: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0
