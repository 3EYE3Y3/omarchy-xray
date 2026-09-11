from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from ..models import Target
from ..util import human_bytes, read_link, read_text, username
from .base import Probe


def parse_status(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key] = value.strip()
    return values


def parse_ss(raw: str, pid: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pid_pattern = re.compile(rf"pid={pid}(?:,|\))") if pid is not None else None
    for line in raw.splitlines():
        if not line.strip() or (pid_pattern and not pid_pattern.search(line)):
            continue
        parts = line.split(None, 6)
        if len(parts) < 6:
            continue
        protocol, state, _recv, _send, local, remote = parts[:6]

        def split_address(value: str) -> tuple[str, str]:
            value = value.strip("[]")
            if value.startswith("[") and "]:" in value:
                host, port = value.rsplit("]:", 1)
                return host.lstrip("["), port
            host, separator, port = value.rpartition(":")
            return (host or value, port if separator else "")

        local_address, local_port = split_address(local)
        remote_address, remote_port = split_address(remote)
        owner = parts[6] if len(parts) > 6 else ""
        found_pid = re.search(r"pid=(\d+)", owner)
        found_name = re.search(r'users:\(\("([^"]+)', owner)
        rows.append(
            {
                "protocol": protocol,
                "state": state,
                "local_address": local_address,
                "local_port": local_port,
                "remote_address": remote_address,
                "remote_port": remote_port,
                "pid": int(found_pid.group(1)) if found_pid else None,
                "process": found_name.group(1) if found_name else "",
            }
        )
    return rows


def process_tree(*, root_pid: int | None = None, proc_root: str = "/proc", limit: int = 1000) -> dict[str, Any]:
    processes: dict[int, dict[str, Any]] = {}
    truncated = False
    try:
        entries = [entry for entry in os.scandir(proc_root) if entry.name.isdigit()]
    except OSError:
        entries = []
    for entry in entries[:limit]:
        raw = read_text(os.path.join(proc_root, entry.name, "stat"), limit=16_384)
        match = re.match(r"^(\d+) \((.*)\) ([A-Z]) (\d+) ", raw)
        if not match:
            continue
        pid = int(match.group(1))
        processes[pid] = {"pid": pid, "name": match.group(2), "state": match.group(3), "ppid": int(match.group(4)), "children": []}
    truncated = len(entries) > limit
    for row in processes.values():
        parent = processes.get(row["ppid"])
        if parent:
            parent["children"].append(row)
    roots = [processes[root_pid]] if root_pid in processes else [row for row in processes.values() if row["ppid"] not in processes]
    return {"roots": roots, "count": len(processes), "truncated": truncated, "limit": limit}


class ProcessProbe(Probe):
    target_types = ("process",)

    def collect(self, target: Target) -> dict[str, Any]:
        pid = int(target.identifier)
        base = Path("/proc") / str(pid)
        status_raw = read_text(str(base / "status"))
        if not status_raw:
            return {"error": f"Process {pid} does not exist or is not readable", "pid": pid}
        status = parse_status(status_raw)
        stat = (base / "stat").stat()
        uid = stat.st_uid
        cmdline = read_text(str(base / "cmdline")).replace("\x00", " ").strip()
        exe = read_link(str(base / "exe"))
        cwd = read_link(str(base / "cwd"))
        boot_time = 0.0
        for line in read_text("/proc/stat").splitlines():
            if line.startswith("btime "):
                boot_time = float(line.split()[1])
                break
        stat_fields = read_text(str(base / "stat"), limit=64_000).rsplit(") ", 1)
        start_ticks = 0
        if len(stat_fields) == 2:
            fields = stat_fields[1].split()
            if len(fields) > 19:
                start_ticks = int(fields[19])
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        start_time = boot_time + start_ticks / ticks if boot_time and start_ticks else 0
        sockets = self.runner.run(["ss", "-H", "-t", "-u", "-n", "-a", "-p"], timeout=2)
        package = self.runner.run(["pacman", "-Qo", exe], timeout=2) if exe else None
        fd_rows, fd_error = self._fds(base)
        cgroup = read_text(str(base / "cgroup"), limit=32_000).strip()
        return {
            "overview": {
                "pid": pid,
                "ppid": int(status.get("PPid", "0")),
                "name": status.get("Name", ""),
                "state": status.get("State", ""),
                "user": username(uid),
                "uid": uid,
                "executable": exe,
                "command": cmdline,
                "working_directory": cwd,
                "start_time_epoch": start_time or None,
                "runtime_seconds": max(0, time.time() - start_time) if start_time else None,
                "threads": int(status.get("Threads", "0")),
                "rss": status.get("VmRSS", ""),
                "virtual_memory": status.get("VmSize", ""),
            },
            "network": {"connections": parse_ss(sockets.stdout, pid), "source": sockets.argv, "error": sockets.stderr if not sockets.ok else ""},
            "files": {"descriptors": fd_rows, "count": len(fd_rows), "error": fd_error, "source": f"/proc/{pid}/fd"},
            "tree": process_tree(root_pid=pid),
            "associations": {
                "cgroup": cgroup,
                "systemd_units": sorted(set(re.findall(r"([A-Za-z0-9_.@-]+\.service)", cgroup))),
                "package": package.stdout.strip() if package and package.ok else "",
            },
            "raw": {"status": status_raw, "cgroup": cgroup},
        }

    def _fds(self, base: Path) -> tuple[list[dict[str, Any]], str]:
        directory = base / "fd"
        try:
            names = list(directory.iterdir())[:4096]
        except PermissionError:
            return [], "Permission denied while reading file descriptors"
        except OSError as exc:
            return [], str(exc)
        rows = []
        for item in names:
            destination = read_link(str(item))
            category = "file"
            if destination.startswith("socket:"):
                category = "socket"
            elif destination.startswith("pipe:"):
                category = "pipe"
            elif destination.startswith("/dev/"):
                category = "device"
            elif destination and os.path.isdir(destination):
                category = "directory"
            rows.append({"fd": item.name, "category": category, "path": destination})
        return rows, ""

    def capabilities(self) -> list[str]:
        return ["overview", "network", "files", "tree", "raw"]
