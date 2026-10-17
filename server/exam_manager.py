from __future__ import annotations

import csv
import hmac
import io
import json
import os
import queue
import secrets
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
from server.repository import ExamRepository, get_exam_repository


def parse_timestamp(val: Any) -> Optional[float]:
    """Chuyển đổi an toàn chuỗi ISO, float timestamp hoặc datetime thành POSIX timestamp."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            pass
        try:
            from datetime import datetime
            return datetime.fromisoformat(val).timestamp()
        except Exception:
            pass
    return None


class ExamManager:
    _instance: Optional[ExamManager] = None
    _lock = threading.Lock()
    _global_timer_thread: Optional[threading.Thread] = None
    _global_stop_timer: Optional[threading.Event] = None

    @classmethod
    def get_instance(cls) -> ExamManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(
        self,
        log_path: str = "data/exam_audit.jsonl",
        repository: Optional[ExamRepository] = None,
    ) -> None:
        self.config = ExamConfig()
        self.students: Dict[str, StudentSession] = {}
        self.subscribers: List[queue.Queue] = []
        self._state_lock = threading.RLock()
        self.log_path = log_path
        self.repository: ExamRepository = repository or get_exam_repository()
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        # Nạp kỳ thi kích hoạt từ cơ sở dữ liệu (chịu được khởi động lại server)
        self.active_exam: Optional[Dict[str, Any]] = None
        try:
            self.active_exam = self.repository.get_active_exam()
            if self.active_exam:
                self.config.exam_title = self.active_exam["title"]
                self.config.duration_minutes = self.active_exam["duration_minutes"]
                status_str = self.active_exam.get("status", "CREATED")
                if status_str in ExamStatus._value2member_map_:
                    self.config.status = ExamStatus(status_str)
        except Exception:
            pass

        # Tự động chốt các kỳ thi IN_PROGRESS đã quá hạn khi khởi động lại server
        try:
            self.check_and_finalize_expired_exams()
        except Exception:
            pass
        self._start_background_timer()

    def set_repository(self, repository: ExamRepository) -> None:
        with self._state_lock:
            self.repository = repository
            self.active_exam = self.repository.get_active_exam()

    def list_question_banks(self) -> List[Dict[str, Any]]:
        with self._state_lock:
            return self.repository.list_question_banks()

    def create_exam(
        self,
        bank_id: int,
        title: str,
        duration_minutes: int = 45,
        question_count: Optional[int] = None,
        shuffle: bool = True,
        actor: str = "PO",
    ) -> Dict[str, Any]:
        with self._state_lock:
            exam = self.repository.create_exam(
                bank_id=bank_id,
                title=title,
                duration_minutes=duration_minutes,
                question_count=question_count,
                shuffle=shuffle,
            )
            self.active_exam = exam
            self.config.exam_title = exam["title"]
            self.config.duration_minutes = exam["duration_minutes"]
            self._log_audit(actor, "EXAM_CREATE", exam)
            self._broadcast({"type": "EXAM_CREATED", "exam": exam})
            return exam

    def get_active_exam(self) -> Optional[Dict[str, Any]]:
        with self._state_lock:
            if not self.active_exam:
                self.active_exam = self.repository.get_active_exam()
            return self.active_exam

    def set_active_exam(self, exam_id: int, actor: str = "PO") -> Dict[str, Any]:
        with self._state_lock:
            exam = self.repository.set_active_exam(exam_id)
            self.active_exam = exam
            self.config.exam_title = exam["title"]
            self.config.duration_minutes = exam["duration_minutes"]
            self._log_audit(actor, "EXAM_ACTIVATE", exam)
            self._broadcast({"type": "EXAM_ACTIVATED", "exam": exam})
            return exam

    def get_remaining_seconds(self) -> int:
        """Tính số giây còn lại của kỳ thi từ started_at theo đồng hồ server."""
        with self._state_lock:
            exam = self.get_active_exam()
            if not exam:
                return int(self.config.duration_minutes * 60)
            status = exam.get("status", "CREATED")
            if status == "FINISHED":
                return 0
            if status != "IN_PROGRESS":
                return int(exam.get("duration_minutes", self.config.duration_minutes) * 60)

            started_at = parse_timestamp(exam.get("started_at"))
            if not started_at:
                return int(exam.get("duration_minutes", self.config.duration_minutes) * 60)

            duration_sec = int(exam.get("duration_minutes", self.config.duration_minutes) * 60)
            elapsed = time.time() - started_at
            remaining = int(duration_sec - elapsed)
            if remaining <= 0:
                if status != "FINISHED":
                    try:
                        self.set_exam_status("FINISHED", actor="SYSTEM_TIMER")
                    except Exception:
                        pass
                return 0
            return remaining

    def ensure_active_exam(self) -> Dict[str, Any]:
        """Đảm bảo luôn có kỳ thi kích hoạt; nếu chưa có thì kích hoạt kỳ thi đầu tiên hoặc tạo kỳ thi mẫu."""
        with self._state_lock:
            exam = self.get_active_exam()
            if exam:
                return exam
            banks = self.repository.list_question_banks()
            if not banks:
                from server.repository import InMemoryExamRepository
                if isinstance(self.repository, InMemoryExamRepository):
                    bank_id = self.repository.add_sample_bank("Ngân hàng Lập trình mạng GK")
                else:
                    raise RuntimeError("Cơ sở dữ liệu chưa có ngân hàng đề nào")
            else:
                bank_id = banks[0]["id"]

            created = self.repository.create_exam(
                bank_id=bank_id,
                title="ĐỀ THI MÔN LẬP TRÌNH MẠNG (LAN PROCTORING)",
                duration_minutes=self.config.duration_minutes,
                shuffle=True,
            )
            self.repository.set_exam_status(created["id"], "IN_PROGRESS")
            self.active_exam = self.repository.get_active_exam()
            if self.active_exam:
                self.config.exam_title = self.active_exam["title"]
                self.config.duration_minutes = self.active_exam["duration_minutes"]
                self.config.status = ExamStatus.IN_PROGRESS
            return self.active_exam

    def check_and_finalize_expired_exams(self, now: Optional[float] = None) -> List[int]:
        """
        Kiểm tra và tự động chốt các kỳ thi IN_PROGRESS đã quá hạn (started_at + duration < now),
        đồng thời tự thu bài và chấm điểm cho tất cả thí sinh đang thi.
        Chạy độc lập với client (phục vụ bộ hẹn giờ nền và khi server restart).
        """
        current_time = now if now is not None else time.time()
        finalized_exam_ids = []
        with self._state_lock:
            # 1. Kiểm tra kỳ thi đang kích hoạt
            exam = self.get_active_exam()
            if exam and exam.get("status") == "IN_PROGRESS":
                started_at = parse_timestamp(exam.get("started_at"))
                duration_sec = int(exam.get("duration_minutes", self.config.duration_minutes) * 60)
                if started_at is not None and (current_time - started_at) >= duration_sec:
                    self.set_exam_status("FINISHED", actor="SERVER_BACKGROUND_TIMER")
                    finalized_exam_ids.append(exam["id"])

            # 2. Quét các kỳ thi IN_PROGRESS khác trong repository
            if hasattr(self.repository, "list_exams"):
                try:
                    for ex in self.repository.list_exams():
                        if ex.get("status") == "IN_PROGRESS":
                            st = parse_timestamp(ex.get("started_at"))
                            dur = int(ex.get("duration_minutes", 45) * 60)
                            if st is not None and (current_time - st) >= dur:
                                self.repository.set_exam_status(ex["id"], "FINISHED")
                                finalized_exam_ids.append(ex["id"])
                                if hasattr(self.repository, "get_exam_student_ids"):
                                    for s_id in self.repository.get_exam_student_ids(ex["id"]):
                                        if s_id in self.students:
                                            self.submit_exam(s_id, actor="SERVER_BACKGROUND_TIMER")
                                        else:
                                            try:
                                                earned, corr, tot = self.repository.grade_student(ex["id"], s_id)
                                                max_pts = self.repository.get_exam_max_points(ex["id"], s_id)
                                                sc = round((earned / max_pts) * self.config.initial_score, 2) if max_pts > 0 else earned
                                                self.repository.save_student_result(
                                                    exam_id=ex["id"],
                                                    student_id=s_id,
                                                    exam_score=sc,
                                                    violation_penalty=0.0,
                                                    final_score=sc,
                                                    violation_count=0,
                                                    status="SUBMITTED",
                                                    submitted=True,
                                                )
                                            except Exception:
                                                pass
                except Exception:
                    pass

        return finalized_exam_ids

    def _start_background_timer(self) -> None:
        with ExamManager._lock:
            if ExamManager._global_timer_thread is not None and ExamManager._global_timer_thread.is_alive():
                self._timer_thread = ExamManager._global_timer_thread
                self._stop_timer = ExamManager._global_stop_timer
                return

            self._stop_timer = threading.Event()
            ExamManager._global_stop_timer = self._stop_timer

            def _timer_worker():
                while not self._stop_timer.is_set():
                    try:
                        self.check_and_finalize_expired_exams()
                    except Exception as exc:
                        import logging
                        logging.getLogger("ExamBackgroundTimer").warning(f"Lỗi kiểm tra kỳ thi tự động: {exc}")
                    self._stop_timer.wait(1.0)

            self._timer_thread = threading.Thread(target=_timer_worker, daemon=True, name="ExamBackgroundTimer")
            ExamManager._global_timer_thread = self._timer_thread
            self._timer_thread.start()

    def stop(self) -> None:
        with ExamManager._lock:
            if hasattr(self, "_stop_timer") and self._stop_timer is not None:
                self._stop_timer.set()
            if ExamManager._global_stop_timer is not None:
                ExamManager._global_stop_timer.set()
            if hasattr(self, "_timer_thread") and self._timer_thread is not None and self._timer_thread.is_alive():
                self._timer_thread.join(timeout=2.0)
            if ExamManager._global_timer_thread is not None and ExamManager._global_timer_thread.is_alive():
                ExamManager._global_timer_thread.join(timeout=2.0)
            ExamManager._global_timer_thread = None
            ExamManager._global_stop_timer = None

    def verify_student_token(self, token: str, expected_student_id: Optional[str] = None) -> StudentSession:
        """Xác thực token phiên thí sinh bằng hmac.compare_digest, chống giả mạo MSSV."""
        import hmac
        with self._state_lock:
            if not token:
                raise PermissionError("Thiếu token phiên thí sinh")

            matched_student = None
            token_bytes = token.encode("utf-8")
            for student in self.students.values():
                if hmac.compare_digest(student.token.encode("utf-8"), token_bytes):
                    matched_student = student
                    break

            if not matched_student:
                raise PermissionError("Token phiên thí sinh không hợp lệ hoặc đã hết hạn")

            if expected_student_id:
                if matched_student.student_id != expected_student_id.strip().upper():
                    raise PermissionError(f"Token không thuộc về sinh viên {expected_student_id.strip().upper()}")

            return matched_student

    def load_exam_for_student(self, student_id: str) -> List[Dict[str, Any]]:
        """Dựng đề thi đã xáo trộn theo MSSV, TUYỆT ĐỐI không chứa answer_key."""
        with self._state_lock:
            student_id = student_id.strip().upper()
            exam = self.ensure_active_exam()
            questions = self.repository.load_exam_for_student(exam["id"], student_id)
            student = self.students.get(student_id)
            if student:
                student.allocated_question_ids = {int(q["question_id"]) for q in questions}
            return questions

    def save_student_answer(self, student_id: str, question_id: int, chosen: str) -> None:
        """Lưu nháp câu trả lời trắc nghiệm (idempotent), giới hạn tần suất và kiểm tra câu hỏi hợp lệ."""
        with self._state_lock:
            student_id = student_id.strip().upper()
            chosen = chosen.strip().upper()
            if chosen not in ("A", "B", "C", "D"):
                raise ValueError("Đáp án phải thuộc A, B, C hoặc D")

            exam = self.get_active_exam()
            if not exam:
                raise RuntimeError("Chưa có kỳ thi nào đang kích hoạt")

            exam_status = exam.get("status", "CREATED")
            if exam_status == "FINISHED" or self.get_remaining_seconds() <= 0:
                raise PermissionError("Kỳ thi đã kết thúc, không thể lưu đáp án")

            student = self.students.get(student_id)
            if not student:
                raise KeyError(f"Sinh viên {student_id} chưa đăng ký vào phòng thi")

            if student.status == StudentStatus.LOCKED:
                raise PermissionError("Bài thi của thí sinh đã bị khóa do vi phạm")
            if student.status == StudentStatus.SUBMITTED:
                raise PermissionError("Bài thi đã được nộp, không thể thay đổi đáp án")

            # 1. Giới hạn tần suất lưu nháp (Rate Limiting: tối thiểu 0.2s giữa 2 lần lưu)
            now = time.time()
            if now - student.last_save_draft_at < 0.2:
                raise BufferError("Thao tác lưu nháp quá nhanh, vui lòng chờ giây lát (Rate Limit)")
            student.last_save_draft_at = now

            # 2. Kiểm tra tính hợp lệ của câu hỏi: phải thuộc đề thi được giao cho thí sinh này
            if not student.allocated_question_ids:
                questions = self.repository.load_exam_for_student(exam["id"], student_id)
                student.allocated_question_ids = {int(q["question_id"]) for q in questions}

            if int(question_id) not in student.allocated_question_ids:
                raise ValueError(f"Câu hỏi #{question_id} không thuộc đề thi được giao cho thí sinh {student_id}")

            self.repository.save_submission(exam["id"], student_id, int(question_id), chosen)

            student.answers[str(question_id)] = chosen
            student.last_seen = now

            # Cập nhật điểm bài làm tạm tính theo thời gian thực (real-time) cho console giám thị
            try:
                earned, corr, tot = self.repository.grade_student(exam["id"], student_id)
                max_pts = self.repository.get_exam_max_points(exam["id"], student_id)
                student.exam_score = round((earned / max_pts) * self.config.initial_score, 2) if max_pts > 0 else earned
            except Exception:
                pass

    def get_student_submissions(self, student_id: str) -> Dict[str, str]:
        """Lấy danh sách các câu trả lời nháp đã lưu để khôi phục khi F5."""
        with self._state_lock:
            student_id = student_id.strip().upper()
            exam = self.get_active_exam()
            if not exam:
                return {}
            raw = self.repository.get_student_submissions(exam["id"], student_id)
            return {str(k): v for k, v in raw.items()}

    def set_exam_status(self, status: str, actor: str = "PO") -> Dict[str, Any]:
        with self._state_lock:
            status_val = status.strip().upper()
            if self.active_exam:
                self.active_exam = self.repository.set_exam_status(self.active_exam["id"], status_val)
            if status_val in ExamStatus._value2member_map_:
                self.config.status = ExamStatus(status_val)
            # Nếu kỳ thi kết thúc, tự động thu bài và chấm cho toàn bộ thí sinh đã đăng ký
            if status_val == "FINISHED":
                for s_id, s in list(self.students.items()):
                    if s.status != StudentStatus.SUBMITTED:
                        try:
                            self.submit_exam(s_id, actor="SYSTEM_AUTO_SUBMIT")
                        except Exception:
                            pass
            self._log_audit(actor, "EXAM_STATUS_CHANGE", {"status": status_val})
            self._broadcast({"type": "CONFIG_UPDATE", "config": self.config.to_dict()})
            return self.active_exam or {"status": status_val}

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
                if not student.allow_re_register:
                    raise FileExistsError("Thí sinh đã đăng ký và đang có phiên thi hợp lệ. Vui lòng liên hệ giám thị để cấp lại phiên nếu cần.")
                # Nếu giám thị đã cấp lại phiên thi: cấp token mới và cập nhật thông tin
                student.token = secrets.token_urlsafe(32)
                student.name = name
                student.ip_address = ip_address
                student.last_seen = time.time()
                student.allow_re_register = False
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

    def reset_student_session(
        self,
        student_id: str,
        reason: str = "Giám thị cấp lại phiên thi",
        actor: str = "SM",
    ) -> StudentSession:
        """Giám thị cấp lại phiên cho thí sinh lỡ đóng tab/đổi máy, vô hiệu hóa token cũ."""
        with self._state_lock:
            student_id = student_id.strip().upper()
            if student_id not in self.students:
                raise KeyError(f"Sinh viên {student_id} chưa đăng ký vào phòng thi")
            student = self.students[student_id]
            # Vô hiệu hóa token cũ ngay lập tức
            student.token = secrets.token_urlsafe(32)
            student.allow_re_register = True
            student.last_seen = time.time()
            self._log_audit(actor, "SESSION_RESET", {
                "student_id": student_id,
                "reason": reason,
            })
            self._broadcast({
                "type": "SESSION_RESET",
                "student_id": student_id,
                "message": reason,
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

    def submit_exam(
        self,
        student_id: str,
        answers: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = None,
    ) -> StudentSession:
        with self._state_lock:
            student_id = student_id.strip().upper()
            if student_id not in self.students:
                raise KeyError(f"Student {student_id} not found")

            student = self.students[student_id]
            exam = self.get_active_exam()
            exam_id = exam["id"] if exam else None

            # Lưu bổ sung các câu trả lời kèm theo (nếu có)
            if answers and isinstance(answers, dict) and exam_id:
                for qid_raw, chosen_raw in answers.items():
                    if chosen_raw and str(chosen_raw).strip().upper() in ("A", "B", "C", "D"):
                        try:
                            self.repository.save_submission(exam_id, student_id, int(qid_raw), str(chosen_raw).strip().upper())
                            student.answers[str(qid_raw)] = str(chosen_raw).strip().upper()
                        except Exception:
                            pass

            # 1. Chấm điểm bài làm từ cơ sở dữ liệu (submissions)
            if exam_id and self.repository:
                try:
                    earned_points, correct_count, total_count = self.repository.grade_student(exam_id, student_id)
                    max_points = 0.0
                    if hasattr(self.repository, "get_exam_max_points"):
                        max_points = self.repository.get_exam_max_points(exam_id, student_id)
                    if max_points <= 0:
                        max_points = float(total_count) if total_count > 0 else 1.0

                    if earned_points > 0 and max_points > 0:
                        exam_score = round((earned_points / max_points) * self.config.initial_score, 2)
                    else:
                        exam_score = 0.0
                except Exception:
                    exam_score = 0.0
                    correct_count = 0
                    total_count = 0
            else:
                exam_score = 0.0
                correct_count = 0
                total_count = 0

            # 2. Tính điểm trừ vi phạm và điểm tổng kết: final = max(0, exam_score - vi phạm)
            violation_penalty = round(len(student.violations) * self.config.penalty_per_violation, 2)
            final_score = max(0.0, round(exam_score - violation_penalty, 2))

            student.exam_score = exam_score
            student.violation_penalty = violation_penalty
            student.score = final_score
            if student.status != StudentStatus.LOCKED:
                student.status = StudentStatus.SUBMITTED
            student.submitted_at = time.time()
            student.last_seen = time.time()

            # 3. Ghi nhận kết quả vào repository (bảng student_exam_results)
            if exam_id and self.repository:
                try:
                    self.repository.save_student_result(
                        exam_id=exam_id,
                        student_id=student_id,
                        exam_score=exam_score,
                        violation_penalty=violation_penalty,
                        final_score=final_score,
                        violation_count=len(student.violations),
                        status=student.status.value,
                        submitted=True,
                    )
                except Exception:
                    pass

            # 4. Ghi audit log
            act = actor or student_id
            self._log_audit(act, "EXAM_SUBMIT", {
                "student_id": student_id,
                "exam_id": exam_id,
                "exam_score": exam_score,
                "violation_penalty": violation_penalty,
                "final_score": final_score,
                "violation_count": len(student.violations),
                "correct_count": correct_count,
                "total_count": total_count,
                "status": student.status.value,
            })
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
        if isinstance(details, dict) and "student_id" in details:
            entry["student_id"] = details["student_id"]
        elif actor and actor not in ("SYSTEM", "PO", "SM", "SERVER_BACKGROUND_TIMER"):
            entry["student_id"] = actor
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # Ghi đồng thời vào hệ thống SHA-256 Chained Audit Log của RPMC
        try:
            from server.audit import AuditLogger
            AuditLogger().log(actor=actor, action=action, result="SUCCESS", metadata=details)
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
            writer.writerow(["MSSV", "Họ tên", "Điểm bài làm", "Điểm trừ vi phạm", "Điểm cuối", "Số lần vi phạm", "Trạng thái"])
            for s in self.students.values():
                writer.writerow([
                    s.student_id,
                    s.name,
                    f"{s.exam_score:.1f}",
                    f"{s.violation_penalty:.1f}",
                    f"{s.score:.1f}",
                    len(s.violations),
                    s.status.value,
                ])
            return output.getvalue()
