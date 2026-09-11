from __future__ import annotations

from typing import Any

from .models import Target, result
from .probes import (
    DiskProbe,
    DomainProbe,
    FileProbe,
    InterfaceProbe,
    IpProbe,
    PackageProbe,
    PortProbe,
    ProcessProbe,
    ServiceProbe,
    SystemProbe,
    WindowProbe,
)
from .resolver import TargetResolver
from .runner import Runner


class Engine:
    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or Runner()
        self.resolver = TargetResolver(self.runner)
        self.probes = [
            WindowProbe(self.runner), ProcessProbe(self.runner), PortProbe(self.runner), FileProbe(self.runner),
            DiskProbe(self.runner), ServiceProbe(self.runner), PackageProbe(self.runner), DomainProbe(self.runner),
            IpProbe(self.runner), InterfaceProbe(self.runner), SystemProbe(self.runner),
        ]

    def inspect(self, args: list[str]) -> dict[str, Any]:
        target = self.resolver.resolve(args)
        if target.type == "ambiguous":
            return result(target, {"chooser": target.metadata["choices"]}, warnings=["Target is ambiguous; select a type explicitly."])
        probe = next((candidate for candidate in self.probes if candidate.supports(target)), None)
        if probe is None:
            return result(target, {"error": f"No probe supports {target.type}"})
        sections = probe.collect(target)
        sections["capabilities"] = probe.capabilities()
        sections["actions"] = sections.get("actions", probe.actions())
        warnings = sections.pop("warnings", []) if isinstance(sections.get("warnings", []), list) else []
        return result(target, sections, warnings=warnings)


def vision_snapshot(runner: Runner | None = None) -> dict[str, Any]:
    command_runner = runner or Runner()
    clients, completed = command_runner.json(["hyprctl", "clients", "-j"], timeout=1.5)
    monitors, _ = command_runner.json(["hyprctl", "monitors", "-j"], timeout=1.5)
    monitor_map = {row.get("id"): row for row in monitors} if isinstance(monitors, list) else {}
    if not completed.ok or not isinstance(clients, list):
        return {"windows": [], "error": completed.stderr or "Hyprland clients unavailable"}
    windows = []
    for client in clients[:100]:
        if not client.get("mapped") or client.get("hidden") or not client.get("visible", True):
            continue
        pid = int(client.get("pid") or 0)
        status = {}
        try:
            with open(f"/proc/{pid}/status", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith(("VmRSS:", "Threads:")):
                        key, _, value = line.partition(":")
                        status[key] = value.strip()
        except OSError:
            pass
        monitor = monitor_map.get(client.get("monitor"), {})
        position = client.get("at", [0, 0])
        windows.append(
            {
                "pid": pid, "application": client.get("class", ""), "title": client.get("title", ""),
                "at": [position[0] - monitor.get("x", 0), position[1] - monitor.get("y", 0)],
                "size": client.get("size", [0, 0]), "monitor": client.get("monitor", 0),
                "monitor_name": monitor.get("name", ""), "memory": status.get("VmRSS", "unknown"),
                "threads": status.get("Threads", "unknown"),
            }
        )
    return {"windows": windows, "error": "", "truncated": len(clients) > 100}
