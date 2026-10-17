from __future__ import annotations

import os
import random
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ExamRepository(ABC):
    """Lớp giao diện Repository trừu tượng cho ngân hàng đề, kỳ thi và bài nộp."""

    @abstractmethod
    def list_question_banks(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các ngân hàng đề hiện có kèm số lượng câu hỏi."""
        pass

    @abstractmethod
    def get_question_bank(self, bank_id: int) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một ngân hàng đề theo ID."""
        pass

    @abstractmethod
    def create_exam(
        self,
        bank_id: int,
        title: str,
        duration_minutes: int = 45,
        question_count: Optional[int] = None,
        shuffle: bool = True,
    ) -> Dict[str, Any]:
        """Tạo một kỳ thi mới từ ngân hàng đề."""
        pass

    @abstractmethod
    def get_exam(self, exam_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một kỳ thi."""
        pass

    @abstractmethod
    def get_active_exam(self) -> Optional[Dict[str, Any]]:
        """Lấy kỳ thi đang được kích hoạt."""
        pass

    @abstractmethod
    def set_active_exam(self, exam_id: int) -> Dict[str, Any]:
        """Kích hoạt một kỳ thi làm kỳ thi chính."""
        pass

    @abstractmethod
    def set_exam_status(self, exam_id: int, status: str) -> Dict[str, Any]:
        """Cập nhật trạng thái kỳ thi ('CREATED', 'IN_PROGRESS', 'FINISHED')."""
        pass

    @abstractmethod
    def list_exams(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các kỳ thi đã tạo."""
        pass

    @abstractmethod
    def load_exam_for_student(
        self,
        exam_id: int,
        student_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Dựng đề thi đã xáo trộn cho từng thí sinh.
        TUYỆT ĐỐI KHÔNG chứa answer_key nhằm chống lộ đáp án phía client.
        """
        pass

    @abstractmethod
    def save_submission(
        self,
        exam_id: int,
        student_id: str,
        question_id: int,
        chosen: str,
    ) -> None:
        """Lưu nháp câu trả lời trắc nghiệm của thí sinh (upsert)."""
        pass

    @abstractmethod
    def get_student_submissions(
        self,
        exam_id: int,
        student_id: str,
    ) -> Dict[int, str]:
        """Lấy danh sách câu trả lời đã lưu của thí sinh {question_id: chosen_orig}."""
        pass

    @abstractmethod
    def grade_student(
        self,
        exam_id: int,
        student_id: str,
        submitted_answers: Optional[Dict[int, str]] = None,
    ) -> Tuple[float, int, int]:
        """
        Chấm điểm bài làm của thí sinh:
        Trả về (điểm_bài_làm, số_câu_đúng, tổng_số_câu).
        """
        pass

    @abstractmethod
    def get_exam_max_points(self, exam_id: int, student_id: str) -> float:
        """Tổng điểm tối đa của đề thi được giao cho thí sinh này."""
        pass

    @abstractmethod
    def get_exam_student_ids(self, exam_id: int) -> List[str]:
        """Danh sách các MSSV có bài làm trong kỳ thi này."""
        pass

    @abstractmethod
    def save_student_result(
        self,
        exam_id: int,
        student_id: str,
        exam_score: float,
        violation_penalty: float,
        final_score: float,
        violation_count: int,
        status: str,
        submitted: bool = False,
    ) -> None:
        """Lưu kết quả tổng hợp của thí sinh xuống cơ sở dữ liệu."""
        pass


class PostgresExamRepository(ExamRepository):
    """Triển khai Repository trên PostgreSQL (psycopg 3) với truy vấn tham số hóa %s."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        import psycopg
        self._psycopg = psycopg

    def _get_connection(self):
        return self._psycopg.connect(self.dsn)

    def list_question_banks(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT b.id, b.title, b.subject, count(q.id) as question_count, b.created_at
                FROM question_banks b
                LEFT JOIN questions q ON q.bank_id = b.id
                GROUP BY b.id, b.title, b.subject, b.created_at
                ORDER BY b.id DESC
                """
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "title": r[1],
                    "subject": r[2] or "",
                    "question_count": int(r[3]),
                    "created_at": r[4].isoformat() if r[4] else "",
                }
                for r in rows
            ]

    def get_question_bank(self, bank_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT b.id, b.title, b.subject, count(q.id) as question_count, b.created_at
                FROM question_banks b
                LEFT JOIN questions q ON q.bank_id = b.id
                WHERE b.id = %s
                GROUP BY b.id, b.title, b.subject, b.created_at
                """,
                (bank_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "title": row[1],
                "subject": row[2] or "",
                "question_count": int(row[3]),
                "created_at": row[4].isoformat() if row[4] else "",
            }

    def create_exam(
        self,
        bank_id: int,
        title: str,
        duration_minutes: int = 45,
        question_count: Optional[int] = None,
        shuffle: bool = True,
    ) -> Dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Tên kỳ thi không được để trống")
        if duration_minutes <= 0:
            raise ValueError("Thời gian làm bài phải lớn hơn 0")
        if question_count is not None and question_count <= 0:
            raise ValueError("Số lượng câu hỏi phải lớn hơn 0")

        with self._get_connection() as conn:
            with conn.transaction():
                # Kiểm tra ngân hàng đề có tồn tại không
                bank = conn.execute(
                    "SELECT id, title FROM question_banks WHERE id = %s", (bank_id,)
                ).fetchone()
                if not bank:
                    raise ValueError(f"Ngân hàng đề #{bank_id} không tồn tại")

                # Hủy kích hoạt các kỳ thi cũ
                conn.execute("UPDATE exams SET is_active = FALSE")

                row = conn.execute(
                    """
                    INSERT INTO exams (bank_id, title, duration_minutes, question_count, shuffle, status, is_active)
                    VALUES (%s, %s, %s, %s, %s, 'CREATED', TRUE)
                    RETURNING id, bank_id, title, duration_minutes, question_count, shuffle, created_at, status, is_active
                    """,
                    (bank_id, title, duration_minutes, question_count, shuffle),
                ).fetchone()

                return {
                    "id": row[0],
                    "bank_id": row[1],
                    "bank_title": bank[1],
                    "title": row[2],
                    "duration_minutes": row[3],
                    "question_count": row[4],
                    "shuffle": row[5],
                    "created_at": row[6].isoformat() if row[6] else "",
                    "status": row[7] if len(row) > 7 else "CREATED",
                    "is_active": row[8] if len(row) > 8 else True,
                    "started_at": None,
                    "ended_at": None,
                }

    def get_exam(self, exam_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT e.id, e.bank_id, e.title, e.duration_minutes, e.question_count, e.shuffle, e.created_at,
                       b.title as bank_title, e.status, e.is_active, e.started_at, e.ended_at
                FROM exams e
                JOIN question_banks b ON b.id = e.bank_id
                WHERE e.id = %s
                """,
                (exam_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "bank_id": row[1],
                "title": row[2],
                "duration_minutes": row[3],
                "question_count": row[4],
                "shuffle": row[5],
                "created_at": row[6].isoformat() if row[6] else "",
                "bank_title": row[7],
                "status": row[8] if row[8] else "CREATED",
                "is_active": bool(row[9]),
                "started_at": row[10].isoformat() if row[10] else None,
                "ended_at": row[11].isoformat() if row[11] else None,
            }

    def get_active_exam(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT e.id, e.bank_id, e.title, e.duration_minutes, e.question_count, e.shuffle, e.created_at,
                       b.title as bank_title, e.status, e.is_active, e.started_at, e.ended_at
                FROM exams e
                JOIN question_banks b ON b.id = e.bank_id
                WHERE e.is_active = TRUE
                ORDER BY e.id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "bank_id": row[1],
                "title": row[2],
                "duration_minutes": row[3],
                "question_count": row[4],
                "shuffle": row[5],
                "created_at": row[6].isoformat() if row[6] else "",
                "bank_title": row[7],
                "status": row[8] if row[8] else "CREATED",
                "is_active": bool(row[9]),
                "started_at": row[10].isoformat() if row[10] else None,
                "ended_at": row[11].isoformat() if row[11] else None,
            }

    def set_active_exam(self, exam_id: int) -> Dict[str, Any]:
        with self._get_connection() as conn:
            with conn.transaction():
                conn.execute("UPDATE exams SET is_active = FALSE")
                conn.execute("UPDATE exams SET is_active = TRUE WHERE id = %s", (exam_id,))
        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")
        return exam

    def set_exam_status(self, exam_id: int, status: str) -> Dict[str, Any]:
        status = status.strip().upper()
        if status not in ("CREATED", "IN_PROGRESS", "FINISHED"):
            raise ValueError(f"Trạng thái {status!r} không hợp lệ")

        with self._get_connection() as conn:
            with conn.transaction():
                if status == "IN_PROGRESS":
                    conn.execute(
                        "UPDATE exams SET status = %s, started_at = COALESCE(started_at, now()) WHERE id = %s",
                        (status, exam_id),
                    )
                elif status == "FINISHED":
                    conn.execute(
                        "UPDATE exams SET status = %s, ended_at = now() WHERE id = %s",
                        (status, exam_id),
                    )
                else:
                    conn.execute("UPDATE exams SET status = %s WHERE id = %s", (status, exam_id))

        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")
        return exam

    def list_exams(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.bank_id, e.title, e.duration_minutes, e.question_count, e.shuffle, e.created_at,
                       b.title as bank_title, e.status, e.is_active, e.started_at, e.ended_at
                FROM exams e
                JOIN question_banks b ON b.id = e.bank_id
                ORDER BY e.id DESC
                """
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "bank_id": r[1],
                    "title": r[2],
                    "duration_minutes": r[3],
                    "question_count": r[4],
                    "shuffle": r[5],
                    "created_at": r[6].isoformat() if r[6] else "",
                    "bank_title": r[7],
                    "status": r[8] if r[8] else "CREATED",
                    "is_active": bool(r[9]),
                    "started_at": r[10].isoformat() if r[10] else None,
                    "ended_at": r[11].isoformat() if r[11] else None,
                }
                for r in rows
            ]

    def load_exam_for_student(
        self,
        exam_id: int,
        student_id: str,
    ) -> List[Dict[str, Any]]:
        student_id = student_id.strip()
        if not student_id:
            raise ValueError("MSSV không được để trống")

        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")

        bank_id = exam["bank_id"]
        count = exam["question_count"]
        shuffle = exam["shuffle"]

        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, q_no, content FROM questions WHERE bank_id = %s ORDER BY q_no",
                (bank_id,),
            ).fetchall()

            rng = random.Random(f"{bank_id}:{student_id}")
            if shuffle:
                rng.shuffle(rows)
            if count:
                rows = rows[:count]

            student_exam = []
            for qid, q_no, content in rows:
                opts = conn.execute(
                    "SELECT label, content FROM question_options WHERE question_id = %s ORDER BY label",
                    (qid,),
                ).fetchall()
                if shuffle:
                    rng.shuffle(opts)

                # Tuyệt đối KHÔNG trả answer_key ra ngoài!
                student_exam.append({
                    "question_id": qid,
                    "content": content,
                    "options": [
                        {"label": "ABCD"[i], "orig": orig, "content": text}
                        for i, (orig, text) in enumerate(opts)
                    ],
                })
            return student_exam

    def save_submission(
        self,
        exam_id: int,
        student_id: str,
        question_id: int,
        chosen: str,
    ) -> None:
        student_id = student_id.strip()
        chosen = chosen.strip().upper()
        if chosen not in ("A", "B", "C", "D"):
            raise ValueError("Đáp án phải thuộc A, B, C hoặc D")

        with self._get_connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO submissions (exam_id, student_id, question_id, chosen, saved_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (exam_id, student_id, question_id)
                    DO UPDATE SET chosen = EXCLUDED.chosen, saved_at = now()
                    """,
                    (exam_id, student_id, question_id, chosen),
                )

    def get_student_submissions(
        self,
        exam_id: int,
        student_id: str,
    ) -> Dict[int, str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT question_id, chosen FROM submissions WHERE exam_id = %s AND student_id = %s",
                (exam_id, student_id.strip()),
            ).fetchall()
            return {r[0]: r[1] for r in rows}

    def grade_student(
        self,
        exam_id: int,
        student_id: str,
        submitted_answers: Optional[Dict[int, str]] = None,
    ) -> Tuple[float, int, int]:
        student_id = student_id.strip()
        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")

        bank_id = exam["bank_id"]

        with self._get_connection() as conn:
            if submitted_answers is None:
                submitted_answers = self.get_student_submissions(exam_id, student_id)

            keys_pts = conn.execute(
                "SELECT id, answer_key, points FROM questions WHERE bank_id = %s",
                (bank_id,),
            ).fetchall()

            keys = {r[0]: r[1] for r in keys_pts}
            pts = {r[0]: float(r[2]) for r in keys_pts}

            student_questions = self.load_exam_for_student(exam_id, student_id)
            allocated_qids = {q["question_id"] for q in student_questions}

            total_score = 0.0
            correct_count = 0
            for qid, chosen_orig in submitted_answers.items():
                if (not allocated_qids or qid in allocated_qids) and keys.get(qid) == chosen_orig:
                    total_score += pts.get(qid, 1.0)
                    correct_count += 1

            total_questions = len(allocated_qids) if allocated_qids else (exam["question_count"] or len(keys))
            return float(round(total_score, 2)), correct_count, total_questions

    def get_exam_max_points(self, exam_id: int, student_id: str) -> float:
        exam = self.get_exam(exam_id)
        if not exam:
            return 0.0
        student_questions = self.load_exam_for_student(exam_id, student_id)
        allocated_qids = {q["question_id"] for q in student_questions}
        bank_id = exam["bank_id"]
        with self._get_connection() as conn:
            rows = conn.execute("SELECT id, points FROM questions WHERE bank_id = %s", (bank_id,)).fetchall()
            pts = {r[0]: float(r[1]) for r in rows}
            if allocated_qids:
                return float(round(sum(pts.get(qid, 1.0) for qid in allocated_qids), 2))
            return float(round(sum(pts.values()) if pts else float(exam.get("question_count") or 1.0), 2))

    def get_exam_student_ids(self, exam_id: int) -> List[str]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT student_id FROM submissions WHERE exam_id = %s", (exam_id,)).fetchall()
            return [r[0] for r in rows]

    def save_student_result(
        self,
        exam_id: int,
        student_id: str,
        exam_score: float,
        violation_penalty: float,
        final_score: float,
        violation_count: int,
        status: str,
        submitted: bool = False,
    ) -> None:
        with self._get_connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO student_exam_results (
                        exam_id, student_id, exam_score, violation_penalty,
                        final_score, violation_count, status, submitted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() ELSE NULL END)
                    ON CONFLICT (exam_id, student_id)
                    DO UPDATE SET
                        exam_score = EXCLUDED.exam_score,
                        violation_penalty = EXCLUDED.violation_penalty,
                        final_score = EXCLUDED.final_score,
                        violation_count = EXCLUDED.violation_count,
                        status = EXCLUDED.status,
                        submitted_at = COALESCE(EXCLUDED.submitted_at, student_exam_results.submitted_at)
                    """,
                    (
                        exam_id,
                        student_id.strip(),
                        exam_score,
                        violation_penalty,
                        final_score,
                        violation_count,
                        status,
                        submitted,
                    ),
                )


class InMemoryExamRepository(ExamRepository):
    """
    Triển khai Repository lưu trữ trong bộ nhớ (In-Memory).
    Dùng để chạy Unit Test độc lập và làm fallback khi chưa cấu hình PostgreSQL.
    """

    def __init__(self):
        self.banks: Dict[int, Dict[str, Any]] = {}
        self.questions: Dict[int, List[Dict[str, Any]]] = {}  # bank_id -> list[question]
        self.options: Dict[int, List[Dict[str, Any]]] = {}    # question_id -> list[opt]
        self.exams: Dict[int, Dict[str, Any]] = {}
        self.submissions: Dict[Tuple[int, str, int], Dict[str, Any]] = {}  # (exam_id, student_id, q_id) -> sub
        self.student_results: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self._next_bank_id = 1
        self._next_q_id = 1
        self._next_exam_id = 1

    def add_sample_bank(
        self,
        title: str,
        subject: str = "Lập trình mạng",
        questions_data: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        bank_id = self._next_bank_id
        self._next_bank_id += 1
        self.banks[bank_id] = {
            "id": bank_id,
            "title": title,
            "subject": subject,
            "created_at": "2026-10-17T00:00:00Z",
        }
        self.questions[bank_id] = []

        if not questions_data:
            questions_data = [
                {
                    "content": f"Câu hỏi kiểm tra số {i} về TCP/IP?",
                    "options": {"A": "Đáp án A", "B": "Đáp án B", "C": "Đáp án C", "D": "Đáp án D"},
                    "answer": "B",
                    "points": 2.0,
                }
                for i in range(1, 6)
            ]

        for q in questions_data:
            qid = self._next_q_id
            self._next_q_id += 1
            self.questions[bank_id].append({
                "id": qid,
                "bank_id": bank_id,
                "q_no": len(self.questions[bank_id]) + 1,
                "content": q["content"],
                "answer_key": q["answer"],
                "points": float(q.get("points", 1.0)),
            })
            self.options[qid] = [
                {"label": lbl, "content": text}
                for lbl, text in sorted(q["options"].items())
            ]
        return bank_id

    def list_question_banks(self) -> List[Dict[str, Any]]:
        res = []
        for b_id, b in sorted(self.banks.items(), reverse=True):
            res.append({
                "id": b["id"],
                "title": b["title"],
                "subject": b["subject"],
                "question_count": len(self.questions.get(b_id, [])),
                "created_at": b["created_at"],
            })
        return res

    def get_question_bank(self, bank_id: int) -> Optional[Dict[str, Any]]:
        b = self.banks.get(bank_id)
        if not b:
            return None
        return {
            "id": b["id"],
            "title": b["title"],
            "subject": b["subject"],
            "question_count": len(self.questions.get(bank_id, [])),
            "created_at": b["created_at"],
        }

    def get_bank_questions(self, bank_id: int) -> List[Dict[str, Any]]:
        return self.questions.get(bank_id, [])

    def create_exam(
        self,
        bank_id: int,
        title: str,
        duration_minutes: int = 45,
        question_count: Optional[int] = None,
        shuffle: bool = True,
    ) -> Dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Tên kỳ thi không được để trống")
        if duration_minutes <= 0:
            raise ValueError("Thời gian làm bài phải lớn hơn 0")
        if question_count is not None and question_count <= 0:
            raise ValueError("Số lượng câu hỏi phải lớn hơn 0")

        bank = self.banks.get(bank_id)
        if not bank:
            raise ValueError(f"Ngân hàng đề #{bank_id} không tồn tại")

        # Hủy kích hoạt các kỳ thi cũ
        for e in self.exams.values():
            e["is_active"] = False

        exam_id = self._next_exam_id
        self._next_exam_id += 1

        exam_data = {
            "id": exam_id,
            "bank_id": bank_id,
            "bank_title": bank["title"],
            "title": title,
            "duration_minutes": duration_minutes,
            "question_count": question_count,
            "shuffle": shuffle,
            "status": "CREATED",
            "is_active": True,
            "started_at": None,
            "ended_at": None,
            "created_at": "2026-10-17T00:00:00Z",
        }
        self.exams[exam_id] = exam_data
        return exam_data

    def get_exam(self, exam_id: int) -> Optional[Dict[str, Any]]:
        return self.exams.get(exam_id)

    def get_active_exam(self) -> Optional[Dict[str, Any]]:
        for e in sorted(self.exams.values(), key=lambda x: x["id"], reverse=True):
            if e.get("is_active"):
                return e
        return None

    def set_active_exam(self, exam_id: int) -> Dict[str, Any]:
        exam = self.exams.get(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")
        for e in self.exams.values():
            e["is_active"] = False
        exam["is_active"] = True
        return exam

    def set_exam_status(self, exam_id: int, status: str) -> Dict[str, Any]:
        exam = self.exams.get(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")
        status = status.strip().upper()
        if status not in ("CREATED", "IN_PROGRESS", "FINISHED"):
            raise ValueError(f"Trạng thái {status!r} không hợp lệ")

        exam["status"] = status
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        if status == "IN_PROGRESS" and not exam.get("started_at"):
            exam["started_at"] = now_iso
        elif status == "FINISHED":
            exam["ended_at"] = now_iso
        return exam

    def list_exams(self) -> List[Dict[str, Any]]:
        return list(sorted(self.exams.values(), key=lambda x: x["id"], reverse=True))

    def load_exam_for_student(
        self,
        exam_id: int,
        student_id: str,
    ) -> List[Dict[str, Any]]:
        student_id = student_id.strip()
        if not student_id:
            raise ValueError("MSSV không được để trống")

        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")

        bank_id = exam["bank_id"]
        count = exam["question_count"]
        shuffle = exam["shuffle"]

        q_list = list(self.questions.get(bank_id, []))
        rng = random.Random(f"{bank_id}:{student_id}")
        if shuffle:
            rng.shuffle(q_list)
        if count:
            q_list = q_list[:count]

        student_exam = []
        for q in q_list:
            qid = q["id"]
            opts = list(self.options.get(qid, []))
            if shuffle:
                rng.shuffle(opts)

            # Tuyệt đối KHÔNG trả answer_key ra ngoài!
            student_exam.append({
                "question_id": qid,
                "content": q["content"],
                "options": [
                    {"label": "ABCD"[i], "orig": opt["label"], "content": opt["content"]}
                    for i, opt in enumerate(opts)
                ],
            })
        return student_exam

    def save_submission(
        self,
        exam_id: int,
        student_id: str,
        question_id: int,
        chosen: str,
    ) -> None:
        student_id = student_id.strip()
        chosen = chosen.strip().upper()
        if chosen not in ("A", "B", "C", "D"):
            raise ValueError("Đáp án phải thuộc A, B, C hoặc D")

        self.submissions[(exam_id, student_id, question_id)] = {
            "exam_id": exam_id,
            "student_id": student_id,
            "question_id": question_id,
            "chosen": chosen,
        }

    def get_student_submissions(
        self,
        exam_id: int,
        student_id: str,
    ) -> Dict[int, str]:
        student_id = student_id.strip()
        result = {}
        for (e_id, s_id, q_id), sub in self.submissions.items():
            if e_id == exam_id and s_id == student_id:
                result[q_id] = sub["chosen"]
        return result

    def grade_student(
        self,
        exam_id: int,
        student_id: str,
        submitted_answers: Optional[Dict[int, str]] = None,
    ) -> Tuple[float, int, int]:
        student_id = student_id.strip()
        exam = self.get_exam(exam_id)
        if not exam:
            raise ValueError(f"Kỳ thi #{exam_id} không tồn tại")

        bank_id = exam["bank_id"]
        q_list = self.questions.get(bank_id, [])
        keys = {q["id"]: q["answer_key"] for q in q_list}
        pts = {q["id"]: q["points"] for q in q_list}

        if submitted_answers is None:
            submitted_answers = self.get_student_submissions(exam_id, student_id)

        student_questions = self.load_exam_for_student(exam_id, student_id)
        allocated_qids = {q["question_id"] for q in student_questions}

        total_score = 0.0
        correct_count = 0
        for qid, chosen_orig in submitted_answers.items():
            if (not allocated_qids or qid in allocated_qids) and keys.get(qid) == chosen_orig:
                total_score += pts.get(qid, 1.0)
                correct_count += 1

        total_questions = len(allocated_qids) if allocated_qids else (exam["question_count"] or len(keys))
        return float(round(total_score, 2)), correct_count, total_questions

    def get_exam_max_points(self, exam_id: int, student_id: str) -> float:
        exam = self.get_exam(exam_id)
        if not exam:
            return 0.0
        student_questions = self.load_exam_for_student(exam_id, student_id)
        allocated_qids = {q["question_id"] for q in student_questions}
        bank_id = exam["bank_id"]
        q_list = self.questions.get(bank_id, [])
        pts = {q["id"]: float(q.get("points", 1.0)) for q in q_list}
        if allocated_qids:
            return float(round(sum(pts.get(qid, 1.0) for qid in allocated_qids), 2))
        return float(round(sum(pts.values()) if pts else float(exam.get("question_count") or len(q_list) or 1.0), 2))

    def get_exam_student_ids(self, exam_id: int) -> List[str]:
        return list({s_id for (ex_id, s_id, _qid) in self.submissions.keys() if ex_id == exam_id})

    def save_student_result(
        self,
        exam_id: int,
        student_id: str,
        exam_score: float,
        violation_penalty: float,
        final_score: float,
        violation_count: int,
        status: str,
        submitted: bool = False,
    ) -> None:
        self.student_results[(exam_id, student_id.strip())] = {
            "exam_id": exam_id,
            "student_id": student_id.strip(),
            "exam_score": exam_score,
            "violation_penalty": violation_penalty,
            "final_score": final_score,
            "violation_count": violation_count,
            "status": status,
            "submitted_at": "2026-10-17T00:30:00Z" if submitted else None,
        }


# Global repository instance management
_global_repository: Optional[ExamRepository] = None


def set_global_repository(repo: ExamRepository) -> None:
    global _global_repository
    _global_repository = repo


def get_exam_repository() -> ExamRepository:
    """
    Trả về thể hiện Repository:
    - Nếu RPMC_REPO=memory -> dùng InMemoryExamRepository.
    - Nếu RPMC_DB_DSN đã đặt mà kết nối lỗi -> BÁO LỖI VÀ DỪNG (không tự fallback).
    - Nếu không cấu hình DSN và không yêu cầu memory -> mặc định dùng InMemory (cho standalone local test).
    """
    global _global_repository
    if _global_repository is not None:
        return _global_repository

    # 1. Người dùng chủ động chọn chế độ in-memory
    repo_mode = os.environ.get("RPMC_REPO", "").strip().lower()
    if repo_mode == "memory":
        _global_repository = InMemoryExamRepository()
        return _global_repository

    # 2. Đọc cấu hình RPMC_DB_DSN từ biến môi trường hoặc file .env
    dsn = os.environ.get("RPMC_DB_DSN")
    if not dsn:
        env = Path(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("RPMC_DB_DSN="):
                    dsn = line.split("=", 1)[1].strip()
                    break

    # Nếu ĐÃ ĐẶT RPMC_DB_DSN thì BẮT BUỘC phải kết nối thành công, nếu lỗi thì dừng ngay lập tức!
    if dsn:
        try:
            repo = PostgresExamRepository(dsn)
            with repo._get_connection():
                pass
            _global_repository = repo
            return _global_repository
        except Exception as exc:
            raise RuntimeError(
                f"[RPMC PostgreSQL Error] Cấu hình RPMC_DB_DSN={dsn!r} nhưng kết nối thất bại: {exc}. "
                f"Vui lòng kiểm tra dịch vụ PostgreSQL hoặc đặt RPMC_REPO=memory nếu muốn chạy bộ nhớ tạm."
            ) from exc

    # 3. Mặc định fallback in-memory nếu chưa từng cấu hình DSN
    _global_repository = InMemoryExamRepository()
    return _global_repository
