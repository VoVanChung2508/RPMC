from __future__ import annotations

import os
import platform
import time

import psutil

from common.dto import SystemInfo


class SystemService:
    def get_system_info(self) -> SystemInfo:
        mem = psutil.virtual_memory()
        return SystemInfo(
            hostname=platform.node(),
            os_name=platform.platform(),
            cpu_count=os.cpu_count() or 1,
            total_ram_bytes=mem.total,
            used_ram_bytes=mem.used,
            uptime_seconds=time.time() - psutil.boot_time(),
            cpu_percent=psutil.cpu_percent(interval=None),
        )
