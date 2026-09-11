from __future__ import annotations

from typing import Any

from ..models import Target
from .base import Probe


class ServiceProbe(Probe):
    target_types = ("service",)
    PROPERTIES = [
        "Id", "Description", "LoadState", "ActiveState", "SubState", "UnitFileState", "MainPID",
        "ExecStart", "FragmentPath", "ActiveEnterTimestamp", "ControlGroup", "Requires", "Wants", "After",
    ]

    def collect(self, target: Target) -> dict[str, Any]:
        unit = target.identifier if target.identifier.endswith(".service") else f"{target.identifier}.service"
        command = ["systemctl", "show", unit, "--no-pager"] + [f"--property={name}" for name in self.PROPERTIES]
        completed = self.runner.run(command, timeout=3)
        properties: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key] = value
        logs = self.runner.run(["journalctl", "--no-pager", "--quiet", "--unit", unit, "--lines", "30"], timeout=4, max_output=128_000)
        return {
            "overview": properties or {"Id": unit, "LoadState": "not-found"},
            "dependencies": {name: properties.get(name, "").split() for name in ("Requires", "Wants", "After")},
            "logs": logs.stdout.splitlines(),
            "actions": [
                {"id": "restart", "confirmation_required": True, "available": False, "reason": "Read-only acceptance candidate"},
                {"id": "stop", "confirmation_required": True, "available": False, "reason": "Read-only acceptance candidate"},
            ],
            "raw": {"source": command, "error": completed.stderr if not completed.ok else ""},
        }

    def capabilities(self) -> list[str]:
        return ["overview", "dependencies", "logs", "actions", "raw"]
