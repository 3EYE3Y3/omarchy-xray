from __future__ import annotations

import os
import unittest

from conftest import FakeRunner

from xraylib.resolver import ResolutionError, TargetResolver


class ResolverTests(unittest.TestCase):
    def test_valid_process_pid(self) -> None:
        target = TargetResolver(FakeRunner()).resolve([str(os.getpid())])
        self.assertEqual(target.type, "process")
        self.assertEqual(target.identifier, str(os.getpid()))

    def test_invalid_pid_is_still_safe_target(self) -> None:
        self.assertEqual(TargetResolver(FakeRunner()).resolve(["99999999"]).type, "process")

    def test_malformed_target(self) -> None:
        with self.assertRaisesRegex(ResolutionError, "Malformed"):
            TargetResolver(FakeRunner()).resolve(["too", "many", "parts"])

    def test_ambiguous_name(self) -> None:
        runner = FakeRunner(
            {
                "pgrep": (0, "44\n", ""),
                "systemctl": (0, "loaded\n", ""),
                "pacman": (0, "firefox 1.0\n", ""),
            }
        )
        target = TargetResolver(runner).resolve(["firefox"])
        self.assertEqual(target.type, "ambiguous")
        self.assertEqual(
            {choice["type"] for choice in target.metadata["choices"]},
            {"process", "service", "package"},
        )

    def test_no_focused_hyprland_window(self) -> None:
        with self.assertRaisesRegex(ResolutionError, "No focused"):
            TargetResolver(FakeRunner({"hyprctl": (0, "{}", "")})).resolve([])

    def test_focused_window(self) -> None:
        runner = FakeRunner(
            {"hyprctl": (0, '{"pid":42,"title":"Odd \\"Title\\"","class":"term"}', "")}
        )
        target = TargetResolver(runner).resolve([])
        self.assertEqual(
            (target.type, target.identifier, target.display_name), ("window", "42", 'Odd "Title"')
        )

    def test_invalid_ips(self) -> None:
        for value in ("999.2.3.4", "not an ip", "1.2.3"):
            with self.subTest(value=value), self.assertRaisesRegex(ResolutionError, "Invalid IP"):
                TargetResolver(FakeRunner()).resolve(["ip", value])

    def test_invalid_domain(self) -> None:
        with self.assertRaisesRegex(ResolutionError, "Invalid domain"):
            TargetResolver(FakeRunner()).resolve(["domain", "bad_domain"])

    def test_process_name_with_spaces(self) -> None:
        runner = FakeRunner({"pgrep": (0, "88\n", "")})
        target = TargetResolver(runner).resolve(["process", "Web Content"])
        self.assertEqual(target.identifier, "88")
        self.assertEqual(runner.calls[0], ["pgrep", "-x", "Web Content"])

    def test_process_name_with_shell_characters_is_argv_data(self) -> None:
        runner = FakeRunner({"pgrep": (0, "91\n", "")})
        target = TargetResolver(runner).resolve(["process", "odd;$(touch nope)"])
        self.assertEqual(target.identifier, "91")
        self.assertEqual(runner.calls[0][-1], "odd;$(touch nope)")


if __name__ == "__main__":
    unittest.main()
