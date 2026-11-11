"""Use case: run one command and apply the exit-status policy."""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.errors import CommandFailed
from ..domain.models import CommandResult
from ..ports.inbound import RunCommandUseCase
from ..ports.outbound import OutputSinkPort, ProcessRunnerPort


class RunCommandService(RunCommandUseCase):
    def __init__(self, runner: ProcessRunnerPort, sink: OutputSinkPort) -> None:
        self._runner = runner
        self._sink = sink

    def __call__(self, argv: Sequence[str], *, check: bool = True) -> CommandResult:
        arguments = tuple(str(item) for item in argv)
        if not arguments:
            raise ValueError("argv must not be empty")
        returncode, output = self._runner.run(arguments, self._sink)
        result = CommandResult(arguments, returncode, output)
        if not result.succeeded:
            if check:
                raise CommandFailed(result)
            self._sink.write(f"[exit code {returncode}]\n")
        return result
