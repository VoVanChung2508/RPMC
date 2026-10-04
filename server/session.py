from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from common.dto import AgentSession


@dataclass
class SessionManager:
    sessions: Dict[str, AgentSession] = field(default_factory=dict)

    def register(self, session_id: str, client_id: str, role: str = "VIEWER") -> AgentSession:
        session = AgentSession(session_id=session_id, client_id=client_id, role=role)
        self.sessions[session_id] = session
        return session

    def bind_data_channel(self, session_id: str, data_channel: str) -> Optional[AgentSession]:
        session = self.sessions.get(session_id)
        if session:
            session.data_channel = data_channel
            session.is_authenticated = True
        return session

    def get(self, session_id: str) -> Optional[AgentSession]:
        return self.sessions.get(session_id)

    def list_active(self):
        return list(self.sessions.values())
