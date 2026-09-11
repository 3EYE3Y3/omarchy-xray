from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class Runner:
    """Bounded direct-argv command runner. It never invokes a shell."""

    def available(self, command: str) -> bool:
        return shutil.which(command) is not None

    def run(self, argv: list[str], *, timeout: float = 3.0, max_output: int = 1_000_000) -> CommandResult:
        if not argv or not self.available(argv[0]):
            return CommandResult(argv, 127, "", f"{argv[0] if argv else 'command'} is not installed")
        try:
            environment = os.environ.copy()
            environment.update({"LANG": "C", "LC_ALL": "C", "PATH": "/usr/local/bin:/usr/bin:/bin"})
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                check=False,
                env=environment,
            )
            return CommandResult(argv, proc.returncode, proc.stdout[:max_output], proc.stderr[:max_output])
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return CommandResult(argv, 124, stdout[:max_output], stderr[:max_output], True)
        except OSError as exc:
            return CommandResult(argv, 126, "", str(exc))

    def json(self, argv: list[str], *, timeout: float = 3.0) -> tuple[Any, CommandResult]:
        completed = self.run(argv, timeout=timeout)
        if not completed.ok:
            return None, completed
        try:
            return json.loads(completed.stdout), completed
        except json.JSONDecodeError:
            return None, completed
