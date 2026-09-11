from __future__ import annotations

from typing import Any

from ..models import Target
from .base import Probe


class PackageProbe(Probe):
    target_types = ("package",)

    def collect(self, target: Target) -> dict[str, Any]:
        name = target.identifier
        info = self.runner.run(["pacman", "-Qi", "--", name], timeout=3)
        fields: dict[str, str] = {}
        current = ""
        for line in info.stdout.splitlines():
            if line.startswith(" ") and current:
                fields[current] += " " + line.strip()
                continue
            key, separator, value = line.partition(":")
            if separator:
                current = key.strip().lower().replace(" ", "_")
                fields[current] = value.strip()
        files = self.runner.run(["pacman", "-Qlq", "--", name], timeout=4)
        paths = files.stdout.splitlines()[:5000] if files.ok else []
        return {
            "overview": fields or {"name": name, "status": "not installed"},
            "files": paths,
            "executables": [path for path in paths if path.startswith("/usr/bin/")],
            "raw": {
                "source": info.argv,
                "error": info.stderr.strip() if not info.ok else "",
                "truncated_files": len(files.stdout.splitlines()) > 5000,
            },
        }

    def capabilities(self) -> list[str]:
        return ["overview", "files", "executables", "raw"]
