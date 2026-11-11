"""Outbound ports: process execution and the visible output."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class OutputSinkPort(ABC):
    @abstractmethod
    def write(self, text: str) -> None:
        """Show `text` to the person running the notebook."""


class ProcessRunnerPort(ABC):
    @abstractmethod
    def run(self, argv: Sequence[str], sink: OutputSinkPort) -> tuple[int, str]:
        """Run `argv`, streaming combined stdout/stderr to `sink`; return the
        exit code and the full output."""
