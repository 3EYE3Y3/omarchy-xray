from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from typing import Any

from ..models import Target
from ..util import call_with_timeout, resolve_addresses
from .base import Probe


def tls_summary(host: str, timeout: float = 3.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as connection:
            with context.wrap_socket(connection, server_hostname=host) as secured:
                certificate = secured.getpeercert()
                issuer = dict(item[0] for item in certificate.get("issuer", []))
                subject = dict(item[0] for item in certificate.get("subject", []))
                return {
                    "available": True,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "issuer": issuer,
                    "subject": subject,
                    "expires": certificate.get("notAfter", ""),
                    "valid": True,
                    "protocol": secured.version(),
                }
    except (OSError, ssl.SSLError) as exc:
        return {"available": False, "error": str(exc), "valid": False}


class DomainProbe(Probe):
    target_types = ("domain",)

    def collect(self, target: Target) -> dict[str, Any]:
        host = target.identifier
        addresses, dns_error = resolve_addresses(host, timeout=2)
        route = (
            self.runner.run(["ip", "route", "get", addresses[0]], timeout=2) if addresses else None
        )
        traceroute = (
            self.runner.run(["tracepath", "-n", "-m", "5", host], timeout=5)
            if self.runner.available("tracepath")
            else None
        )
        return {
            "overview": {
                "domain": host,
                "resolved": bool(addresses),
                "https_url": f"https://{host}",
            },
            "dns": {
                "a": [value for value in addresses if ":" not in value],
                "aaaa": [value for value in addresses if ":" in value],
                "error": dns_error,
            },
            "tls": tls_summary(host),
            "route": route.stdout.strip() if route and route.ok else "",
            "trace": traceroute.stdout.splitlines() if traceroute and traceroute.ok else [],
            "raw": {
                "network_requested": True,
                "timeouts_seconds": {"dns": 2, "tls": 3, "trace": 5},
            },
        }

    def capabilities(self) -> list[str]:
        return ["overview", "dns", "tls", "route", "trace", "raw"]


class IpProbe(Probe):
    target_types = ("ip",)

    def collect(self, target: Target) -> dict[str, Any]:
        address = ipaddress.ip_address(target.identifier)
        ping_flag = "-6" if address.version == 6 else "-4"
        ping = self.runner.run(
            ["ping", ping_flag, "-n", "-c", "1", "-W", "2", str(address)], timeout=3
        )
        route = self.runner.run(["ip", "route", "get", str(address)], timeout=2)
        reverse, reverse_ok = call_with_timeout(socket.gethostbyaddr, str(address), timeout=2)
        neighbour = self.runner.run(["ip", "neighbour", "show", "to", str(address)], timeout=2)
        return {
            "overview": {
                "address": str(address),
                "version": address.version,
                "private": address.is_private,
                "loopback": address.is_loopback,
                "link_local": address.is_link_local,
                "multicast": address.is_multicast,
                "global": address.is_global,
            },
            "reachability": {
                "reachable": ping.ok,
                "summary": ping.stdout.splitlines()[-1] if ping.stdout else ping.stderr.strip(),
            },
            "reverse_dns": reverse[0] if reverse_ok else "",
            "route": route.stdout.strip() if route.ok else route.stderr.strip(),
            "neighbour": neighbour.stdout.strip() if neighbour.ok else "",
            "raw": {
                "network_requested": True,
                "timeouts_seconds": {"ping": 3, "dns": 2, "route": 2},
            },
        }

    def capabilities(self) -> list[str]:
        return ["overview", "reachability", "reverse_dns", "route", "neighbour", "raw"]
