from __future__ import annotations

import json
from typing import Any

from xraylib.runner import CommandResult


class FakeRunner:
    def __init__(
        self,
        responses: dict[str, tuple[int, str, str]] | None = None,
        available: set[str] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.available_tools = available if available is not None else set(self.responses)
        self.calls: list[list[str]] = []

    def available(self, command: str) -> bool:
        return command in self.available_tools

    def run(self, argv: list[str], **kwargs: Any) -> CommandResult:
        self.calls.append(argv)
        code, stdout, stderr = self.responses.get(argv[0], (127, "", "missing"))
        return CommandResult(argv, code, stdout, stderr)

    def json(self, argv: list[str], **kwargs: Any) -> tuple[Any, CommandResult]:
        completed = self.run(argv, **kwargs)
        try:
            return json.loads(completed.stdout), completed
        except json.JSONDecodeError:
            return None, completed
