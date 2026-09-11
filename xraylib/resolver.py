from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .models import Target
from .runner import Runner

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$")


class ResolutionError(ValueError):
    pass


class TargetResolver:
    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or Runner()

    def focused_window(self) -> Target:
        data, completed = self.runner.json(["hyprctl", "activewindow", "-j"], timeout=1.5)
        if not completed.ok or not isinstance(data, dict) or not data.get("pid"):
            raise ResolutionError("No focused Hyprland window was found")
        title = str(data.get("title") or data.get("class") or "Focused window")
        return Target("window", str(data["pid"]), title, {"window": data})

    def resolve(self, args: list[str]) -> Target:
        if not args:
            return self.focused_window()
        kind = args[0].lower()
        if kind in {"system", "disk"} and len(args) == 1:
            return Target(kind, kind, kind.title())
        if kind in {"process", "port", "file", "service", "package", "domain", "ip", "interface", "window"}:
            if len(args) != 2:
                raise ResolutionError(f"{kind} requires exactly one target")
            return self._explicit(kind, args[1])
        if len(args) != 1:
            raise ResolutionError("Malformed target: quote names containing spaces")
        return self._implicit(args[0])

    def _explicit(self, kind: str, value: str) -> Target:
        if kind == "process":
            if value.isdigit():
                return Target("process", value, f"PID {value}")
            return self._named(value, only="process")
        if kind == "port":
            value = value.removeprefix(":")
            if not value.isdigit() or not (0 <= int(value) <= 65535):
                raise ResolutionError("Port must be an integer from 0 to 65535")
            return Target("port", value, f"Port {value}")
        if kind == "file":
            return self._path(value, require_exists=False)
        if kind == "ip":
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise ResolutionError(f"Invalid IP address: {value}") from exc
            return Target("ip", str(address), str(address))
        if kind == "domain":
            host = self._domain_from(value)
            return Target("domain", host, host, {"input": value})
        if kind == "interface":
            return Target("interface", value, value)
        if kind == "window":
            if value == "focused":
                return self.focused_window()
            if not value.isdigit():
                raise ResolutionError("Window target must be 'focused' or a PID")
            return Target("window", value, f"Window PID {value}")
        return Target(kind, value, value)

    def _implicit(self, value: str) -> Target:
        expanded = os.path.expanduser(value)
        if value.startswith(":"):
            return self._explicit("port", value)
        if os.path.lexists(expanded) or value.startswith(("/", "./", "../", "~/")):
            return self._path(value, require_exists=False)
        if value.isdigit():
            return Target("process", value, f"PID {value}")
        try:
            address = ipaddress.ip_address(value)
            return Target("ip", str(address), str(address))
        except ValueError:
            pass
        if "://" in value or DOMAIN_RE.fullmatch(value):
            host = self._domain_from(value)
            return Target("domain", host, host, {"input": value})
        if Path("/sys/class/net", value).exists():
            return Target("interface", value, value)
        return self._named(value)

    def _path(self, value: str, *, require_exists: bool) -> Target:
        path = os.path.abspath(os.path.expanduser(value))
        if require_exists and not os.path.lexists(path):
            raise ResolutionError(f"File does not exist: {path}")
        kind = "disk" if path.startswith("/dev/") else "file"
        return Target(kind, path, os.path.basename(path) or path)

    def _domain_from(self, value: str) -> str:
        parsed = urlparse(value if "://" in value else f"//{value}")
        host = (parsed.hostname or "").rstrip(".").lower()
        if not host or not DOMAIN_RE.fullmatch(host):
            raise ResolutionError(f"Invalid domain: {value}")
        return host

    def _named(self, value: str, *, only: str = "") -> Target:
        choices: list[dict[str, str]] = []
        if only in {"", "process"}:
            found = self.runner.run(["pgrep", "-x", value], timeout=1)
            if found.ok and found.stdout.strip():
                pid = found.stdout.splitlines()[0].strip()
                choices.append({"type": "process", "identifier": pid, "display_name": f"{value} (PID {pid})"})
        if only == "":
            service = self.runner.run(["systemctl", "show", f"{value}.service", "--property=LoadState", "--value"], timeout=1)
            if service.ok and service.stdout.strip() not in {"", "not-found"}:
                choices.append({"type": "service", "identifier": value, "display_name": f"{value}.service"})
            package = self.runner.run(["pacman", "-Q", value], timeout=1)
            if package.ok:
                choices.append({"type": "package", "identifier": value, "display_name": value})
        if not choices:
            raise ResolutionError(f"Could not resolve target: {value}")
        if len(choices) == 1:
            choice = choices[0]
            return Target(choice["type"], choice["identifier"], choice["display_name"])
        return Target("ambiguous", value, value, {"choices": choices})
