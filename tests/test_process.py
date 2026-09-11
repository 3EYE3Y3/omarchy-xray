from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from conftest import FakeRunner

from xraylib.models import Target
from xraylib.probes.process import (
    ProcessProbe,
    invocation_pipe_peers,
    parse_ss,
    parse_status,
    proc_size_bytes,
    process_tree,
)


class ProcessTests(unittest.TestCase):
    def test_proc_memory_values_have_integer_byte_equivalents(self) -> None:
        status = parse_status("VmRSS:\t9116 kB\nVmSize:\t10676 kB\n")
        self.assertEqual(proc_size_bytes(status["VmRSS"]), 9_334_784)
        self.assertEqual(proc_size_bytes(status["VmSize"]), 10_932_224)
        self.assertIsInstance(proc_size_bytes(status["VmRSS"]), int)

    def test_malformed_proc_memory_value_has_no_numeric_equivalent(self) -> None:
        self.assertIsNone(proc_size_bytes("unknown"))

    def test_process_overview_preserves_proc_sizes_and_adds_byte_fields(self) -> None:
        status = (
            "Name:\tfixture\nState:\tS (sleeping)\nPPid:\t1\nThreads:\t1\n"
            "VmRSS:\t9116 kB\nVmSize:\t10676 kB\n"
        )

        def fixture_read(path: str, **_kwargs: object) -> str:
            return status if path.endswith("/status") else ""

        runner = FakeRunner({"ss": (0, "", ""), "ps": (0, "1.0 2.0 3", "")})
        with (
            patch("xraylib.probes.process.read_text", side_effect=fixture_read),
            patch("xraylib.probes.process.read_link", return_value=""),
            patch.object(Path, "stat", return_value=SimpleNamespace(st_uid=1000)),
            patch.object(ProcessProbe, "_fds", return_value=([], "")),
            patch("xraylib.probes.process.process_tree", return_value={}),
        ):
            overview = ProcessProbe(runner).collect(Target("process", "42", "fixture"))["overview"]

        self.assertEqual(overview["rss"], "9116 kB")
        self.assertEqual(overview["rss_bytes"], 9_334_784)
        self.assertEqual(overview["virtual_memory"], "10676 kB")
        self.assertEqual(overview["virtual_memory_bytes"], 10_932_224)
        self.assertIsInstance(overview["rss_bytes"], int)
        self.assertIsInstance(overview["virtual_memory_bytes"], int)

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

    def test_process_tree_filters_only_the_inspector_job_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = [
                (100, "bash", 1, 100),
                (200, "python3", 100, 200),
                (201, "jq", 100, 200),
                (202, "ss", 200, 200),
                (300, "python3", 100, 300),
                (301, "jq", 300, 300),
            ]
            for pid, name, ppid, process_group in fixtures:
                directory = root / str(pid)
                directory.mkdir()
                (directory / "stat").write_text(
                    f"{pid} ({name}) S {ppid} {process_group} 10 0 0 0 0\n"
                )
            tree = process_tree(
                root_pid=100,
                proc_root=temporary,
                inspector_pid=200,
                inspector_process_group=200,
            )
            children = tree["roots"][0]["children"]
            self.assertEqual([(row["pid"], row["name"]) for row in children], [(300, "python3")])
            self.assertEqual(children[0]["children"][0]["name"], "jq")
            self.assertEqual(tree["count"], 3)

    def test_process_tree_keeps_pipeline_sibling_when_group_is_not_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid, name, ppid in [(100, "bash", 1), (200, "python3", 100), (201, "jq", 100)]:
                directory = root / str(pid)
                directory.mkdir()
                (directory / "stat").write_text(f"{pid} ({name}) S {ppid} 100 10 0 0 0 0\n")
            tree = process_tree(
                root_pid=100,
                proc_root=temporary,
                inspector_pid=200,
                inspector_process_group=100,
            )
            children = tree["roots"][0]["children"]
            self.assertEqual([(row["pid"], row["name"]) for row in children], [(201, "jq")])

            filtered = process_tree(
                root_pid=100,
                proc_root=temporary,
                inspector_pid=200,
                inspector_process_group=100,
                inspector_related_pids={201},
            )
            self.assertEqual(filtered["roots"][0]["children"], [])

    def test_invocation_pipe_peer_uses_pipe_identity_not_process_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid in (100, 200, 201, 300):
                (root / str(pid) / "fd").mkdir(parents=True)
            (root / "100" / "fd" / "1").symlink_to("pipe:[999]")
            (root / "200" / "fd" / "0").symlink_to("/dev/null")
            (root / "200" / "fd" / "1").symlink_to("pipe:[123]")
            (root / "201" / "fd" / "0").symlink_to("pipe:[123]")
            (root / "300" / "fd" / "0").symlink_to("pipe:[999]")

            self.assertEqual(invocation_pipe_peers(200, 100, temporary), {201})

    def test_inherited_pipe_is_not_treated_as_invocation_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid in (100, 200, 201):
                (root / str(pid) / "fd").mkdir(parents=True)
            for pid in (100, 200, 201):
                (root / str(pid) / "fd" / "1").symlink_to("pipe:[999]")

            self.assertEqual(invocation_pipe_peers(200, 100, temporary), set())

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
