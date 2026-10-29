import csv
import io
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from common.exam_models import StudentStatus
from server.exam_manager import ExamManager
from server.exam_web_server import ExamRequestHandler
from server.repository import (
    InMemoryExamRepository,
    PostgresExamRepository,
    set_global_repository,
)


class TestWebExamStep2(unittest.TestCase):
    server: ThreadingHTTPServer
    server_thread: threading.Thread
    base_url: str

    @classmethod
    def setUpClass(cls):
        # Đảm bảo cô lập hoàn toàn, dùng InMemoryExamRepository mặc định
        cls.repo = InMemoryExamRepository()
        set_global_repository(cls.repo)
        cls.bank_id = cls.repo.add_sample_bank(
            title="Ngân hàng Kiểm thử Bước 2",
            subject="Lập trình mạng",
            questions_data=[
                {
                    "content": "Giao thức TCP là gì?",
                    "options": {"A": "Hướng kết nối", "B": "Không kết nối", "C": "Broadcast", "D": "Multicast"},
                    "answer": "A",
                    "points": 1.0,
                },
                {
                    "content": "Cổng HTTP tiêu chuẩn là bao nhiêu?",
                    "options": {"A": "21", "B": "22", "C": "80", "D": "443"},
                    "answer": "C",
                    "points": 1.0,
                },
                {
                    "content": "Cổng DNS tiêu chuẩn trên UDP là?",
                    "options": {"A": "25", "B": "53", "C": "110", "D": "143"},
                    "answer": "B",
                    "points": 1.0,
                },
                {
                    "content": "Giao thức nào không hướng kết nối?",
                    "options": {"A": "TCP", "B": "SCTP", "C": "SSH", "D": "UDP"},
                    "answer": "D",
                    "points": 1.0,
                },
            ],
        )

        cls.exam_mgr = ExamManager(log_path="data/test_step2_audit.jsonl", repository=cls.repo)
        ExamManager._instance = cls.exam_mgr
        cls.exam = cls.repo.create_exam(cls.bank_id, title="Kỳ thi Thử Nghiệm Bước 2", duration_minutes=45, shuffle=True)
        cls.repo.set_exam_status(cls.exam["id"], "IN_PROGRESS")
        cls.exam_mgr.active_exam = cls.repo.get_active_exam()

        # Khởi động web server trên port ngẫu nhiên (port 0)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ExamRequestHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.exam_mgr.stop()
        cls.server.shutdown()
        cls.server.server_close()
        set_global_repository(None)
        ExamManager._instance = None
        if os.path.exists("data/test_step2_audit.jsonl"):
            try:
                os.remove("data/test_step2_audit.jsonl")
            except OSError:
                pass

    def setUp(self):
        from common.exam_models import ExamStatus
        self.repo.set_exam_status(self.exam["id"], "IN_PROGRESS")
        self.exam_mgr.active_exam = self.repo.get_exam(self.exam["id"])
        self.exam_mgr.config.status = ExamStatus.IN_PROGRESS

    def _request(
        self,
        path: str,
        method: str = "GET",
        data: dict | None = None,
        token: str | None = None,
    ) -> tuple[int, dict | str]:
        url = f"{self.base_url}{path}"
        headers = {}
        if token:
            headers["X-Student-Token"] = token
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")

        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return status, parsed

    def test_01_session_token_authentication_and_rejection(self):
        """1. PHIÊN THÍ SINH: Cấp token, bắt buộc token trên mọi API, từ chối khi thiếu/sai/mạo danh."""
        # Đăng ký thí sinh A và B
        s_a, r_a = self._request("/api/exam/register", method="POST", data={"student_id": "SV_A", "name": "Nguyễn Văn A"})
        self.assertEqual(s_a, 200)
        self.assertIn("token", r_a)
        token_a = r_a["token"]
        self.assertTrue(len(token_a) > 20)

        s_b, r_b = self._request("/api/exam/register", method="POST", data={"student_id": "SV_B", "name": "Trần Thị B"})
        self.assertEqual(s_b, 200)
        token_b = r_b["token"]
        self.assertNotEqual(token_a, token_b)

        # 1a. Không có token -> Bị từ chối (401)
        st_no_tok, _ = self._request("/api/exam/questions?student_id=SV_A")
        self.assertEqual(st_no_tok, 401)

        st_no_tok_save, _ = self._request("/api/exam/save_draft", method="POST", data={"student_id": "SV_A", "question_id": 1, "chosen": "A"})
        self.assertEqual(st_no_tok_save, 401)

        st_no_tok_sub, _ = self._request("/api/exam/submissions?student_id=SV_A")
        self.assertEqual(st_no_tok_sub, 401)

        st_no_tok_status, _ = self._request("/api/exam/status?student_id=SV_A")
        self.assertEqual(st_no_tok_status, 401)

        st_no_tok_submit, _ = self._request("/api/exam/submit", method="POST", data={"student_id": "SV_A"})
        self.assertEqual(st_no_tok_submit, 401)

        # 1b. Token sai/giả mạo -> Bị từ chối (401)
        st_bad_tok, _ = self._request("/api/exam/questions?student_id=SV_A", token="fake_token_1234567890")
        self.assertEqual(st_bad_tok, 401)

        # 1c. Thí sinh A dùng token của mình nhưng gửi MSSV của B -> Bị từ chối (403)
        st_mismatch_q, _ = self._request("/api/exam/questions?student_id=SV_B", token=token_a)
        self.assertEqual(st_mismatch_q, 403)

        st_mismatch_save, _ = self._request(
            "/api/exam/save_draft",
            method="POST",
            data={"student_id": "SV_B", "question_id": 1, "chosen": "A"},
            token=token_a,
        )
        self.assertEqual(st_mismatch_save, 403)

        # 1d. Thí sinh A dùng token hợp lệ của mình -> Thành công 200 (không phụ thuộc client_id)
        st_ok_q, data_q = self._request("/api/exam/questions?student_id=SV_A", token=token_a)
        self.assertEqual(st_ok_q, 200)
        self.assertIn("questions", data_q)

        # Bỏ qua student_id, server tự nhận diện theo token
        st_ok_no_id, _ = self._request("/api/exam/questions", token=token_a)
        self.assertEqual(st_ok_no_id, 200)

    def test_02_rate_limit_save_draft(self):
        """1 (tiếp). Giới hạn tần suất cơ bản cho save_draft (Rate Limit 0.2s -> 429)."""
        _, r = self._request("/api/exam/register", method="POST", data={"student_id": "SV_SPEED", "name": "Thí sinh bấm nhanh"})
        token = r["token"]
        qid = self.repo.questions[self.bank_id][0]["id"]

        # Gọi lần 1: thành công
        s1, _ = self._request(
            "/api/exam/save_draft",
            method="POST",
            data={"question_id": qid, "chosen": "A"},
            token=token,
        )
        self.assertEqual(s1, 200)

        # Gọi lần 2 ngay lập tức (<0.2s): Bị chặn 429 Too Many Requests
        s2, res2 = self._request(
            "/api/exam/save_draft",
            method="POST",
            data={"question_id": qid, "chosen": "B"},
            token=token,
        )
        self.assertEqual(s2, 429)
        self.assertIn("Rate Limit", res2.get("error", ""))

        # Sau khi chờ đủ thời gian (>0.25s) -> lưu lại thành công
        time.sleep(0.25)
        s3, _ = self._request(
            "/api/exam/save_draft",
            method="POST",
            data={"question_id": qid, "chosen": "B"},
            token=token,
        )
        self.assertEqual(s3, 200)

    def test_03_question_allocation_validation(self):
        """4. TÍNH HỢP LỆ CỦA CÂU HỎI: Chỉ nhận question_id thuộc tập câu đã giao cho thí sinh đó."""
        # Tạo thêm 1 ngân hàng khác với câu hỏi riêng (ID khác)
        other_bank = self.repo.add_sample_bank(
            title="Ngân hàng khác",
            subject="Khác",
            questions_data=[{"content": "Câu hỏi ngân hàng khác?", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "A"}],
        )
        foreign_qid = self.repo.questions[other_bank][0]["id"]

        _, r = self._request("/api/exam/register", method="POST", data={"student_id": "SV_VALID_Q", "name": "Kiểm tra câu hỏi"})
        token = r["token"]

        # Gửi question_id của ngân hàng khác hoặc câu không nằm trong đề -> Bị từ chối (400)
        s_foreign, res_foreign = self._request(
            "/api/exam/save_draft",
            method="POST",
            data={"question_id": foreign_qid, "chosen": "A"},
            token=token,
        )
        self.assertEqual(s_foreign, 400)
        self.assertIn("không thuộc đề thi", res_foreign.get("error", ""))

        # Gửi question_id hoàn toàn không tồn tại (999999) -> 400
        time.sleep(0.25)
        s_fake, res_fake = self._request(
            "/api/exam/save_draft",
            method="POST",
            data={"question_id": 999999, "chosen": "A"},
            token=token,
        )
        self.assertEqual(s_fake, 400)

    def test_04_scoring_scale_normalization_concrete_numbers(self):
        """
        3. THANG ĐIỂM: Quy đổi về cùng thang với initial_score (10.0).
        Công thức:
          exam_score = (tổng điểm đúng / tổng điểm tối đa của đề) * initial_score
          final = max(0, exam_score - điểm_trừ_vi_phạm)
        Test cụ thể: Đề có 4 câu (tổng điểm tối đa = 4.0), làm đúng 3/4 câu -> exam_score = 7.5.
        Bị 1 vi phạm trừ 1.0 -> final_score = 6.5.
        """
        # Cấu hình điểm khởi đầu 10.0, trừ 1.0 đ/lỗi vi phạm
        self.exam_mgr.update_config({"initial_score": 10.0, "penalty_per_violation": 1.0})

        _, r = self._request("/api/exam/register", method="POST", data={"student_id": "SV_SCORE_TEST", "name": "Thí sinh tính điểm"})
        token = r["token"]

        # Nạp đề để biết 4 câu hỏi
        _, q_data = self._request("/api/exam/questions", token=token)
        questions = q_data["questions"]
        self.assertEqual(len(questions), 4)

        # Trả lời 3 câu đúng, 1 câu sai: tra cứu đáp án đúng theo question_id (độc lập với thứ tự xáo trộn)
        key_by_qid = {q["id"]: q["answer_key"] for q in self.repo.questions[self.bank_id]}
        time.sleep(0.25)
        for idx, q in enumerate(questions):
            qid = q["question_id"]
            if idx < 3:
                # 3 câu đầu chọn đáp án đúng
                correct_ans = key_by_qid[qid]
                self._request("/api/exam/save_draft", method="POST", data={"question_id": qid, "chosen": correct_ans}, token=token)
            else:
                # Câu thứ 4 chọn đáp án sai
                wrong_ans = "B" if key_by_qid[qid] == "A" else "A"
                self._request("/api/exam/save_draft", method="POST", data={"question_id": qid, "chosen": wrong_ans}, token=token)
            time.sleep(0.25)

        # Giả lập 1 vi phạm phòng thi (trừ 1.0)
        self.exam_mgr.record_violation("SV_SCORE_TEST", "TAB_SWITCH", "Rời màn hình")

        # Nộp bài
        s_sub, res_sub = self._request("/api/exam/submit", method="POST", token=token)
        self.assertEqual(s_sub, 200)

        # Kiểm tra kết quả:
        # exam_score = 3/4 * 10.0 = 7.5
        # final_score = max(0, 7.5 - 1.0) = 6.5
        student_data = res_sub["student"]
        self.assertEqual(student_data["score"], 6.5)

        # Kiểm tra dữ liệu lưu trong repository
        stored = self.repo.student_results.get((self.exam["id"], "SV_SCORE_TEST"))
        self.assertIsNotNone(stored)
        self.assertEqual(stored["exam_score"], 7.5)
        self.assertEqual(stored["violation_penalty"], 1.0)
        self.assertEqual(stored["final_score"], 6.5)
        self.assertEqual(stored["violation_count"], 1)

    def test_05_server_background_timer_fake_clock_and_idempotent(self):
        """
        2. TỰ THU BÀI PHÍA SERVER: Hẹn giờ nền chốt kỳ thi tại started_at + duration.
        Test bằng ĐỒNG HỒ GIẢ (không sleep thật), kiểm tra tính IDEMPOTENT (chấm 2 lần không trùng lặp).
        """
        # Tạo kỳ thi với started_at cụ thể
        exam = self.repo.create_exam(self.bank_id, title="Kỳ thi Đồng Hồ Giả", duration_minutes=30)
        exam_id = exam["id"]
        self.repo.set_exam_status(exam_id, "IN_PROGRESS")
        self.exam_mgr.active_exam = self.repo.get_exam(exam_id)

        # Đăng ký thí sinh và lưu nháp
        _, r = self._request("/api/exam/register", method="POST", data={"student_id": "SV_AUTO_SUBMIT", "name": "Thí sinh tự thu bài"})
        token = r["token"]
        qid = self.repo.questions[self.bank_id][0]["id"]
        time.sleep(0.25)
        self._request("/api/exam/save_draft", method="POST", data={"question_id": qid, "chosen": "A"}, token=token)

        started_at = 10000.0  # Giả lập mốc thời gian bắt đầu
        # Patch started_at của kỳ thi
        self.exam_mgr.active_exam["started_at"] = started_at
        duration_sec = 30 * 60  # 1800s

        # Trường hợp 1: Đồng hồ giả tại t = 10000 + 1000s (chưa hết giờ) -> Chưa chốt
        finalized = self.exam_mgr.check_and_finalize_expired_exams(now=started_at + 1000.0)
        self.assertEqual(len(finalized), 0)
        self.assertEqual(self.exam_mgr.get_active_exam()["status"], "IN_PROGRESS")

        # Trường hợp 2: Đồng hồ giả tại t = 10000 + 1805s (quá hạn 5s) -> Tự động chốt và thu bài
        finalized = self.exam_mgr.check_and_finalize_expired_exams(now=started_at + duration_sec + 5.0)
        self.assertIn(exam_id, finalized)
        self.assertEqual(self.exam_mgr.get_active_exam()["status"], "FINISHED")

        # Thí sinh tự động được thu bài và có kết quả trong repository
        res_first = self.repo.student_results.get((exam_id, "SV_AUTO_SUBMIT"))
        self.assertIsNotNone(res_first)
        self.assertEqual(res_first["status"], "SUBMITTED")

        # Trường hợp 3: IDEMPOTENT - Gọi lại lần 2 tại t = 10000 + 2000s -> Không tạo kết quả đôi
        finalized_2 = self.exam_mgr.check_and_finalize_expired_exams(now=started_at + duration_sec + 200.0)
        self.assertEqual(len(finalized_2), 0)

        # Chấm lại trực tiếp bằng submit_exam -> Vẫn giữ nguyên 1 bản ghi duy nhất (Upsert)
        self.exam_mgr.submit_exam("SV_AUTO_SUBMIT")
        res_second = self.repo.student_results.get((exam_id, "SV_AUTO_SUBMIT"))
        self.assertEqual(res_first["final_score"], res_second["final_score"])

    def test_06_server_restart_auto_finalize_expired_exams(self):
        """2 (tiếp). Khi server khởi động lại thì tự chốt các kỳ thi IN_PROGRESS đã quá hạn."""
        # Giả lập kỳ thi IN_PROGRESS bị quá hạn trước khi server khởi động
        expired_exam = self.repo.create_exam(self.bank_id, title="Kỳ thi Quá Hạn Treo", duration_minutes=30)
        self.repo.set_exam_status(expired_exam["id"], "IN_PROGRESS")
        # Ghi nhận bài làm nháp của thí sinh
        self.repo.save_submission(expired_exam["id"], "SV_RESTART", question_id=1, chosen="A")

        # Khởi động lại ExamManager mới (giả lập restart server)
        # Tại thời điểm time.time(), kỳ thi với started_at = 1000.0 sẽ bị quá hạn
        with patch.object(self.repo, "list_exams", return_value=[
            {
                "id": expired_exam["id"],
                "bank_id": self.bank_id,
                "title": "Kỳ thi Quá Hạn Treo",
                "status": "IN_PROGRESS",
                "duration_minutes": 30,
                "started_at": 1000.0,  # Thời điểm trong quá khứ xa
            }
        ]):
            restarted_mgr = ExamManager(log_path="data/test_step2_restart.jsonl", repository=self.repo)
            try:
                # Kỳ thi quá hạn đã được tự động chốt về FINISHED
                status_in_repo = self.repo.get_exam(expired_exam["id"])["status"]
                self.assertEqual(status_in_repo, "FINISHED")

                # Bài làm của SV_RESTART đã được tự động chấm và lưu kết quả
                res = self.repo.student_results.get((expired_exam["id"], "SV_RESTART"))
                self.assertIsNotNone(res)
                self.assertEqual(res["status"], "SUBMITTED")
            finally:
                restarted_mgr.stop()
                if os.path.exists("data/test_step2_restart.jsonl"):
                    try:
                        os.remove("data/test_step2_restart.jsonl")
                    except OSError:
                        pass

    def test_07_load_questions_shuffled_by_mssv_no_answer_key(self):
        """Đề thi được xáo trộn theo MSSV và TUYỆT ĐỐI không chứa answer_key."""
        _, r1 = self._request("/api/exam/register", method="POST", data={"student_id": "SV_SHUF_1", "name": "SV 1"})
        t1 = r1["token"]
        _, r2 = self._request("/api/exam/register", method="POST", data={"student_id": "SV_SHUF_2", "name": "SV 2"})
        t2 = r2["token"]

        s1, d1 = self._request("/api/exam/questions", token=t1)
        self.assertEqual(s1, 200)
        s2, d2 = self._request("/api/exam/questions", token=t2)
        self.assertEqual(s2, 200)

        for q in d1["questions"]:
            self.assertNotIn("answer_key", q)
            self.assertNotIn("answer", q)
            for opt in q["options"]:
                self.assertNotIn("answer_key", opt)

    def test_08_restore_submissions_on_f5(self):
        """Khôi phục đáp án khi F5."""
        _, r = self._request("/api/exam/register", method="POST", data={"student_id": "SV_F5", "name": "Thí sinh F5"})
        token = r["token"]
        qid1 = self.repo.questions[self.bank_id][0]["id"]
        qid2 = self.repo.questions[self.bank_id][1]["id"]

        time.sleep(0.25)
        self._request("/api/exam/save_draft", method="POST", data={"question_id": qid1, "chosen": "A"}, token=token)
        time.sleep(0.25)
        self._request("/api/exam/save_draft", method="POST", data={"question_id": qid2, "chosen": "C"}, token=token)

        # F5 tải lại trang: gọi /api/exam/status
        s, st_data = self._request("/api/exam/status", token=token)
        self.assertEqual(s, 200)
        self.assertEqual(st_data["submissions"].get(str(qid1)), "A")
        self.assertEqual(st_data["submissions"].get(str(qid2)), "C")

    def test_10_duplicate_registration_returns_409_and_reset_session_flow(self):
        """1. ĐĂNG KÝ LẠI CÙNG MSSV: 409 khi có phiên hợp lệ; Cấp lại phiên qua Console ghi audit log và vô hiệu token cũ."""
        sid = "SV_DUP_FLOW"
        # 1a. Đăng ký lần đầu -> 200, nhận token1
        s1, r1 = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Nguyễn Trùng Lặp"})
        self.assertEqual(s1, 200)
        token1 = r1["token"]
        self.assertTrue(len(token1) > 20)

        # 1b. Đăng ký lại cùng MSSV khi phiên đang hợp lệ -> 409 kèm thông báo tiếng Việt
        s2, r2 = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Nguyễn Trùng Lặp"})
        self.assertEqual(s2, 409)
        self.assertIn("Thí sinh đã đăng ký và đang có phiên thi hợp lệ", r2.get("error", ""))
        self.assertNotIn("token", r2)

        # Token cũ vẫn hoạt động bình thường trước khi được giám thị cấp lại
        s_chk, _ = self._request("/api/exam/questions", token=token1)
        self.assertEqual(s_chk, 200)

        # 1c. Giám thị bấm 'Cấp lại phiên' (/api/exam/reset_session)
        s_reset, r_reset = self._request(
            "/api/exam/reset_session",
            method="POST",
            data={"student_id": sid, "reason": "Thí sinh đổi máy phòng thi"}
        )
        self.assertEqual(s_reset, 200)
        self.assertEqual(r_reset["status"], "ok")

        # Kiểm tra audit log: có ghi action SESSION_RESET và KHÔNG ghi token vào log
        audit_logs = self.exam_mgr.get_audit_logs()
        reset_logs = [
            log for log in audit_logs
            if log.get("action") == "SESSION_RESET" and (log.get("student_id") == sid or log.get("details", {}).get("student_id") == sid)
        ]
        self.assertTrue(len(reset_logs) >= 1)
        self.assertNotIn(token1, json.dumps(reset_logs))

        # Token cũ (token1) đã bị vô hiệu hóa -> gọi API trả về 401
        s_old, r_old = self._request("/api/exam/questions", token=token1)
        self.assertEqual(s_old, 401)

        # 1d. Thí sinh đăng ký lại sau khi giám thị cấp lại -> 200, nhận token mới (token2)
        s3, r3 = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Nguyễn Trùng Lặp"})
        self.assertEqual(s3, 200)
        token2 = r3["token"]
        self.assertNotEqual(token1, token2)

        # Token mới hoạt động bình thường
        s_new, _ = self._request("/api/exam/questions", token=token2)
        self.assertEqual(s_new, 200)

    def test_11_token_in_url_rejected_for_regular_apis_and_no_token_leak(self):
        """8. BẢO MẬT: Không chấp nhận token trong URL query cho API thường (chỉ cho SSE), không ghi token vào log."""
        sid = "SV_SEC_URL"
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Bảo Mật URL"})
        self.assertEqual(s_reg, 200)
        token = r_reg["token"]

        # Gửi token trong query URL cho GET /api/exam/questions (không có header) -> 401
        s_q, _ = self._request(f"/api/exam/questions?token={token}")
        self.assertEqual(s_q, 401)

        # Gửi token trong query URL cho POST /api/exam/save_draft (không có header) -> 401
        s_sd, _ = self._request(f"/api/exam/save_draft?token={token}", method="POST", data={"question_id": 1, "chosen": "A"})
        self.assertEqual(s_sd, 401)

        # Gửi token trong query URL cho GET /api/exam/submissions (không có header) -> 401
        s_sub, _ = self._request(f"/api/exam/submissions?token={token}")
        self.assertEqual(s_sub, 401)

        # Đảm bảo chuỗi token tuyệt đối không bị lộ vào file audit log
        logs = self.exam_mgr.get_audit_logs()
        all_logs_text = json.dumps(logs)
        self.assertNotIn(token, all_logs_text)

    def test_12_client_save_draft_rapid_clicking_simulation_and_queue(self):
        """2. 429 PHÍA CLIENT: Mô phỏng hàng đợi retry khi bấm liên tiếp, đảm bảo không mất đáp án."""
        sid = "SV_RAPID_CLICK"
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Thí Sinh Bấm Nhanh"})
        self.assertEqual(s_reg, 200)
        token = r_reg["token"]

        s_q, r_q = self._request("/api/exam/questions", token=token)
        self.assertEqual(s_q, 200)
        qids = [q["question_id"] for q in r_q["questions"]]
        self.assertTrue(len(qids) >= 4)

        # Mô phỏng thuật toán hàng đợi của client (web/app.js):
        # Người dùng bấm nhanh liên tiếp nhiều câu trong khoảng thời gian rất ngắn (< 0.2s)
        actions = [
            (qids[0], "A"),
            (qids[0], "B"),  # đổi ý câu 0
            (qids[1], "C"),
            (qids[2], "A"),
            (qids[3], "D"),
        ]

        # Xếp hàng và gửi tuần tự kèm retry khi gặp 429
        queue = []
        for qid, chosen in actions:
            # Nếu câu đã có trong hàng đợi chờ gửi, cập nhật đáp án mới nhất
            idx = next((i for i, item in enumerate(queue) if item["qid"] == qid), None)
            if idx is not None:
                queue[idx]["chosen"] = chosen
            else:
                queue.append({"qid": qid, "chosen": chosen, "retries": 0})

        # Xử lý hàng đợi
        while queue:
            item = queue[0]
            st, res = self._request(
                "/api/exam/save_draft",
                method="POST",
                data={"question_id": item["qid"], "chosen": item["chosen"]},
                token=token,
            )
            if st == 200:
                queue.pop(0)
            elif st == 429:
                item["retries"] += 1
                self.assertLessEqual(item["retries"], 5)
                time.sleep(0.22)  # Backoff chờ qua rate limit 0.2s
            else:
                self.fail(f"Lỗi không mong muốn khi lưu nháp: {st} {res}")

        # Kiểm tra đáp án đã lưu trên server: không câu nào bị mất, câu 0 nhận đáp án B
        s_chk, r_chk = self._request("/api/exam/submissions", token=token)
        self.assertEqual(s_chk, 200)
        subs = r_chk["submissions"]
        self.assertEqual(subs.get(str(qids[0])), "B")
        self.assertEqual(subs.get(str(qids[1])), "C")
        self.assertEqual(subs.get(str(qids[2])), "A")
        self.assertEqual(subs.get(str(qids[3])), "D")

    def test_13_background_timer_resilience_stop_and_singleton(self):
        """3. ExamBackgroundTimer: Try/except bọc lỗi repository tạm thời, không chạy 2 thread, dừng sạch khi server stop."""
        # 3a. Không chạy hai bản cùng lúc (Singleton thread)
        self.exam_mgr.stop()
        self.exam_mgr._start_background_timer()
        initial_threads = [t for t in threading.enumerate() if t.name == "ExamBackgroundTimer" and t.is_alive()]
        self.assertEqual(len(initial_threads), 1)

        # Gọi lại _start_background_timer: số thread không tăng lên
        self.exam_mgr._start_background_timer()
        current_threads = [t for t in threading.enumerate() if t.name == "ExamBackgroundTimer" and t.is_alive()]
        self.assertEqual(len(current_threads), 1)

        # 3b. Repository ném lỗi tạm thời: không làm sập tiến trình, ghi log lỗi và xử lý an toàn
        with patch.object(self.repo, "list_exams", side_effect=RuntimeError("Mất kết nối DB tạm thời")):
            # Hàm kiểm tra bắt được exception và tiếp tục bình thường
            res = self.exam_mgr.check_and_finalize_expired_exams()
            self.assertEqual(res, [])

        # Thread hẹn giờ nền vẫn còn sống bình thường
        self.assertTrue(current_threads[0].is_alive())

        # 3c. Dừng sạch khi server tắt
        self.exam_mgr.stop()
        time.sleep(0.3)
        self.assertFalse(self.exam_mgr._timer_thread.is_alive())

        # Khởi động lại timer để phục vụ các test khác
        self.exam_mgr._start_background_timer()

    def test_14_finalized_exam_records_all_registered_students_with_zero_score(self):
        """4. KHI CHỐT KỲ THI: Mọi thí sinh đã đăng ký đều phải có dòng trong kết quả (chưa làm câu nào -> exam_score = 0)."""
        sid = "SV_NO_ANSWER"
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Chưa Làm Bài"})
        self.assertEqual(s_reg, 200)

        # Chốt kỳ thi
        self.exam_mgr.set_exam_status("FINISHED", actor="SUPERVISOR_TEST")

        student = self.exam_mgr.students[sid]
        self.assertEqual(student.status, StudentStatus.SUBMITTED)
        self.assertEqual(student.exam_score, 0.0)
        self.assertEqual(student.violation_penalty, 0.0)
        self.assertEqual(student.score, 0.0)

        # Khôi phục trạng thái kỳ thi về IN_PROGRESS cho các bài test tiếp
        self.exam_mgr.set_exam_status("IN_PROGRESS", actor="TEST_RESET")

    def test_15_csv_export_format_and_exact_scores(self):
        """6. XUẤT CSV: Đủ các cột MSSV, Họ tên, Điểm bài làm, Điểm trừ vi phạm, Điểm cuối, Số lần vi phạm, Trạng thái. Test số liệu cụ thể (7.5 / 1.0 / 6.5)."""
        sid = "SV_CSV_VAL"
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Lê Văn Điểm Chuẩn"})
        self.assertEqual(s_reg, 200)
        token = r_reg["token"]

        s_q, r_q = self._request("/api/exam/questions", token=token)
        self.assertEqual(s_q, 200)
        questions = r_q["questions"]

        # Tra cứu đáp án đúng
        bank = self.repo.get_bank_questions(self.bank_id)
        key_by_qid = {q["id"]: q["answer_key"] for q in bank}

        # Trả lời 3/4 câu đúng -> Điểm bài làm = 3/4 * 10 = 7.5
        time.sleep(0.25)
        for idx, q in enumerate(questions):
            qid = q["question_id"]
            chosen = key_by_qid[qid] if idx < 3 else ("B" if key_by_qid[qid] == "A" else "A")
            s_save, _ = self._request("/api/exam/save_draft", method="POST", data={"question_id": qid, "chosen": chosen}, token=token)
            self.assertEqual(s_save, 200)
            time.sleep(0.22)

        # 1 vi phạm trừ 1.0 -> Điểm trừ = 1.0; Điểm cuối = 6.5
        self.exam_mgr.record_violation(sid, "BLUR", "Mất focus")

        # Nộp bài
        s_sub, r_sub = self._request("/api/exam/submit", method="POST", token=token)
        self.assertEqual(s_sub, 200)

        # Xuất CSV và kiểm tra định dạng + dữ liệu chính xác
        csv_text = self.exam_mgr.export_csv_report()
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertTrue(len(reader) >= 2)

        # Kiểm tra tiêu đề cột chuẩn xác theo yêu cầu
        headers = reader[0]
        expected_headers = ["MSSV", "Họ tên", "Điểm bài làm", "Điểm trừ vi phạm", "Điểm cuối", "Số lần vi phạm", "Trạng thái"]
        self.assertEqual(headers, expected_headers)

        # Tìm dòng của thí sinh SV_CSV_VAL
        row = next((r for r in reader[1:] if r[0] == sid), None)
        self.assertIsNotNone(row)
        self.assertEqual(row[0], sid)
        self.assertEqual(row[1], "Lê Văn Điểm Chuẩn")
        self.assertEqual(row[2], "7.5")   # Điểm bài làm
        self.assertEqual(row[3], "1.0")   # Điểm trừ vi phạm
        self.assertEqual(row[4], "6.5")   # Điểm cuối
        self.assertEqual(row[5], "1")     # Số lần vi phạm
        self.assertEqual(row[6], "SUBMITTED")

    def test_16_supervisor_console_fields_in_student_session(self):
        """5. CONSOLE GIÁM THỊ: Thêm cột 'Số câu đã làm' và 'Điểm bài làm' cập nhật theo thời gian thực."""
        sid = "SV_CONSOLE_METRICS"
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Thí Sinh Giám Sát"})
        self.assertEqual(s_reg, 200)
        token = r_reg["token"]

        s_q, r_q = self._request("/api/exam/questions", token=token)
        self.assertEqual(s_q, 200)
        questions = r_q["questions"]

        student_dict = self.exam_mgr.students[sid].to_dict()
        self.assertIn("answered_count", student_dict)
        self.assertIn("exam_score", student_dict)
        self.assertEqual(student_dict["answered_count"], 0)
        self.assertEqual(student_dict["exam_score"], 0.0)

        # Lưu 1 câu
        time.sleep(0.25)
        self._request("/api/exam/save_draft", method="POST", data={"question_id": questions[0]["question_id"], "chosen": "A"}, token=token)
        student_dict_after = self.exam_mgr.students[sid].to_dict()
        self.assertEqual(student_dict_after["answered_count"], 1)


