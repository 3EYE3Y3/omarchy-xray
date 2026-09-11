from __future__ import annotations

import os
import platform
import socket
from typing import Any

from ..models import Target
from ..util import human_bytes, read_text
from .base import Probe


def meminfo() -> dict[str, int]:
    output: dict[str, int] = {}
    for line in read_text("/proc/meminfo").splitlines():
        key, separator, rest = line.partition(":")
        if separator:
            try:
                output[key] = int(rest.strip().split()[0]) * 1024
            except (ValueError, IndexError):
                continue
    return output


class SystemProbe(Probe):
    target_types = ("system",)

    def collect(self, target: Target) -> dict[str, Any]:
        memory = meminfo()
        uptime_raw = read_text("/proc/uptime", limit=256).split()
        uptime = float(uptime_raw[0]) if uptime_raw else 0
        load = os.getloadavg()
        filesystems = self.runner.run(["df", "--output=source,fstype,size,used,avail,pcent,target", "--block-size=1", "-x", "tmpfs", "-x", "devtmpfs"], timeout=3)
        processes = self.runner.run(["ps", "-eo", "pid=,comm=,%cpu=,%mem=,rss=", "--sort=-%cpu"], timeout=3)
        gpu = self.runner.run(["lspci", "-mm"], timeout=2)
        temperatures = self._temperatures()
        interfaces, _ = self.runner.json(["ip", "-json", "-statistics", "link", "show"], timeout=2)
        return {
            "overview": {
                "hostname": socket.gethostname(), "kernel": platform.release(), "architecture": platform.machine(),
                "uptime_seconds": uptime, "load_average": list(load), "cpu_count": os.cpu_count(),
                "memory_total": human_bytes(memory.get("MemTotal")),
                "memory_available": human_bytes(memory.get("MemAvailable")),
                "swap_total": human_bytes(memory.get("SwapTotal")),
                "swap_free": human_bytes(memory.get("SwapFree")),
            },
            "filesystems": filesystems.stdout.splitlines(),
            "top_processes": processes.stdout.splitlines()[:16],
            "gpu": [line for line in gpu.stdout.splitlines() if "VGA" in line or "Display" in line or "3D controller" in line],
            "temperatures": temperatures,
            "network_interfaces": interfaces if isinstance(interfaces, list) else [],
            "raw": {"meminfo": memory, "sources": ["/proc", "df", "ps", "lspci", "/sys/class/thermal", "ip"]},
        }

    @staticmethod
    def _temperatures() -> list[dict[str, Any]]:
        rows = []
        for path in sorted(os.listdir("/sys/class/thermal")) if os.path.isdir("/sys/class/thermal") else []:
            if not path.startswith("thermal_zone"):
                continue
            base = f"/sys/class/thermal/{path}"
            raw = read_text(f"{base}/temp", limit=128).strip()
            if raw.lstrip("-").isdigit():
                rows.append({"sensor": read_text(f"{base}/type", limit=128).strip() or path, "celsius": int(raw) / 1000})
        return rows

    def capabilities(self) -> list[str]:
        return ["overview", "filesystems", "top_processes", "gpu", "temperatures", "network", "raw"]
