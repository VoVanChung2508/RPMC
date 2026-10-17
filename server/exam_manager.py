from __future__ import annotations

import csv
import io
import json
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from common.exam_models import (
    ExamConfig,
    ExamStatus,
    StudentSession,
    StudentStatus,
    ViolationRecord,
    ViolationType,
)


class ExamManager:
    _instance: Optional[ExamManager] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ExamManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, log_path: str = "data/exam_audit.jsonl") -> None:
        self.config = ExamConfig()
        self.students: Dict[str, StudentSession] = {}
        self.subscribers: List[queue.Queue] = []
        self._state_lock = threading.RLock()
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def get_config(self) -> ExamConfig:
        with self._state_lock:
            return self.config

    def update_config(self, new_data: Dict[str, Any], actor: str = "PO") -> ExamConfig:
        with self._state_lock:
            if "initial_score" in new_data:
                self.config.initial_score = float(new_data["initial_score"])
            if "penalty_per_violation" in new_data:
                self.config.penalty_per_violation = float(new_data["penalty_per_violation"])
            if "max_violations" in new_data:
                self.config.max_violations = int(new_data["max_violations"])
            if "duration_minutes" in new_data:
                self.config.duration_minutes = int(new_data["duration_minutes"])
            if "status" in new_data:
                self.config.status = ExamStatus(new_data["status"])
            if "exam_title" in new_data:
                self.config.exam_title = str(new_data["exam_title"])

            # Recalculate scores for all students currently in progress
            for student in self.students.values():
                if student.status != StudentStatus.SUBMITTED:
                    self._recalc_student_score(student)

            self._log_audit(actor, "CONFIG_UPDATE", self.config.to_dict())
            self._broadcast({"type": "CONFIG_UPDATE", "config": self.config.to_dict()})
            return self.config

    def register_student(self, student_id: str, name: str, ip_address: str) -> StudentSession:
        with self._state_lock:
            student_id = student_id.strip().upper()
            name = name.strip() or f"Sinh viên {student_id}"

            if student_id in self.students:
                student = self.students[student_id]
                student.name = name
                student.ip_address = ip_address
                student.last_seen = time.time()
                if student.status == StudentStatus.DISCONNECTED:
                    student.status = StudentStatus.IN_PROGRESS
            else:
                student = StudentSession(
                    student_id=student_id,
                    name=name,
                    ip_address=ip_address,
                    score=self.config.initial_score,
                    status=StudentStatus.IN_PROGRESS,
                )
                self.students[student_id] = student

            self._log_audit(student_id, "STUDENT_JOIN", {"name": name, "ip": ip_address})
            self._broadcast({
                "type": "STUDENT_JOIN",
                "student": student.to_dict(),
            })
            return student

    def record_violation(
        self,
        student_id: str,
        event_type: str,
        detail: str = "",
        manual: bool = False,
        actor: str = "SYSTEM",
    ) -> Tuple[StudentSession, ViolationRecord]:
        with self._state_lock:
            student_id = student_id.strip().upper()
            if student_id not in self.students:
                self.register_student(student_id, f"Sinh viên {student_id}", "unknown")

            student = self.students[student_id]
            if student.status in (StudentStatus.LOCKED, StudentStatus.SUBMITTED):
                # Student already locked or submitted
                fake_rec = ViolationRecord(
                    event_type=event_type,
                    timestamp=time.time(),
                    detail=f"{detail} (Đã bị khóa/nộp)",
                    deduction=0.0,
                    remaining_score=student.score,
                    student_id=student_id,
                    manual=manual,
                )
                return student, fake_rec

            deduction = self.config.penalty_per_violation
            # Calculate new score
            new_score = max(0.0, self.config.initial_score - ((len(student.violations) + 1) * deduction))
            record = ViolationRecord(
                event_type=event_type,
                timestamp=time.time(),
                detail=detail,
                deduction=deduction,
                remaining_score=round(new_score, 2),
                student_id=student_id,
                manual=manual,
            )
            student.violations.append(record)
            student.score = round(new_score, 2)
            student.last_seen = time.time()

            # Check if max violations reached
            if len(student.violations) >= self.config.max_violations:
                student.status = StudentStatus.LOCKED
                student.warning_message = f"Bài thi bị KHÓA do đã vi phạm {len(student.violations)}/{self.config.max_violations} lần!"
            else:
                student.status = StudentStatus.WARNED
                student.warning_message = f"CẢNH BÁO VI PHẠM: Bạn vừa bị trừ {deduction} điểm vì {detail}. Số lần vi phạm: {len(student.violations)}/{self.config.max_violations}."

            self._log_audit(actor, "VIOLATION_RECORDED", {
                "student_id": student_id,
                "violation": record.to_dict(),
                "status": student.status.value,
            })
            self._broadcast({
                "type": "VIOLATION_ALERT",
                "student": student.to_dict(),
                "violation": record.to_dict(),
            })
            return student, record

    def send_warning(self, student_id: str, message: str, actor: str = "SM") -> StudentSession:
        with self._state_lock:
            student_id = student_id.strip().upper()
            if student_id not in self.students:
                raise KeyError(f"Student {student_id} not found")

            student = self.students[student_id]
            student.warning_message = message
            student.status = StudentStatus.WARNED
            student.last_seen = time.time()

            self._log_audit(actor, "SEND_WARNING", {"student_id": student_id, "message": message})
            self._broadcast({
                "type": "DIRECT_WARNING",
                "student_id": student_id,
                "message": message,
                "actor": actor,
            })
            return student

    def lock_student(self, student_id: str, reason: str = "Giám thị cưỡng chế khóa", actor: str = "SM") -> StudentSession:
        with self._state_lock:
            student_id = student_id.strip().upper()
            if student_id not in self.students:
                raise KeyError(f"Student {student_id} not found")

            student = self.students[student_id]
            student.status = StudentStatus.LOCKED
            student.warning_message = f"BÀI THI ĐÃ BỊ KHÓA: {reason}"
            student.last_seen = time.time()

            self._log_audit(actor, "FORCE_LOCK", {"student_id": student_id, "reason": reason})
            self._broadcast({
                "type": "STUDENT_LOCKED",
                "student": student.to_dict(),
                "reason": reason,
            })
            return student

    def submit_exam(self, student_id: str, answers: Dict[str, Any]) -> StudentSession:
        with self._state_lock:
            student_id = student_id.strip().upper()
            if student_id not in self.students:
                raise KeyError(f"Student {student_id} not found")

            student = self.students[student_id]
            if student.status != StudentStatus.LOCKED:
                student.status = StudentStatus.SUBMITTED
            student.answers = answers
            student.submitted_at = time.time()
            student.last_seen = time.time()

            self._log_audit(student_id, "EXAM_SUBMIT", {"score": student.score, "answers_count": len(answers)})
            self._broadcast({
                "type": "EXAM_SUBMIT",
                "student": student.to_dict(),
            })
            return student

    def get_students(self) -> List[Dict[str, Any]]:
        with self._state_lock:
            return [s.to_dict() for s in self.students.values()]

    def get_student(self, student_id: str) -> Optional[StudentSession]:
        with self._state_lock:
            return self.students.get(student_id.strip().upper())

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._state_lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._state_lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def _broadcast(self, payload: Dict[str, Any]) -> None:
        payload["timestamp"] = time.time()
        dead = []
        for q in self.subscribers:
            try:
                q.put_nowait(payload)
            except (queue.Full, Exception):
                dead.append(q)
        for d in dead:
            if d in self.subscribers:
                self.subscribers.remove(d)

    def _recalc_student_score(self, student: StudentSession) -> None:
        count = len(student.violations)
        new_score = max(0.0, self.config.initial_score - (count * self.config.penalty_per_violation))
        student.score = round(new_score, 2)
        if count >= self.config.max_violations:
            student.status = StudentStatus.LOCKED

    def _log_audit(self, actor: str, action: str, details: Dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "actor": actor,
            "action": action,
            "details": details,
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_audit_logs(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not os.path.exists(self.log_path):
            return []
        logs = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            logs.append(json.loads(line))
                        except Exception:
                            continue
        except Exception:
            return []
        return logs[-limit:]

    def export_csv_report(self) -> str:
        with self._state_lock:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Mã SV", "Họ và tên", "IP LAN", "Điểm cuối", "Số vi phạm", "Trạng thái", "Thời gian nộp"])
            for s in self.students.values():
                sub_time = (
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s.submitted_at))
                    if s.submitted_at
                    else "Chưa nộp"
                )
                writer.writerow([
                    s.student_id,
                    s.name,
                    s.ip_address,
                    s.score,
                    len(s.violations),
                    s.status.value,
                    sub_time,
                ])
            return output.getvalue()
