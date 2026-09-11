from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conftest import FakeRunner

from xraylib.models import Target
from xraylib.probes.process import ProcessProbe, parse_ss, process_tree


class ProcessTests(unittest.TestCase):
    def test_network_connection_parsing_is_locale_independent(self) -> None:
        raw = 'tcp ESTAB 0 0 127.0.0.1:40222 93.184.216.34:443 users:(("odd name",pid=123,fd=9))\n'
        row = parse_ss(raw, 123)[0]
        self.assertEqual(row["process"], "odd name")
        self.assertEqual(row["remote_port"], "443")

    def test_no_network_connections(self) -> None:
        self.assertEqual(parse_ss("", 1), [])

    def test_dead_socket_without_owner(self) -> None:
        row = parse_ss("tcp TIME-WAIT 0 0 127.0.0.1:8 127.0.0.1:9\n")[0]
        self.assertIsNone(row["pid"])
        self.assertEqual(row["state"], "TIME-WAIT")

    def test_process_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid, name, ppid in [
                ("1", "init", 0),
                ("2", "child with spaces", 1),
                ("3", "odd)name", 2),
            ]:
                directory = root / pid
                directory.mkdir()
                (directory / "stat").write_text(f"{pid} ({name}) S {ppid} 0 0 0 0 0 0\n")
            tree = process_tree(root_pid=1, proc_root=temporary)
            self.assertEqual(tree["count"], 3)
            self.assertEqual(tree["roots"][0]["children"][0]["name"], "child with spaces")

    def test_huge_process_tree_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid in range(1, 31):
                directory = root / str(pid)
                directory.mkdir()
                (directory / "stat").write_text(f"{pid} (p{pid}) S 0 0 0 0 0 0 0\n")
            tree = process_tree(proc_root=temporary, limit=10)
            self.assertEqual(tree["count"], 10)
            self.assertTrue(tree["truncated"])

    def test_disappearing_process(self) -> None:
        report = ProcessProbe(FakeRunner()).collect(Target("process", "99999999", "gone"))
        self.assertIn("does not exist", report["error"])

    def test_permission_denied_file_descriptors(self) -> None:
        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            rows, error = ProcessProbe(FakeRunner())._fds(Path("/proc/1"))
        self.assertEqual(rows, [])
        self.assertIn("Permission denied", error)


if __name__ == "__main__":
    unittest.main()
