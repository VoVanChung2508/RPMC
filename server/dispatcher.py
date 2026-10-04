from __future__ import annotations

from common.protocol import CommandType
from server.rbac import RBACEnforcer, Role


class CommandDispatcher:
    """Authorize console RPC operations and map them to agent protocol commands."""

    AGENT_COMMANDS = {
        "system.info": (CommandType.SYSTEM_INFO_REQUEST, "read"),
        "process.list": (CommandType.PROCESS_LIST_REQUEST, "read"),
        "process.terminate": (CommandType.PROCESS_KILL_REQUEST, "terminate"),
        "file.list": (CommandType.FILE_LIST_REQUEST, "read"),
        "file.download": (CommandType.FILE_DOWNLOAD_REQUEST, "download"),
        "screen.capture": (CommandType.SCREEN_START_REQUEST, "screen"),
        "screen.stop": (CommandType.SCREEN_STOP_REQUEST, "screen"),
    }

    def __init__(self, rbac_enforcer: RBACEnforcer | None = None) -> None:
        self.rbac = rbac_enforcer or RBACEnforcer()

    def resolve(self, role: Role, operation: str) -> tuple[CommandType, str]:
        if operation not in self.AGENT_COMMANDS:
            raise ValueError(f"Unsupported operation: {operation}")
        command, permission = self.AGENT_COMMANDS[operation]
        if not self.rbac.can(role, permission):
            raise PermissionError(f"Role {role.value} is not allowed to {operation}")
        return command, permission
