from __future__ import annotations

import datetime as dt
import os
import pwd
import queue
import socket
import threading
from collections.abc import Callable
from typing import Any


def read_text(path: str, *, limit: int = 256_000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except (OSError, PermissionError):
        return ""


def read_link(path: str) -> str:
    try:
        return os.readlink(path)
    except (OSError, PermissionError):
        return ""


def username(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def human_bytes(value: int | float | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(size) < 1024 or unit == "PiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PiB"


def iso_time(timestamp: float) -> str:
    return (
        dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    )


def call_with_timeout(
    function: Callable[..., Any], *args: Any, timeout: float = 2.0
) -> tuple[Any, bool]:
    """Run a potentially blocking libc resolver call in a daemon thread."""
    output: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            output.put((True, function(*args)))
        except Exception as exc:  # resolver exceptions are returned as data
            output.put((False, exc))

    threading.Thread(target=worker, daemon=True).start()
    try:
        ok, value = output.get(timeout=timeout)
        return value, ok
    except queue.Empty:
        return TimeoutError(f"operation exceeded {timeout}s"), False


def resolve_addresses(host: str, *, timeout: float = 2.0) -> tuple[list[str], str]:
    value, ok = call_with_timeout(socket.getaddrinfo, host, None, timeout=timeout)
    if not ok:
        return [], str(value)
    addresses = sorted({row[4][0] for row in value})
    return addresses, ""
