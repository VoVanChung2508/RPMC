from __future__ import annotations

from common.protocol import CommandType


class CommandPolicyEnforcer:
    """Allow only the agent capabilities that have explicit implementations."""

    ALLOWED_COMMANDS = {
        CommandType.SYSTEM_INFO_REQUEST,
        CommandType.PROCESS_LIST_REQUEST,
        CommandType.PROCESS_KILL_REQUEST,
        CommandType.FILE_LIST_REQUEST,
        CommandType.FILE_DOWNLOAD_REQUEST,
        CommandType.SCREEN_START_REQUEST,
        CommandType.SCREEN_STOP_REQUEST,
    }

    def is_allowed(self, command: CommandType) -> bool:
        return command in self.ALLOWED_COMMANDS

    def validate_path(self, root: str, requested: str) -> str:
        from common.security import PathValidator

        return str(PathValidator.validate(root, requested))
