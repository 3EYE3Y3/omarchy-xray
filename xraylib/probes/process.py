from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from ..models import Target
from ..util import read_link, read_text, username
from .base import Probe


def parse_status(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key] = value.strip()
    return values


def proc_size_bytes(value: str) -> int | None:
    """Convert a Linux /proc size such as ``9116 kB`` to bytes."""
    match = re.fullmatch(r"\s*(\d+)\s+kB\s*", value)
    return int(match.group(1)) * 1024 if match else None


def parse_proc_stat(raw: str) -> dict[str, int | str] | None:
    """Parse the identity fields of /proc/<pid>/stat without splitting comm."""
    prefix, separator, suffix = raw.rpartition(") ")
    opening = prefix.find("(")
    if not separator or opening < 1:
        return None
    fields = suffix.split()
    if len(fields) < 4:
        return None
    try:
        return {
            "pid": int(prefix[:opening].strip()),
            "name": prefix[opening + 1 :],
            "state": fields[0],
            "ppid": int(fields[1]),
            "process_group": int(fields[2]),
            "session": int(fields[3]),
        }
    except ValueError:
        return None


def _pipe_links(pid: int, proc_root: str, descriptors: tuple[str, ...] | None = None) -> set[str]:
    fd_root = os.path.join(proc_root, str(pid), "fd")
    if descriptors is None:
        try:
            descriptors = tuple(entry.name for entry in os.scandir(fd_root))
        except OSError:
            return set()
    links = {read_link(os.path.join(fd_root, descriptor)) for descriptor in descriptors}
    return {link for link in links if re.fullmatch(r"pipe:\[\d+\]", link)}


def invocation_pipe_peers(
    inspector_pid: int, target_pid: int, proc_root: str = "/proc"
) -> set[int]:
    """Find direct pipeline peers through pipe endpoints unique to this invocation."""
    inspector_pipes = _pipe_links(inspector_pid, proc_root, ("0", "1"))
    invocation_pipes = inspector_pipes - _pipe_links(target_pid, proc_root)
    if not invocation_pipes:
        return set()

    try:
        entries = [entry for entry in os.scandir(proc_root) if entry.name.isdigit()]
    except OSError:
        return set()
    peers = set()
    for entry in entries:
        pid = int(entry.name)
        if pid not in {inspector_pid, target_pid} and invocation_pipes & _pipe_links(
            pid, proc_root, ("0", "1")
        ):
            peers.add(pid)
    return peers


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


def process_tree(
    *,
    root_pid: int | None = None,
    proc_root: str = "/proc",
    limit: int = 1000,
    inspector_pid: int | None = None,
    inspector_process_group: int | None = None,
    inspector_related_pids: set[int] | None = None,
) -> dict[str, Any]:
    processes: dict[int, dict[str, Any]] = {}
    process_groups: dict[int, int] = {}
    truncated = False
    try:
        entries = [entry for entry in os.scandir(proc_root) if entry.name.isdigit()]
    except OSError:
        entries = []
    for entry in entries[:limit]:
        raw = read_text(os.path.join(proc_root, entry.name, "stat"), limit=16_384)
        stat = parse_proc_stat(raw)
        if not stat:
            continue
        pid = int(stat["pid"])
        processes[pid] = {
            "pid": pid,
            "name": stat["name"],
            "state": stat["state"],
            "ppid": int(stat["ppid"]),
            "children": [],
        }
        process_groups[pid] = int(stat["process_group"])
    truncated = len(entries) > limit

    excluded: set[int] = set()
    if root_pid is not None and inspector_pid in processes and inspector_pid != root_pid:
        cursor = inspector_pid
        seen: set[int] = set()
        while cursor in processes and cursor not in seen:
            if cursor == root_pid:
                excluded.add(inspector_pid)
                excluded.update(inspector_related_pids or set())
                break
            seen.add(cursor)
            cursor = int(processes[cursor]["ppid"])

        root_process_group = process_groups.get(root_pid)
        inspector_group_matches = (
            inspector_process_group is not None
            and process_groups.get(inspector_pid) == inspector_process_group
        )
        if excluded and inspector_group_matches and root_process_group != inspector_process_group:
            excluded.update(
                pid
                for pid, process_group in process_groups.items()
                if process_group == inspector_process_group
            )

    while excluded:
        descendants = {
            pid
            for pid, row in processes.items()
            if pid not in excluded and int(row["ppid"]) in excluded
        }
        if not descendants:
            break
        excluded.update(descendants)
    for pid in excluded:
        processes.pop(pid, None)

    for row in processes.values():
        parent = processes.get(row["ppid"])
        if parent:
            parent["children"].append(row)
    roots = (
        [processes[root_pid]]
        if root_pid in processes
        else [row for row in processes.values() if row["ppid"] not in processes]
    )
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
        telemetry = self.runner.run(["ps", "-p", str(pid), "-o", "%cpu=,%mem=,etimes="], timeout=2)
        telemetry_fields = telemetry.stdout.split()
        inspector_pid = os.getpid()
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
                "rss_bytes": proc_size_bytes(status.get("VmRSS", "")),
                "virtual_memory": status.get("VmSize", ""),
                "virtual_memory_bytes": proc_size_bytes(status.get("VmSize", "")),
                "cpu_percent": float(telemetry_fields[0]) if len(telemetry_fields) >= 1 else None,
                "memory_percent": float(telemetry_fields[1])
                if len(telemetry_fields) >= 2
                else None,
            },
            "network": {
                "connections": parse_ss(sockets.stdout, pid),
                "source": sockets.argv,
                "error": sockets.stderr if not sockets.ok else "",
            },
            "files": {
                "descriptors": fd_rows,
                "count": len(fd_rows),
                "error": fd_error,
                "source": f"/proc/{pid}/fd",
            },
            "tree": process_tree(
                root_pid=pid,
                inspector_pid=inspector_pid,
                inspector_process_group=os.getpgrp(),
                inspector_related_pids=invocation_pipe_peers(inspector_pid, pid),
            ),
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
