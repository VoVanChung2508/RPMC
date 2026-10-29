import os
import unittest
from pathlib import Path

from server.exam_manager import ExamManager
from server.repository import (
    ExamRepository,
    InMemoryExamRepository,
    PostgresExamRepository,
    get_exam_repository,
    set_global_repository,
)


class TestExamRepository(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryExamRepository()
        set_global_repository(self.repo)
        # Tạo sẵn ngân hàng đề mẫu với 5 câu hỏi (mỗi câu 2 điểm)
        self.bank_id = self.repo.add_sample_bank(
            title="Ngân hàng Lập trình mạng GK",
            subject="Lập trình mạng",
            questions_data=[
                {
                    "content": "Giao thức nào là hướng kết nối?",
                    "options": {"A": "UDP", "B": "TCP", "C": "ICMP", "D": "ARP"},
                    "answer": "B",
                    "points": 2.0,
                },
                {
                    "content": "Cổng mặc định của HTTP là gì?",
                    "options": {"A": "21", "B": "22", "C": "80", "D": "443"},
                    "answer": "C",
                    "points": 2.0,
                },
                {
                    "content": "Header nhị phân RPMC dài bao nhiêu byte?",
                    "options": {"A": "8 bytes", "B": "12 bytes", "C": "16 bytes", "D": "20 bytes"},
                    "answer": "B",
                    "points": 2.0,
                },
                {
                    "content": "Bắt tay 3 bước TCP kết thúc bằng cờ nào?",
                    "options": {"A": "SYN", "B": "FIN", "C": "ACK", "D": "RST"},
                    "answer": "C",
                    "points": 2.0,
                },
                {
                    "content": "Tầng nào chịu trách nhiệm định tuyến IP?",
                    "options": {"A": "Data Link", "B": "Network", "C": "Transport", "D": "Application"},
                    "answer": "B",
                    "points": 2.0,
                },
            ],
        )

    def test_01_list_and_get_question_banks(self):
        banks = self.repo.list_question_banks()
        self.assertEqual(len(banks), 1)
        self.assertEqual(banks[0]["id"], self.bank_id)
        self.assertEqual(banks[0]["question_count"], 5)

        bank = self.repo.get_question_bank(self.bank_id)
        self.assertIsNotNone(bank)
        self.assertEqual(bank["title"], "Ngân hàng Lập trình mạng GK")

    def test_02_create_exam_validations(self):
        # Tên rỗng -> Lỗi
        with self.assertRaises(ValueError):
            self.repo.create_exam(self.bank_id, title="   ")

        # Thời gian <= 0 -> Lỗi
        with self.assertRaises(ValueError):
            self.repo.create_exam(self.bank_id, title="Thi GK", duration_minutes=0)

        # Ngân hàng không tồn tại -> Lỗi
        with self.assertRaises(ValueError):
            self.repo.create_exam(9999, title="Thi GK")

        # Hợp lệ
        exam = self.repo.create_exam(
            bank_id=self.bank_id,
            title="Thi Giữa Kỳ Lập Trình Mạng",
            duration_minutes=60,
            question_count=3,
            shuffle=True,
        )
        self.assertIsNotNone(exam.get("id"))
        self.assertEqual(exam["title"], "Thi Giữa Kỳ Lập Trình Mạng")
        self.assertEqual(exam["duration_minutes"], 60)
        self.assertEqual(exam["question_count"], 3)
        self.assertTrue(exam["shuffle"])
        self.assertEqual(exam["status"], "CREATED")
        self.assertTrue(exam["is_active"])

    def test_03_load_exam_for_student_security_and_shuffle(self):
        exam = self.repo.create_exam(self.bank_id, title="Thi GK", question_count=3, shuffle=True)
        exam_id = exam["id"]

        student_exam = self.repo.load_exam_for_student(exam_id, "SV01")
        self.assertEqual(len(student_exam), 3)

        # RÀNG BUỘC BẢO MẬT: TUYỆT ĐỐI không được chứa answer_key
        for q in student_exam:
            self.assertNotIn("answer_key", q)
            self.assertIn("question_id", q)
            self.assertIn("content", q)
            self.assertIn("options", q)
            self.assertEqual(len(q["options"]), 4)
            labels = [opt["label"] for opt in q["options"]]
            self.assertEqual(labels, ["A", "B", "C", "D"])
            # Mỗi option phải có orig để server đối chiếu khi chấm
            for opt in q["options"]:
                self.assertIn("orig", opt)
                self.assertIn(opt["orig"], ("A", "B", "C", "D"))

        # Kiểm tra tính ổn định: cùng 1 sinh viên tải lại thì thứ tự không đổi
        student_exam_reload = self.repo.load_exam_for_student(exam_id, "SV01")
        self.assertEqual(
            [q["question_id"] for q in student_exam],
            [q["question_id"] for q in student_exam_reload],
        )

    def test_04_save_draft_submission_and_overwrite(self):
        exam = self.repo.create_exam(self.bank_id, title="Thi GK", shuffle=False)
        exam_id = exam["id"]

        # Lưu nháp lần 1
        self.repo.save_submission(exam_id, "SV01", question_id=1, chosen="B")
        self.repo.save_submission(exam_id, "SV01", question_id=2, chosen="A")

        drafts = self.repo.get_student_submissions(exam_id, "SV01")
        self.assertEqual(drafts, {1: "B", 2: "A"})

        # GHI ĐÈ KHI CHỌN LẠI: sinh viên đổi câu 2 sang đáp án C
        self.repo.save_submission(exam_id, "SV01", question_id=2, chosen="C")
        drafts_updated = self.repo.get_student_submissions(exam_id, "SV01")
        self.assertEqual(drafts_updated, {1: "B", 2: "C"})

        # Validate nhãn không hợp lệ
        with self.assertRaises(ValueError):
            self.repo.save_submission(exam_id, "SV01", question_id=1, chosen="E")

    def test_05_grade_student(self):
        exam = self.repo.create_exam(self.bank_id, title="Thi GK", shuffle=False)
        exam_id = exam["id"]

        # Câu 1 (qid=1, đúng là B), Câu 2 (qid=2, đúng là C)
        self.repo.save_submission(exam_id, "SV01", question_id=1, chosen="B")  # đúng (+2.0)
        self.repo.save_submission(exam_id, "SV01", question_id=2, chosen="A")  # sai (+0.0)

        score, correct, total = self.repo.grade_student(exam_id, "SV01")
        self.assertEqual(score, 2.0)
        self.assertEqual(correct, 1)
        self.assertEqual(total, 5)

        # Sửa câu 2 sang đúng
        self.repo.save_submission(exam_id, "SV01", question_id=2, chosen="C")
        score, correct, total = self.repo.grade_student(exam_id, "SV01")
        self.assertEqual(score, 4.0)
        self.assertEqual(correct, 2)

    def test_06_active_exam_and_status_transitions(self):
        exam1 = self.repo.create_exam(self.bank_id, title="Kỳ thi 1")
        active = self.repo.get_active_exam()
        self.assertEqual(active["id"], exam1["id"])
        self.assertEqual(active["status"], "CREATED")
        self.assertIsNone(active["started_at"])

        # Chuyển trạng thái sang IN_PROGRESS
        exam1_running = self.repo.set_exam_status(exam1["id"], "IN_PROGRESS")
        self.assertEqual(exam1_running["status"], "IN_PROGRESS")
        self.assertIsNotNone(exam1_running["started_at"])

        # Chuyển sang FINISHED
        exam1_finished = self.repo.set_exam_status(exam1["id"], "FINISHED")
        self.assertEqual(exam1_finished["status"], "FINISHED")
        self.assertIsNotNone(exam1_finished["ended_at"])


class TestExamManagerWithRepository(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryExamRepository()
        self.bank_id = self.repo.add_sample_bank("Ngân hàng Đề Test")
        self.manager = ExamManager(log_path="data/test_audit.jsonl", repository=self.repo)

    def test_07_manager_exam_lifecycle(self):
        banks = self.manager.list_question_banks()
        self.assertEqual(len(banks), 1)

        exam = self.manager.create_exam(
            bank_id=self.bank_id,
            title="Kỳ thi Cuối kỳ Mạng",
            duration_minutes=90,
            question_count=5,
            shuffle=True,
            actor="PO_GIANG_VIEN",
        )
        self.assertEqual(exam["title"], "Kỳ thi Cuối kỳ Mạng")
        self.assertEqual(self.manager.config.duration_minutes, 90)

        active = self.manager.get_active_exam()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], exam["id"])

        # Đổi trạng thái qua manager
        res = self.manager.set_exam_status("IN_PROGRESS")
        self.assertEqual(self.manager.config.status.value, "IN_PROGRESS")

    def test_08_manager_restarts_preserves_active_exam(self):
        # Tạo kỳ thi
        exam = self.manager.create_exam(
            bank_id=self.bank_id,
            title="Kỳ thi Giữ nguyên sau Restart",
            duration_minutes=50,
            actor="PO",
        )
        self.manager.set_exam_status("IN_PROGRESS")

        # Giả lập restart server bằng cách tạo instance ExamManager mới cùng repo
        new_manager = ExamManager(log_path="data/test_audit.jsonl", repository=self.repo)
        active = new_manager.get_active_exam()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], exam["id"])
        self.assertEqual(active["title"], "Kỳ thi Giữ nguyên sau Restart")
        self.assertEqual(new_manager.config.duration_minutes, 50)
        self.assertEqual(new_manager.config.status.value, "IN_PROGRESS")


