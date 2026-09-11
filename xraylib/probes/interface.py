from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import Target
from ..util import read_text
from .base import Probe


class InterfaceProbe(Probe):
    target_types = ("interface",)

    def collect(self, target: Target) -> dict[str, Any]:
        name = target.identifier
        base = Path("/sys/class/net") / name
        if not base.exists():
            return {"error": f"Network interface does not exist: {name}"}
        addresses, address_result = self.runner.json(["ip", "-json", "address", "show", "dev", name], timeout=2)
        routes, route_result = self.runner.json(["ip", "-json", "route", "show", "dev", name], timeout=2)
        wireless: dict[str, Any] = {}
        if self.runner.available("iw"):
            iw = self.runner.run(["iw", "dev", name, "link"], timeout=2)
            if iw.ok:
                wireless = {"details": iw.stdout.strip()}
        return {
            "overview": {
                "name": name,
                "state": read_text(str(base / "operstate"), limit=128).strip(),
                "mac": read_text(str(base / "address"), limit=128).strip(),
                "mtu": read_text(str(base / "mtu"), limit=128).strip(),
                "link_type": read_text(str(base / "type"), limit=128).strip(),
                "rx_bytes": int(read_text(str(base / "statistics/rx_bytes"), limit=128).strip() or 0),
                "tx_bytes": int(read_text(str(base / "statistics/tx_bytes"), limit=128).strip() or 0),
            },
            "addresses": addresses if isinstance(addresses, list) else [],
            "routes": routes if isinstance(routes, list) else [],
            "wireless": wireless,
            "raw": {"address_error": address_result.stderr, "route_error": route_result.stderr},
        }

    def capabilities(self) -> list[str]:
        return ["overview", "addresses", "routes", "wireless", "live"]
