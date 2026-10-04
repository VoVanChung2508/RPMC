from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProcessInfo:
    pid: int
    name: str
    command: str
    user: str
    cpu_usage_percent: float
    memory_bytes: int
    start_time: str


@dataclass
class FileItem:
    path: str
    name: str
    is_dir: bool
    size: int = 0
    modified: Optional[str] = None


@dataclass
class ScreenTile:
    x: int
    y: int
    width: int = 64
    height: int = 64
    hash: str = ""
    jpeg_base64: str = ""


@dataclass
class SystemInfo:
    hostname: str
    os_name: str
    cpu_count: int
    total_ram_bytes: int
    used_ram_bytes: int
    uptime_seconds: float
    cpu_percent: float


@dataclass
class AuditEntry:
    timestamp: str
    actor: str
    action: str
    result: str
    previous_hash: str
    current_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSession:
    session_id: str
    client_id: str
    control_channel: Optional[str] = None
    data_channel: Optional[str] = None
    role: str = "VIEWER"
    is_authenticated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
