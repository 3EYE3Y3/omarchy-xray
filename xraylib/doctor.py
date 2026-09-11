from __future__ import annotations

import os
from typing import Any

from .runner import Runner

REQUIRED = [
    "python3",
    "omarchy",
    "omarchy-shell",
    "hyprctl",
    "ss",
    "systemctl",
    "journalctl",
    "ip",
    "lsblk",
    "pacman",
    "file",
]
OPTIONAL = [
    "lsof",
    "smartctl",
    "nvme",
    "exiftool",
    "identify",
    "readelf",
    "ldd",
    "tracepath",
    "iw",
    "whois",
]


def diagnose(runner: Runner | None = None) -> dict[str, Any]:
    command_runner = runner or Runner()
    version = command_runner.run(["omarchy", "version"], timeout=2)
    plugin_list = command_runner.run(["omarchy", "plugin", "list", "--json"], timeout=2)
    tools = {name: command_runner.available(name) for name in REQUIRED + OPTIONAL}
    omarchy_ok = version.ok
    hyprland_ok = command_runner.run(["hyprctl", "version"], timeout=2).ok
    plugin_enabled = (
        "io.github.3eye3y3.xray" in plugin_list.stdout
        and '"enabled":true' in plugin_list.stdout.replace(" ", "")
    )
    capabilities = {
        "Window inspection": hyprland_ok and tools["python3"],
        "Process inspection": os.path.isdir("/proc"),
        "Port inspection": tools["ss"],
        "File inspection": tools["file"],
        "Disk inspection": tools["lsblk"],
        "Service inspection": tools["systemctl"],
        "Package inspection": tools["pacman"],
        "Domain inspection": tools["python3"],
        "Network inspection": tools["ip"],
        "X-Ray Vision": hyprland_ok and plugin_enabled,
    }
    return {
        "omarchy": {
            "detected": omarchy_ok,
            "version": version.stdout.strip(),
            "plugin_api": "manifest schema 1",
        },
        "hyprland": hyprland_ok,
        "proc": os.path.isdir("/proc"),
        "sys": os.path.isdir("/sys"),
        "plugin_enabled": plugin_enabled,
        "tools": tools,
        "required_missing": [name for name in REQUIRED if not tools[name]],
        "optional_missing": [name for name in OPTIONAL if not tools[name]],
        "capabilities": capabilities,
    }


def format_doctor(report: dict[str, Any]) -> str:
    lines = ["X-RAY DOCTOR", ""]
    checks = [
        (
            report["omarchy"]["detected"],
            f"Omarchy detected ({report['omarchy']['version'] or 'unknown'})",
        ),
        (report["omarchy"]["detected"], "Omarchy plugin API compatible (schema 1)"),
        (report["hyprland"], "Hyprland detected"),
        (report["proc"], "/proc available"),
        (report["sys"], "/sys available"),
    ]
    checks.extend(
        (available, f"{name} available")
        for name, available in report["tools"].items()
        if name in REQUIRED
    )
    for available, label in checks:
        lines.append(f"{'✓' if available else '✗'} {label}")
    for name in OPTIONAL:
        available = report["tools"][name]
        lines.append(
            f"{'✓' if available else '○'} {name} {'available' if available else 'OPTIONAL MISSING'}"
        )
    lines.append("")
    width = max(len(name) for name in report["capabilities"])
    for name, ready in report["capabilities"].items():
        lines.append(f"{name:<{width}}  {'READY' if ready else 'UNAVAILABLE'}")
    return "\n".join(lines)
