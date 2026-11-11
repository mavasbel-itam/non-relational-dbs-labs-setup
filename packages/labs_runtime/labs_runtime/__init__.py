"""Shell-free command execution for the lab notebooks.

Notebooks call `run_command(["docker", ...])` instead of IPython `!` lines. A
`!` line is handed to the operating system shell (`cmd.exe` on Windows,
`/bin/sh` elsewhere), so its quoting, globbing and pipes mean different things
on each system. An argument list reaches the program unchanged everywhere.
"""

from .composition import run_command
from .domain.errors import CommandFailed
from .domain.models import CommandResult

__all__ = ["CommandFailed", "CommandResult", "run_command"]