class TestRepositoryFactoryMode(unittest.TestCase):
    def setUp(self):
        set_global_repository(None)

    def tearDown(self):
        set_global_repository(None)
        if "RPMC_REPO" in os.environ:
            del os.environ["RPMC_REPO"]
        if "RPMC_DB_DSN" in os.environ:
            del os.environ["RPMC_DB_DSN"]
        os.environ["RPMC_REPO"] = "memory"

    def test_09_get_repo_fails_loudly_when_dsn_invalid(self):
        """Nếu RPMC_DB_DSN đã đặt mà kết nối lỗi thì PHẢI báo lỗi rõ ràng và dừng."""
        os.environ.pop("RPMC_REPO", None)
        os.environ["RPMC_DB_DSN"] = "postgresql://user_khong_ton_tai:mat_khau_sai@127.0.0.1:5432/db_ao"
        with self.assertRaises(RuntimeError) as ctx:
            get_exam_repository()
        self.assertIn("[RPMC PostgreSQL Error]", str(ctx.exception))

    def test_10_get_repo_uses_memory_when_explicitly_set(self):
        """InMemory chỉ dùng khi chủ động chọn RPMC_REPO=memory."""
        os.environ["RPMC_REPO"] = "memory"
        repo = get_exam_repository()
        self.assertIsInstance(repo, InMemoryExamRepository)


