from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from conftest import FakeRunner

from xraylib.models import Target
from xraylib.probes.disk import DiskProbe
from xraylib.probes.domain import DomainProbe
from xraylib.probes.package import PackageProbe
from xraylib.probes.port import PortProbe, exposure
from xraylib.probes.service import ServiceProbe
from xraylib.util import call_with_timeout


class OtherProbeTests(unittest.TestCase):
    def test_missing_optional_disk_utility(self) -> None:
        runner = FakeRunner({"lsblk": (0, '{"blockdevices":[]}', "")}, available={"lsblk"})
        report = DiskProbe(runner).collect(Target("disk", "/dev/fake", "fake"))
        self.assertTrue(any("smartctl" in warning for warning in report["warnings"]))

    def test_empty_service_result(self) -> None:
        runner = FakeRunner({"systemctl": (1, "", "not found"), "journalctl": (1, "", "")})
        report = ServiceProbe(runner).collect(Target("service", "absent", "absent"))
        self.assertEqual(report["overview"]["LoadState"], "not-found")
        self.assertFalse(report["actions"][0]["available"])

    def test_nonexistent_package(self) -> None:
        report = PackageProbe(FakeRunner({"pacman": (1, "", "package not found")})).collect(
            Target("package", "absent", "absent")
        )
        self.assertEqual(report["overview"]["status"], "not installed")

    def test_dns_timeout_helper_returns_quickly(self) -> None:
        started = time.monotonic()
        value, ok = call_with_timeout(time.sleep, 1, timeout=0.02)
        self.assertFalse(ok)
        self.assertIsInstance(value, TimeoutError)
        self.assertLess(time.monotonic() - started, 0.2)

    def test_invalid_domain_resolution_is_bounded(self) -> None:
        with (
            patch("xraylib.probes.domain.resolve_addresses", return_value=([], "timeout")),
            patch(
                "xraylib.probes.domain.tls_summary",
                return_value={"available": False, "error": "timeout"},
            ),
        ):
            report = DomainProbe(FakeRunner()).collect(
                Target("domain", "invalid.example", "invalid.example")
            )
        self.assertEqual(report["dns"]["error"], "timeout")
        self.assertFalse(report["tls"]["available"])

    def test_port_exposure_context(self) -> None:
        self.assertEqual(exposure("127.0.0.1"), "local only")
        self.assertEqual(exposure("0.0.0.0"), "all IPv4 interfaces")  # noqa: S104
        self.assertEqual(exposure("::"), "potentially all IPv6 interfaces")

    def test_port_with_no_connections(self) -> None:
        report = PortProbe(FakeRunner({"ss": (0, "", "")})).collect(
            Target("port", "65534", "Port 65534")
        )
        self.assertFalse(report["overview"]["found"])


if __name__ == "__main__":
    unittest.main()
