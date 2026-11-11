"""Inbound port: what a notebook asks for."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..domain.models import CommandResult


class RunCommandUseCase(ABC):
    @abstractmethod
    def __call__(self, argv: Sequence[str], *, check: bool = True) -> CommandResult:
        """Run `argv` without a shell, echoing its output; raise CommandFailed
        on a non-zero exit when `check` is true."""
