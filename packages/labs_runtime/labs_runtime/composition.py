"""Composition root: the only place the concrete adapters are named."""

from __future__ import annotations

from .adapters.outbound.process import SubprocessRunner
from .adapters.outbound.sink import StdoutSink
from .application.service import RunCommandService
from .ports.inbound import RunCommandUseCase

run_command: RunCommandUseCase = RunCommandService(SubprocessRunner(), StdoutSink())
