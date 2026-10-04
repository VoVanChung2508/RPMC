from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


class RBACEnforcer:
    def __init__(self) -> None:
        self._permissions = {
            Role.VIEWER: {"read"},
            Role.OPERATOR: {"read", "download", "screen"},
            Role.ADMIN: {"read", "download", "screen", "terminate"},
        }

    def can(self, role: Role | str, action: str) -> bool:
        try:
            normalized = Role(role) if isinstance(role, str) else role
        except ValueError:
            return False
        return action in self._permissions.get(normalized, set())
