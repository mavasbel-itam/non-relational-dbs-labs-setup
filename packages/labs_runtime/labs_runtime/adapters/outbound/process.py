"""subprocess-backed runner: argument list, no shell, UTF-8 on every OS."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from ...ports.outbound import OutputSinkPort, ProcessRunnerPort


class SubprocessRunner(ProcessRunnerPort):
    def run(self, argv: Sequence[str], sink: OutputSinkPort) -> tuple[int, str]:
        lines: list[str] = []
        with subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                lines.append(line)
                sink.write(line)
        return process.returncode, "".join(lines)
