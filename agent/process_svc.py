from __future__ import annotations

import os
from datetime import datetime, timezone

import psutil

from common.dto import ProcessInfo


class ProcessService:
    def __init__(self, allow_termination: bool = False) -> None:
        self.allow_termination = allow_termination

    def list_processes(self):
        items = []
        for proc in psutil.process_iter(["pid", "name", "exe", "username", "cpu_percent", "memory_info", "create_time", "cmdline"]):
            try:
                info = proc.info
                items.append(
                    ProcessInfo(
                        pid=int(info["pid"]),
                        name=str(info.get("name") or "unknown"),
                        command=" ".join(info.get("cmdline") or []),
                        user=str(info.get("username") or "unknown"),
                        cpu_usage_percent=float(proc.cpu_percent(interval=None)),
                        memory_bytes=int(getattr(info.get("memory_info"), "rss", 0)),
                        start_time=datetime.fromtimestamp(
                            info.get("create_time") or 0, tz=timezone.utc
                        ).isoformat(),
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return items

    def terminate_process(self, pid: int) -> bool:
        if not self.allow_termination:
            raise PermissionError("Process termination is disabled by local agent policy")
        if pid <= 4 or pid == os.getpid():
            raise PermissionError("Protected process cannot be terminated")
        try:
            proc = psutil.Process(pid)
            if proc.username() != psutil.Process().username():
                raise PermissionError("Only processes owned by the agent user may be terminated")
            proc.terminate()
            proc.wait(timeout=3)
            return True
        except psutil.TimeoutExpired:
            return False
        except psutil.NoSuchProcess:
            return False
