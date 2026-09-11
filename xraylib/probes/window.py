from __future__ import annotations

from typing import Any

from ..models import Target
from .base import Probe
from .process import ProcessProbe


class WindowProbe(Probe):
    target_types = ("window",)

    def collect(self, target: Target) -> dict[str, Any]:
        window = target.metadata.get("window", {})
        if not window:
            clients, completed = self.runner.json(["hyprctl", "clients", "-j"], timeout=1.5)
            if completed.ok and isinstance(clients, list):
                window = next((row for row in clients if str(row.get("pid")) == target.identifier), {})
        process = ProcessProbe(self.runner).collect(Target("process", target.identifier, target.display_name))
        return {
            "window": {
                "application": window.get("class", ""),
                "title": window.get("title", target.display_name),
                "address": window.get("address", ""),
                "workspace": window.get("workspace", {}),
                "geometry": {"at": window.get("at", []), "size": window.get("size", [])},
                "floating": window.get("floating", False),
                "fullscreen": window.get("fullscreen", 0),
            },
            **process,
        }

    def capabilities(self) -> list[str]:
        return ["window", "overview", "network", "files", "tree", "raw", "hud"]
