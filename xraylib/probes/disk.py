from __future__ import annotations

from typing import Any

from ..models import Target
from .base import Probe


class DiskProbe(Probe):
    target_types = ("disk",)

    def collect(self, target: Target) -> dict[str, Any]:
        device = "" if target.identifier == "disk" else target.identifier
        argv = ["lsblk", "--json", "--bytes", "--output-all"]
        if device:
            argv.extend(["--", device])
        data, completed = self.runner.json(argv, timeout=4)
        smart: dict[str, Any] = {}
        warnings: list[str] = []
        if device:
            if self.runner.available("smartctl"):
                smart_data, smart_result = self.runner.json(["smartctl", "--json", "--all", device], timeout=5)
                if isinstance(smart_data, dict):
                    smart = smart_data
                elif not smart_result.ok:
                    warnings.append("Additional health information requires elevated privileges or device support.")
            else:
                warnings.append("smartctl is optional and not installed.")
            if device.startswith("/dev/nvme") and self.runner.available("nvme"):
                nvme_data, _ = self.runner.json(["nvme", "smart-log", "--output-format=json", device], timeout=5)
                if isinstance(nvme_data, dict):
                    smart["nvme_smart_log"] = nvme_data
        return {
            "overview": {"device": device or "all block devices", "found": completed.ok and bool(data)},
            "devices": data.get("blockdevices", []) if isinstance(data, dict) else [],
            "health": smart,
            "warnings": warnings,
            "raw": {"source": argv, "error": completed.stderr if not completed.ok else ""},
        }

    def capabilities(self) -> list[str]:
        return ["overview", "devices", "health", "raw"]