class TestPostgresWebExamStep2Integration(unittest.TestCase):
    """
    Test tích hợp PostgreSQL thật cho toàn bộ luồng Web Thí sinh Bước 2.
    Chỉ chạy khi có biến RPMC_TEST_DSN (rpmc_test).
    TUYỆT ĐỐI không chạm vào database thật và tự dọn dẹp sau khi chạy.
    """

    test_bank_id: int | None = None
    test_exam_id: int | None = None
    server: ThreadingHTTPServer | None = None

    @classmethod
    def _cleanup(cls, test_dsn: str):
        import psycopg
        with psycopg.connect(test_dsn) as conn:
            with conn.transaction():
                conn.execute("""
                    DELETE FROM submissions
                    WHERE exam_id IN (
                        SELECT e.id FROM exams e
                        JOIN question_banks b ON e.bank_id = b.id
                        WHERE b.created_by = 'step2_postgres_test'
                    )
                """)
                conn.execute("""
                    DELETE FROM student_exam_results
                    WHERE exam_id IN (
                        SELECT e.id FROM exams e
                        JOIN question_banks b ON e.bank_id = b.id
                        WHERE b.created_by = 'step2_postgres_test'
                    )
                """)
                if cls.test_exam_id:
                    conn.execute("DELETE FROM submissions WHERE exam_id = %s", (cls.test_exam_id,))
                    conn.execute("DELETE FROM student_exam_results WHERE exam_id = %s", (cls.test_exam_id,))
                    conn.execute("DELETE FROM exams WHERE id = %s", (cls.test_exam_id,))

                conn.execute("""
                    DELETE FROM exams
                    WHERE bank_id IN (SELECT id FROM question_banks WHERE created_by = 'step2_postgres_test')
                """)
                if cls.test_bank_id:
                    conn.execute("DELETE FROM question_banks WHERE id = %s", (cls.test_bank_id,))
                conn.execute("DELETE FROM question_banks WHERE created_by = 'step2_postgres_test'")

    @classmethod
    def setUpClass(cls):
        test_dsn = os.environ.get("RPMC_TEST_DSN")
        if not test_dsn:
            raise unittest.SkipTest("Bỏ qua test vì không có biến RPMC_TEST_DSN")

        cls._cleanup(test_dsn)

        # Khởi tạo schema và nạp dữ liệu kỳ thi vào rpmc_test (4 câu hỏi)
        import psycopg
        with psycopg.connect(test_dsn) as conn:
            def _get_schema(name: str) -> str:
                p = Path("database") / name
                return p.read_text(encoding="utf-8") if p.exists() else Path(name).read_text(encoding="utf-8")
            conn.execute(_get_schema("schema.sql"))
            conn.execute(_get_schema("schema_v2.sql"))
            conn.commit()

            with conn.transaction():
                b_id = conn.execute(
                    """INSERT INTO question_banks (title, subject, created_by)
                       VALUES (%s, %s, %s) RETURNING id""",
                    ("Bank Step 2 PG Test", "Lập trình mạng", "step2_postgres_test"),
                ).fetchone()[0]
                cls.test_bank_id = b_id

                for q_no, (content, ans) in enumerate([
                    ("TCP là giao thức gì?", "A"),
                    ("Cổng DNS chuẩn là?", "B"),
                    ("Cổng HTTP chuẩn là?", "C"),
                    ("UDP là giao thức gì?", "D"),
                ], 1):
                    qid = conn.execute(
                        """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (b_id, q_no, content, ans, 1.0),
                    ).fetchone()[0]
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (qid, "A", "Đáp án A"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (qid, "B", "Đáp án B"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (qid, "C", "Đáp án C"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (qid, "D", "Đáp án D"))

        cls.repo = PostgresExamRepository(test_dsn)
        exam = cls.repo.create_exam(cls.test_bank_id, title="Kỳ Thi PG Bước 2", duration_minutes=45, shuffle=True)
        cls.repo.set_exam_status(exam["id"], "IN_PROGRESS")
        cls.test_exam_id = exam["id"]

        cls.exam_mgr = ExamManager(log_path="data/test_step2_pg_audit.jsonl", repository=cls.repo)
        ExamManager._instance = cls.exam_mgr

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ExamRequestHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        test_dsn = os.environ.get("RPMC_TEST_DSN")
        if cls.exam_mgr:
            cls.exam_mgr.stop()
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
        ExamManager._instance = None
        set_global_repository(None)
        if test_dsn:
            try:
                cls._cleanup(test_dsn)
            except Exception:
                pass
        if os.path.exists("data/test_step2_pg_audit.jsonl"):
            try:
                os.remove("data/test_step2_pg_audit.jsonl")
            except OSError:
                pass

    def _request(self, path: str, method: str = "GET", data: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
        url = f"{self.base_url}{path}"
        headers = {}
        if token:
            headers["X-Student-Token"] = token
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")

        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return status, parsed

    def test_09_postgres_full_student_web_lifecycle_and_idempotent(self):
        """Kiểm tra toàn bộ vòng đời làm bài thi trên PostgreSQL thật (rpmc_test) với Token, Thang điểm chuẩn và Idempotent Upsert."""
        import psycopg
        test_dsn = os.environ["RPMC_TEST_DSN"]

        # 1. Đăng ký nhận token
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": "SV_PG_FULL", "name": "Học sinh PG"})
        self.assertEqual(s_reg, 200)
        token = r_reg["token"]

        # 2. Bắt buộc token hợp lệ: thiếu token -> 401
        s_no_tok, _ = self._request("/api/exam/questions?student_id=SV_PG_FULL")
        self.assertEqual(s_no_tok, 401)

        # 3. Nạp đề thi qua token
        status, q_data = self._request("/api/exam/questions", token=token)
        self.assertEqual(status, 200)
        questions = q_data["questions"]
        self.assertEqual(len(questions), 4)

        # 4. Trả lời 3/4 câu đúng:
        # Tra cứu đáp án đúng theo question_id trong cơ sở dữ liệu để độc lập với thứ tự xáo trộn
        with psycopg.connect(test_dsn) as conn:
            q_rows = conn.execute("SELECT id, answer_key FROM questions WHERE bank_id = %s", (self.test_bank_id,)).fetchall()
            key_by_qid = {r[0]: r[1] for r in q_rows}

        time.sleep(0.25)
        for idx, q in enumerate(questions):
            qid = q["question_id"]
            if idx < 3:
                chosen = key_by_qid[qid]
            else:
                chosen = "B" if key_by_qid[qid] == "A" else "A"
            s_save, _ = self._request("/api/exam/save_draft", method="POST", data={"question_id": qid, "chosen": chosen}, token=token)
            self.assertEqual(s_save, 200)
            time.sleep(0.25)

        # 5. Giả lập 1 vi phạm trừ 1.0
        self.exam_mgr.record_violation("SV_PG_FULL", "BLUR", "Mất focus")

        # 6. Nộp bài lần 1:
        # exam_score = 3/4 * 10.0 = 7.5; final_score = max(0, 7.5 - 1.0) = 6.5
        sub_status, sub_res = self._request("/api/exam/submit", method="POST", token=token)
        self.assertEqual(sub_status, 200)
        self.assertEqual(sub_res["student"]["score"], 6.5)

        # 7. Nộp bài lần 2 (Idempotent): kết quả không bị nhân đôi trong database
        sub_status_2, sub_res_2 = self._request("/api/exam/submit", method="POST", token=token)
        self.assertEqual(sub_status_2, 200)
        self.assertEqual(sub_res_2["student"]["score"], 6.5)

        # 8. Xác minh trực tiếp trong database rpmc_test thật (chỉ có duy nhất 1 hàng, không trùng lặp)
        import psycopg
        with psycopg.connect(test_dsn) as conn:
            rows = conn.execute(
                "SELECT exam_score, violation_penalty, final_score, violation_count, status FROM student_exam_results WHERE student_id = %s",
                ("SV_PG_FULL",),
            ).fetchall()
            self.assertEqual(len(rows), 1)  # Đúng 1 hàng duy nhất
            row = rows[0]
            self.assertEqual(float(row[0]), 7.5)
            self.assertEqual(float(row[1]), 1.0)
            self.assertEqual(float(row[2]), 6.5)
            self.assertEqual(row[3], 1)
            self.assertEqual(row[4], "SUBMITTED")

    def test_17_postgres_unanswered_student_records_zero_score_on_finalize(self):
        """4 (PostgreSQL). KHI CHỐT KỲ THI: Thí sinh đăng ký nhưng chưa làm bài vẫn được ghi dòng vào student_exam_results với exam_score = 0."""
        test_dsn = os.environ.get("RPMC_TEST_DSN")
        if not test_dsn:
            self.skipTest("Bỏ qua vì không có biến RPMC_TEST_DSN")

        sid = "SV_PG_ZERO"
        s_reg, r_reg = self._request("/api/exam/register", method="POST", data={"student_id": sid, "name": "Nguyễn Không Làm Gì"})
        self.assertEqual(s_reg, 200)

        # Chốt kỳ thi
        self.exam_mgr.set_exam_status("FINISHED", actor="POSTGRES_TIMER_AUTO")

        # Xác minh trong bảng student_exam_results của PostgreSQL thật (rpmc_test)
        import psycopg
        with psycopg.connect(test_dsn) as conn:
            rows = conn.execute(
                "SELECT exam_score, violation_penalty, final_score, violation_count, status FROM student_exam_results WHERE student_id = %s",
                (sid,),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(float(row[0]), 0.0)  # exam_score = 0
            self.assertEqual(float(row[1]), 0.0)  # penalty = 0
            self.assertEqual(float(row[2]), 0.0)  # final_score = 0
            self.assertEqual(row[3], 0)           # 0 violations
            self.assertEqual(row[4], "SUBMITTED")


if __name__ == "__main__":
    unittest.main()