class TestPostgresExamRepositoryIntegration(unittest.TestCase):
    """
    Test tích hợp PostgreSQL thật.
    Chỉ chạy khi có cấu hình biến môi trường RPMC_TEST_DSN (ví dụ: postgresql://postgres:pass@localhost:5432/rpmc_test).
    Tự động dọn dẹp (cleanup) toàn bộ dữ liệu test sau khi chạy theo đúng thứ tự ràng buộc khóa ngoại.
    """

    test_bank_id: int | None = None
    test_exam_id: int | None = None
    TEST_BANK_TITLE = "Bank Test Postgres"
    TEST_EXAM_TITLE = "Kỳ Thi Postgres Thật"
    TEST_SUITE_ACTOR = "test_postgres_suite"

    @classmethod
    def _cleanup_test_data(cls, test_dsn: str):
        """
        Dọn dẹp triệt để theo đúng thứ tự quan hệ bảng (Foreign Key):
        1. submissions và student_exam_results của các kỳ thi test
        2. exams (theo bank_id test hoặc tiêu đề kỳ thi test)
        3. question_banks (questions & question_options tự cascade)
        """
        import psycopg
        with psycopg.connect(test_dsn) as conn:
            with conn.transaction():
                # 1. Thu thập bank_ids liên quan
                rows = conn.execute(
                    """SELECT id FROM question_banks 
                       WHERE created_by = %s OR title = %s""",
                    (cls.TEST_SUITE_ACTOR, cls.TEST_BANK_TITLE),
                ).fetchall()
                bank_ids = [r[0] for r in rows]
                if cls.test_bank_id and cls.test_bank_id not in bank_ids:
                    bank_ids.append(cls.test_bank_id)

                # 2. Thu thập exam_ids liên quan
                exam_ids = []
                if bank_ids:
                    e_rows = conn.execute(
                        """SELECT id FROM exams WHERE bank_id = ANY(%s) OR title = %s""",
                        (bank_ids, cls.TEST_EXAM_TITLE),
                    ).fetchall()
                    exam_ids = [r[0] for r in e_rows]
                else:
                    e_rows = conn.execute(
                        """SELECT id FROM exams WHERE title = %s""",
                        (cls.TEST_EXAM_TITLE,),
                    ).fetchall()
                    exam_ids = [r[0] for r in e_rows]

                if cls.test_exam_id and cls.test_exam_id not in exam_ids:
                    exam_ids.append(cls.test_exam_id)

                # 3. Dọn đúng thứ tự:
                # 3a. submissions và student_exam_results
                if exam_ids:
                    conn.execute("DELETE FROM submissions WHERE exam_id = ANY(%s)", (exam_ids,))
                    conn.execute("DELETE FROM student_exam_results WHERE exam_id = ANY(%s)", (exam_ids,))
                    # 3b. exams
                    conn.execute("DELETE FROM exams WHERE id = ANY(%s)", (exam_ids,))

                # 3c. question_banks
                if bank_ids:
                    conn.execute("DELETE FROM question_banks WHERE id = ANY(%s)", (bank_ids,))
                conn.execute(
                    "DELETE FROM question_banks WHERE created_by = %s OR title = %s",
                    (cls.TEST_SUITE_ACTOR, cls.TEST_BANK_TITLE),
                )

    @classmethod
    def setUpClass(cls):
        test_dsn = os.environ.get("RPMC_TEST_DSN")
        if not test_dsn:
            raise unittest.SkipTest("Bỏ qua test PostgreSQL vì không có biến RPMC_TEST_DSN")

        cls.repo = PostgresExamRepository(test_dsn)
        import psycopg
        # Khởi tạo schema từ database/schema.sql và database/schema_v2.sql
        with psycopg.connect(test_dsn) as conn:
            def _get_schema(name: str) -> str:
                p = Path("database") / name
                return p.read_text(encoding="utf-8") if p.exists() else Path(name).read_text(encoding="utf-8")
            conn.execute(_get_schema("schema.sql"))
            conn.execute(_get_schema("schema_v2.sql"))
            conn.commit()

        # Dọn dẹp dữ liệu sót từ lần chạy trước (dựa vào tiêu đề cố định), đảm bảo chạy lại nhiều lần vẫn xanh
        try:
            cls._cleanup_test_data(test_dsn)
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls):
        test_dsn = os.environ.get("RPMC_TEST_DSN")
        if not test_dsn:
            return
        try:
            cls._cleanup_test_data(test_dsn)
        finally:
            cls.test_bank_id = None
            cls.test_exam_id = None

    def test_11_postgres_full_flow_with_rollback_and_cleanup(self):
        import psycopg
        test_dsn = os.environ["RPMC_TEST_DSN"]

        try:
            # 1. Tạo Bank và Questions
            with psycopg.connect(test_dsn) as conn:
                with conn.transaction():
                    b_row = conn.execute(
                        """INSERT INTO question_banks (title, subject, created_by)
                           VALUES (%s, %s, %s) RETURNING id""",
                        (self.TEST_BANK_TITLE, "Lập trình mạng", self.TEST_SUITE_ACTOR),
                    ).fetchone()
                    self.__class__.test_bank_id = b_row[0]
                    bank_id = b_row[0]

                    # Thêm 2 câu hỏi mẫu
                    q1 = conn.execute(
                        """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (bank_id, 1, "TCP là giao thức gì?", "A", 2.5),
                    ).fetchone()[0]
                    conn.execute(
                        "INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)",
                        (q1, "A", "Hướng kết nối"),
                    )
                    conn.execute(
                        "INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)",
                        (q1, "B", "Không kết nối"),
                    )

                    q2 = conn.execute(
                        """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (bank_id, 2, "Cổng DNS chuẩn là bao nhiêu?", "B", 2.5),
                    ).fetchone()[0]
                    conn.execute(
                        "INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)",
                        (q2, "A", "80"),
                    )
                    conn.execute(
                        "INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)",
                        (q2, "B", "53"),
                    )

            # 2. Tạo kỳ thi
            exam = self.repo.create_exam(bank_id, title=self.TEST_EXAM_TITLE, duration_minutes=45, shuffle=True)
            self.__class__.test_exam_id = exam["id"]
            exam_id = exam["id"]
            self.assertEqual(exam["status"], "CREATED")
            self.assertTrue(exam["is_active"])

            # 3. Kích hoạt và load_exam_for_student (Bảo mật: Không lộ answer_key)
            loaded = self.repo.load_exam_for_student(exam_id, "SV_PG_01")
            self.assertEqual(len(loaded), 2)
            for q in loaded:
                self.assertNotIn("answer_key", q)

            # 4. save_submission & ghi đè khi chọn lại
            self.repo.save_submission(exam_id, "SV_PG_01", question_id=q1, chosen="B")  # sai
            self.repo.save_submission(exam_id, "SV_PG_01", question_id=q2, chosen="B")  # đúng
            # Ghi đè câu 1 sang A (đúng)
            self.repo.save_submission(exam_id, "SV_PG_01", question_id=q1, chosen="A")

            subs = self.repo.get_student_submissions(exam_id, "SV_PG_01")
            self.assertEqual(subs[q1], "A")
            self.assertEqual(subs[q2], "B")

            # 5. Chấm điểm trên PostgreSQL thật
            score, correct, total = self.repo.grade_student(exam_id, "SV_PG_01")
            self.assertEqual(score, 5.0)
            self.assertEqual(correct, 2)
            self.assertEqual(total, 2)

            # 6. Kiểm tra Rollback khi lỗi giữa chừng
            with self.assertRaises(Exception):
                with psycopg.connect(test_dsn) as conn:
                    with conn.transaction():
                        conn.execute(
                            """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                               VALUES (%s, %s, %s, %s, %s)""",
                            (bank_id, 99, "Câu hỏi lỗi", "Z", 1.0),  # Vi phạm CHECK (answer_key IN ('A','B','C','D'))
                        )
            # Chứng minh bản ghi không hề được tạo do đã rollback
            with psycopg.connect(test_dsn) as conn:
                cnt = conn.execute(
                    "SELECT count(*) FROM questions WHERE bank_id = %s AND q_no = 99",
                    (bank_id,),
                ).fetchone()[0]
                self.assertEqual(cnt, 0)
        finally:
            # Bọc trong try/finally để dọn được cả khi test thất bại giữa chừng
            try:
                self._cleanup_test_data(test_dsn)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

