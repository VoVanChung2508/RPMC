import json
import os
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import exam_editor_server
from exam_editor_server import Handler


class TestExamEditorServer(unittest.TestCase):
    server: ThreadingHTTPServer
    server_thread: threading.Thread
    base_url: str

    @classmethod
    def setUpClass(cls):
        os.environ["RPMC_ADMIN_TOKEN"] = "test_admin_token_123456"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server_port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.server_port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _request(
        self,
        path: str,
        method: str = "GET",
        data: dict | bytes | None = None,
        headers: dict | None = None,
    ) -> tuple[int, dict | bytes, dict]:
        url = f"{self.base_url}{path}"
        req_headers = headers or {}
        body = None
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, bytes):
            body = data

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                resp_body = resp.read()
                resp_headers = dict(resp.headers)
        except urllib.error.HTTPError as exc:
            status = exc.code
            resp_body = exc.read()
            resp_headers = dict(exc.headers)

        parsed_data = resp_body
        if "application/json" in resp_headers.get("Content-Type", ""):
            try:
                parsed_data = json.loads(resp_body.decode("utf-8"))
            except Exception:
                pass
        return status, parsed_data, resp_headers

    def test_01_favicon_returns_204(self):
        """Kiểm tra GET /favicon.ico trả về 204 No Content, tránh lỗi 404 trên trình duyệt."""
        status, body, headers = self._request("/favicon.ico")
        self.assertEqual(status, 204)
        self.assertEqual(len(body), 0)

    def test_02_save_unauthorized_returns_401_json(self):
        """(c) Sai hoặc thiếu token: mong đợi HTTP 401 kèm phản hồi JSON rõ ràng."""
        status, body, _ = self._request(
            "/api/exam/save",
            method="POST",
            data={"title": "Đề Test", "questions": []},
            headers={"X-Admin-Token": "sai_token_quan_tri"},
        )
        self.assertEqual(status, 401)
        self.assertIsInstance(body, dict)
        self.assertIn("error", body)
        self.assertIn("Sai hoặc thiếu token", body["error"])

    def test_03_save_validation_error_returns_422_json(self):
        """(b) Đề thiếu đáp án đúng hoặc thiếu tên ngân hàng: mong đợi HTTP 422 JSON."""
        # Đề câu 1 chưa chọn đáp án đúng (answer = None)
        invalid_payload = {
            "title": "Ngân hàng đề LTM",
            "questions": [
                {
                    "content": "Giao thức nào là hướng kết nối?",
                    "options": {"A": "TCP", "B": "UDP", "C": "IP", "D": "ARP"},
                    "answer": None,
                }
            ],
        }
        status, body, _ = self._request(
            "/api/exam/save",
            method="POST",
            data=invalid_payload,
            headers={"X-Admin-Token": "test_admin_token_123456"},
        )
        self.assertEqual(status, 422)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("error"), "Đề còn lỗi")
        self.assertIn("errors", body)
        self.assertTrue(len(body["errors"]) > 0)

    def test_04_save_without_dsn_returns_500_json_not_empty_response(self):
        """
        (a) Khi thiếu cấu hình RPMC_DB_DSN:
        Server PHẢI trả về HTTP 500 JSON tiếng Việt chỉ cách khắc phục,
        TUYỆT ĐỐI KHÔNG được đóng kết nối rỗng (ERR_EMPTY_RESPONSE).
        Test được cô lập bằng patch, không phụ thuộc file .env hay database thật.
        """
        valid_payload = {
            "title": "Ngân hàng đề kiểm tra DSN",
            "questions": [
                {
                    "content": "Cổng mặc định HTTP là gì?",
                    "options": {"A": "80", "B": "443", "C": "22", "D": "21"},
                    "answer": "A",
                }
            ],
        }
        with unittest.mock.patch(
            "question_bank.get_dsn",
            side_effect=ValueError("Chưa cấu hình RPMC_DB_DSN trong file .env hoặc biến môi trường"),
        ):
            status, body, _ = self._request(
                "/api/exam/save",
                method="POST",
                data=valid_payload,
                headers={"X-Admin-Token": "test_admin_token_123456"},
            )
        self.assertEqual(status, 500)
        self.assertIsInstance(body, dict)
        self.assertIn("error", body)
        self.assertIn("RPMC_DB_DSN", body["error"])

    def test_05_save_with_test_dsn_success_and_cleanup(self):
        """
        Kiểm tra POST /api/exam/save thành công (HTTP 200) khi cấu hình RPMC_TEST_DSN.
        Chỉ kết nối database test (rpmc_test), tự động dọn sạch dữ liệu sau khi chạy.
        """
        test_dsn = os.environ.get("RPMC_TEST_DSN")
        if not test_dsn:
            raise unittest.SkipTest("Bỏ qua test vì không có biến RPMC_TEST_DSN")

        import psycopg
        from pathlib import Path

        # Đảm bảo schema đã được khởi tạo trong test database
        with psycopg.connect(test_dsn) as conn:
            def _get_schema(name: str) -> str:
                p = Path("database") / name
                return p.read_text(encoding="utf-8") if p.exists() else Path(name).read_text(encoding="utf-8")
            conn.execute(_get_schema("schema.sql"))
            conn.execute(_get_schema("schema_v2.sql"))
            conn.commit()

        test_title = "Ngân hàng đề Test Save Editor"

        # Dọn trước dữ liệu còn sót
        with psycopg.connect(test_dsn) as conn:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM submissions WHERE exam_id IN (SELECT id FROM exams WHERE bank_id IN (SELECT id FROM question_banks WHERE title = %s))",
                    (test_title,),
                )
                conn.execute(
                    "DELETE FROM student_exam_results WHERE exam_id IN (SELECT id FROM exams WHERE bank_id IN (SELECT id FROM question_banks WHERE title = %s))",
                    (test_title,),
                )
                conn.execute(
                    "DELETE FROM exams WHERE bank_id IN (SELECT id FROM question_banks WHERE title = %s)",
                    (test_title,),
                )
                conn.execute("DELETE FROM question_banks WHERE title = %s", (test_title,))

        payload = {
            "title": test_title,
            "subject": "Lập trình mạng",
            "filename": "de_test_save_editor.docx",
            "questions": [
                {
                    "content": "TCP là giao thức hướng kết nối hay không kết nối?",
                    "options": {
                        "A": "Hướng kết nối",
                        "B": "Không kết nối",
                        "C": "Broadcast",
                        "D": "Multicast",
                    },
                    "answer": "A",
                }
            ],
        }

        created_bank_id = None
        try:
            with unittest.mock.patch("question_bank.get_dsn", return_value=test_dsn):
                status, body, _ = self._request(
                    "/api/exam/save",
                    method="POST",
                    data=payload,
                    headers={"X-Admin-Token": "test_admin_token_123456"},
                )

            self.assertEqual(status, 200)
            self.assertIsInstance(body, dict)
            self.assertTrue(body.get("ok"))
            self.assertEqual(body.get("count"), 1)
            created_bank_id = body.get("bank_id")
            self.assertIsNotNone(created_bank_id)

            # Xác thực dữ liệu được lưu đúng trong database test (rpmc_test)
            with psycopg.connect(test_dsn) as conn:
                row = conn.execute(
                    "SELECT id, title, created_by FROM question_banks WHERE id = %s",
                    (created_bank_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[1], test_title)
                self.assertEqual(row[2], "exam-editor")
        finally:
            # Dọn dẹp dữ liệu sau khi test xong
            with psycopg.connect(test_dsn) as conn:
                with conn.transaction():
                    if created_bank_id:
                        conn.execute(
                            "DELETE FROM submissions WHERE exam_id IN (SELECT id FROM exams WHERE bank_id = %s)",
                            (created_bank_id,),
                        )
                        conn.execute(
                            "DELETE FROM student_exam_results WHERE exam_id IN (SELECT id FROM exams WHERE bank_id = %s)",
                            (created_bank_id,),
                        )
                        conn.execute(
                            "DELETE FROM exams WHERE bank_id = %s",
                            (created_bank_id,),
                        )
                        conn.execute("DELETE FROM question_banks WHERE id = %s", (created_bank_id,))
                    conn.execute("DELETE FROM question_banks WHERE title = %s", (test_title,))


if __name__ == "__main__":
    unittest.main()

