from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from conftest import FakeRunner

from xraylib.models import Target
from xraylib.probes.file import FileProbe


def probe(path: Path) -> dict:
    runner = FakeRunner({"file": (0, "text/plain\n", "")})
    return FileProbe(runner).collect(Target("file", str(path), path.name))


class FileTests(unittest.TestCase):
    def test_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("hello")
            link = root / "link"
            link.symlink_to(source)
            report = probe(link)
            self.assertEqual(report["overview"]["kind"], "symlink")
            self.assertEqual(report["overview"]["symlink_target"], str(source))

    def test_inaccessible_or_missing_file(self) -> None:
        report = FileProbe(FakeRunner()).collect(Target("file", "/definitely/not/here", "here"))
        self.assertIn("error", report)

    def test_archive_handling_never_extracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "safe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../../escape.txt", "never extracted")
            report = probe(path)
            self.assertEqual(report["archive"]["file_count"], 1)
            self.assertFalse(report["archive"]["extracted"])
            self.assertFalse((root.parent / "escape.txt").exists())

    def test_executable_inspection(self) -> None:
        runner = FakeRunner(
            {
                "file": (0, "application/x-executable\n", ""),
                "readelf": (0, "ELF64\ninterpreter /lib/ld.so\n", ""),
                "ldd": (0, "libc.so.6\n", ""),
                "pacman": (0, "/usr/bin/sh is owned by bash\n", ""),
            }
        )
        report = FileProbe(runner).collect(Target("file", "/usr/bin/bash", "bash"))
        self.assertIn("executable", report)
        self.assertTrue(report["overview"]["sha256"])

    def test_hash_is_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "note.txt"
            path.write_text("one")
            first = probe(path)["overview"]["sha256"]
            path.write_text("two")
            self.assertNotEqual(first, probe(path)["overview"]["sha256"])


if __name__ == "__main__":
    unittest.main()
