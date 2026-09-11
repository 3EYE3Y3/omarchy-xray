from __future__ import annotations

import hashlib
import mimetypes
import os
import stat
import tarfile
import zipfile
from typing import Any

from ..models import Target
from ..util import human_bytes, iso_time, read_link, username
from .base import Probe


def sha256(path: str) -> tuple[str, str]:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
        return digest.hexdigest(), ""
    except (OSError, PermissionError) as exc:
        return "", str(exc)


class FileProbe(Probe):
    target_types = ("file",)

    def collect(self, target: Target) -> dict[str, Any]:
        path = target.identifier
        try:
            info = os.lstat(path)
        except (OSError, PermissionError) as exc:
            return {"error": str(exc), "path": path}
        mode = stat.filemode(info.st_mode)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        file_result = self.runner.run(["file", "--brief", "--mime-type", "--", path], timeout=2)
        if file_result.ok:
            mime = file_result.stdout.strip()
        digest, digest_error = (
            sha256(path) if stat.S_ISREG(info.st_mode) else ("", "Not a regular file")
        )
        sections: dict[str, Any] = {
            "overview": {
                "path": os.path.abspath(path),
                "filename": os.path.basename(path),
                "kind": self._kind(info.st_mode),
                "mime": mime,
                "size_bytes": info.st_size,
                "size": human_bytes(info.st_size),
                "owner": username(info.st_uid),
                "uid": info.st_uid,
                "gid": info.st_gid,
                "permissions": mode,
                "modified": iso_time(info.st_mtime),
                "accessed": iso_time(info.st_atime),
                "changed": iso_time(info.st_ctime),
                "symlink_target": read_link(path) if stat.S_ISLNK(info.st_mode) else "",
                "sha256": digest,
                "hash_error": digest_error,
            },
            "raw": {"stat_mode": info.st_mode, "inode": info.st_ino, "device": info.st_dev},
        }
        if mime.startswith("image/"):
            sections["image"] = self._image(path)
        if self._is_elf(path):
            sections["executable"] = self._executable(path)
        archive = self._archive(path)
        if archive:
            sections["archive"] = archive
        return sections

    @staticmethod
    def _kind(mode: int) -> str:
        if stat.S_ISLNK(mode):
            return "symlink"
        if stat.S_ISDIR(mode):
            return "directory"
        if stat.S_ISREG(mode):
            return "regular file"
        if stat.S_ISBLK(mode):
            return "block device"
        if stat.S_ISCHR(mode):
            return "character device"
        if stat.S_ISSOCK(mode):
            return "socket"
        if stat.S_ISFIFO(mode):
            return "pipe"
        return "unknown"

    @staticmethod
    def _is_elf(path: str) -> bool:
        try:
            with open(path, "rb") as handle:
                return handle.read(4) == b"\x7fELF"
        except OSError:
            return False

    def _image(self, path: str) -> dict[str, Any]:
        output: dict[str, Any] = {
            "privacy_warning": "Image metadata can reveal device, time, and GPS location."
        }
        identify = self.runner.run(
            ["identify", "-format", "%m %wx%h %[colorspace]", "--", path], timeout=3
        )
        if identify.ok:
            output["identity"] = identify.stdout.strip()
        exif = self.runner.run(
            ["exiftool", "-json", "-GPS*", "-Make", "-Model", "-DateTimeOriginal", "--", path],
            timeout=3,
        )
        if exif.ok:
            output["metadata"] = exif.stdout.strip()
            output["gps_present"] = "GPS" in exif.stdout
        else:
            output["optional_missing"] = "exiftool unavailable or could not read metadata"
        return output

    def _executable(self, path: str) -> dict[str, Any]:
        header = self.runner.run(["readelf", "-h", "--", path], timeout=3)
        interpreter = self.runner.run(["readelf", "-l", "--", path], timeout=3)
        libraries = self.runner.run(["ldd", path], timeout=3)
        package = self.runner.run(["pacman", "-Qo", path], timeout=2)
        return {
            "elf_header": header.stdout.strip(),
            "interpreter": next(
                (line.strip() for line in interpreter.stdout.splitlines() if "interpreter" in line),
                "",
            ),
            "linked_libraries": libraries.stdout.splitlines()[:200] if libraries.ok else [],
            "package": package.stdout.strip() if package.ok else "",
        }

    def _archive(self, path: str) -> dict[str, Any] | None:
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    names = archive.namelist()
                return {
                    "type": "zip",
                    "file_count": len(names),
                    "preview": names[:100],
                    "extracted": False,
                }
            if tarfile.is_tarfile(path):
                with tarfile.open(path, "r:*") as archive:
                    names = archive.getnames()
                return {
                    "type": "tar",
                    "file_count": len(names),
                    "preview": names[:100],
                    "extracted": False,
                }
        except (OSError, tarfile.TarError, zipfile.BadZipFile):
            return None
        return None

    def capabilities(self) -> list[str]:
        return ["overview", "image", "executable", "archive", "raw"]
