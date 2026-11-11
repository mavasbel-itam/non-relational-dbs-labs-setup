"""Output sink bound to the interpreter's current stdout.

Resolved on every write, because Jupyter replaces sys.stdout per cell.
"""

from __future__ import annotations

import sys

from ...ports.outbound import OutputSinkPort


class StdoutSink(OutputSinkPort):
    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()
