from __future__ import annotations

from typing import Any

from ..models import Target
from .base import Probe
from .process import parse_ss


def exposure(address: str) -> str:
    if address in {"127.0.0.1", "::1", "localhost"}:
        return "local only"
    if address in {"0.0.0.0", "*"}:
        return "all IPv4 interfaces"
    if address == "::":
        return "potentially all IPv6 interfaces"
    return "specific interface"


class PortProbe(Probe):
    target_types = ("port",)

    def collect(self, target: Target) -> dict[str, Any]:
        port = target.identifier
        completed = self.runner.run(["ss", "-H", "-t", "-u", "-n", "-a", "-p"], timeout=2)
        connections = [row for row in parse_ss(completed.stdout) if row["local_port"] == port or row["remote_port"] == port]
        for row in connections:
            row["exposure"] = exposure(row["local_address"])
            row["url"] = f"http://{row['local_address']}:{port}" if row["state"] in {"LISTEN", "UNCONN"} else ""
        return {
            "overview": {"port": int(port), "found": bool(connections), "listeners": sum(row["state"] in {"LISTEN", "UNCONN"} for row in connections)},
            "connections": connections,
            "raw": {"source": completed.argv, "error": completed.stderr if not completed.ok else ""},
        }

    def capabilities(self) -> list[str]:
        return ["overview", "connections", "raw"]
