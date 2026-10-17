from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExamStatus(str, Enum):
    WAITING = "WAITING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"


class StudentStatus(str, Enum):
    CONNECTED = "CONNECTED"
    IN_PROGRESS = "IN_PROGRESS"
    WARNED = "WARNED"
    LOCKED = "LOCKED"
    SUBMITTED = "SUBMITTED"
    DISCONNECTED = "DISCONNECTED"


class ViolationType(str, Enum):
    TAB_SWITCH = "TAB_SWITCH"
    BLUR = "BLUR"
    EXIT_FULLSCREEN = "EXIT_FULLSCREEN"
    DEVTOOLS_ATTEMPT = "DEVTOOLS_ATTEMPT"
    KEY_SHORTCUT_BLOCK = "KEY_SHORTCUT_BLOCK"
    MANUAL_PENALTY = "MANUAL_PENALTY"


@dataclass
class ExamConfig:
    initial_score: float = 10.0
    penalty_per_violation: float = 1.0
    max_violations: int = 3
    duration_minutes: int = 45
    status: ExamStatus = ExamStatus.IN_PROGRESS
    exam_title: str = "ĐỀ THI MÔN LẬP TRÌNH MẠNG (LAN PROCTORING)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_score": self.initial_score,
            "penalty_per_violation": self.penalty_per_violation,
            "max_violations": self.max_violations,
            "duration_minutes": self.duration_minutes,
            "status": self.status.value,
            "exam_title": self.exam_title,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExamConfig:
        return cls(
            initial_score=float(data.get("initial_score", 10.0)),
            penalty_per_violation=float(data.get("penalty_per_violation", 1.0)),
            max_violations=int(data.get("max_violations", 3)),
            duration_minutes=int(data.get("duration_minutes", 45)),
            status=ExamStatus(data.get("status", ExamStatus.IN_PROGRESS.value)),
            exam_title=str(data.get("exam_title", "ĐỀ THI MÔN LẬP TRÌNH MẠNG")),
        )


@dataclass
class ViolationRecord:
    event_type: str
    timestamp: float
    detail: str
    deduction: float
    remaining_score: float
    student_id: str
    manual: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StudentSession:
    student_id: str
    name: str
    ip_address: str
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    score: float = 10.0
    violations: List[ViolationRecord] = field(default_factory=list)
    status: StudentStatus = StudentStatus.CONNECTED
    warning_message: Optional[str] = None
    answers: Dict[str, Any] = field(default_factory=dict)
    submitted_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "ip_address": self.ip_address,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "score": round(self.score, 2),
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "status": self.status.value,
            "warning_message": self.warning_message,
            "submitted_at": self.submitted_at,
        }
