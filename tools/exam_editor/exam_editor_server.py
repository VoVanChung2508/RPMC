"""Máy chủ nhỏ cho trang "Nhập đề từ Word" (người ra đề).

Luồng:  kéo thả .docx  ->  POST /api/exam/parse  ->  form tự điền, người ra đề chỉnh sửa
        ->  POST /api/exam/save  ->  lưu PostgreSQL.

Chạy:   python -m exam_editor_server
Mở:     http://127.0.0.1:8082/

Cấu hình (biến môi trường hoặc .env):
    RPMC_ADMIN_TOKEN    bắt buộc - người ra đề nhập token này trên trang
    RPMC_DB_DSN         chuỗi kết nối PostgreSQL (chỉ cần khi bấm Lưu)
    EXAM_EDITOR_PORT    mặc định 8082
    EXAM_EDITOR_HOST    mặc định 127.0.0.1 (đổi 0.0.0.0 nếu muốn mở cho máy khác trong LAN)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

# Đảm bảo nhận thư mục gốc dự án khi chạy file trực tiếp
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from docx_parser import MAX_FILE_BYTES, ParsedQuestion, parse_docx, validate_questions

HTML_FILE = Path(__file__).with_name("exam_editor.html")
MAX_JSON_BYTES = 2 * 1024 * 1024


def load_env() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def questions_to_json(questions: list[ParsedQuestion]) -> list[dict]:
    return [
        {
            "no": q.no,
            "content": q.content,
            "options": {k: q.options.get(k, "") for k in "ABCD"},
            "answer": q.answer,
        }
        for q in questions
    ]


def questions_from_json(items) -> list[ParsedQuestion]:
    if not isinstance(items, list):
        raise ValueError("Dữ liệu câu hỏi không hợp lệ")
    out = []
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict) or not isinstance(it.get("options"), dict):
            raise ValueError(f"Câu thứ {i}: dữ liệu không hợp lệ")
        opts = {
            k: str(v).strip()
            for k, v in it["options"].items()
            if k in ("A", "B", "C", "D") and str(v).strip()
        }
        ans = it.get("answer")
        out.append(ParsedQuestion(
            no=i,  # đánh số lại theo thứ tự trên form
            content=str(it.get("content", "")).strip(),
            options=opts,
            answer=ans if ans in ("A", "B", "C", "D") else None,
        ))
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "RPMCExamEditor/1.0"

    # ---- tiện ích ----
    def _send_json(self, status: int, obj) -> None:
        try:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _safe_send_error(self, status: int, message: str) -> None:
        """Đảm bảo luôn gửi phản hồi JSON có định dạng chuẩn, không bao giờ đóng kết nối rỗng."""
        self._send_json(status, {"error": message})

    def _authorized(self) -> bool:
        expected = os.environ.get("RPMC_ADMIN_TOKEN", "")
        given = self.headers.get("X-Admin-Token", "")
        return bool(expected) and hmac.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))

    def _read_body(self, limit: int) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > limit:
            self._send_json(413, {"error": "Dữ liệu gửi lên quá lớn hoặc không hợp lệ"})
            return None
        return self.rfile.read(length)

    # ---- routes tầng ngoài bọc try/except BaseException ----
    def do_GET(self):
        try:
            self._handle_get()
        except BaseException as exc:
            traceback.print_exc()
            self._safe_send_error(500, "Lỗi máy chủ nội bộ trong quá trình xử lý yêu cầu GET.")

    def do_POST(self):
        try:
            self._handle_post()
        except BaseException as exc:
            traceback.print_exc()
            self._safe_send_error(500, "Lỗi máy chủ nội bộ trong quá trình xử lý yêu cầu POST.")

    def _handle_get(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path in ("/", "/index.html"):
            if not HTML_FILE.exists():
                self._send_json(404, {"error": "Chưa có file exam_editor.html"})
                return
            body = HTML_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json(404, {"error": "Không tìm thấy đường dẫn"})

    def _handle_post(self):
        if not self._authorized():
            self._send_json(401, {"error": "Sai hoặc thiếu token quản trị (X-Admin-Token)"})
            return
        if self.path == "/api/exam/parse":
            self._parse()
        elif self.path == "/api/exam/save":
            self._save()
        else:
            self._send_json(404, {"error": "Không tìm thấy API endpoint"})

    def _parse(self):
        """Body = nội dung thô của file .docx; tên file gửi qua header X-Filename."""
        data = self._read_body(MAX_FILE_BYTES)
        if data is None:
            return
        filename = os.path.basename(unquote(self.headers.get("X-Filename", "de.docx")))[:255]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "upload.docx")
            Path(path).write_bytes(data)
            try:
                result = parse_docx(path)
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            except Exception:
                self._send_json(400, {"error": "Không đọc được file Word (file hỏng?)"})
                return
        self._send_json(200, {
            "filename": filename,
            "sha256": hashlib.sha256(data).hexdigest(),
            "questions": questions_to_json(result.questions),
            "errors": result.errors,
        })

    def _save(self):
        raw = self._read_body(MAX_JSON_BYTES)
        if raw is None:
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
            questions = questions_from_json(payload.get("questions"))
        except (ValueError, UnicodeDecodeError, AttributeError) as e:
            self._send_json(400, {"error": str(e) or "JSON không hợp lệ"})
            return

        errors = validate_questions(questions)
        title = str(payload.get("title", "")).strip()
        if not title:
            errors.insert(0, "Thiếu tên ngân hàng đề")
        if errors:
            self._send_json(422, {"error": "Đề còn lỗi", "errors": errors})
            return

        sha = payload.get("sha256")
        if sha is not None and not (isinstance(sha, str) and len(sha) == 64):
            sha = None

        # 1. Kiểm tra thư viện psycopg
        try:
            import psycopg
        except ImportError:
            self._send_json(500, {
                "error": "Máy chủ chưa cài đặt thư viện 'psycopg'. Vui lòng chạy lệnh: .venv\\Scripts\\python.exe -m pip install \"psycopg[binary]\""
            })
            return

        # 2. Kiểm tra cấu hình RPMC_DB_DSN
        try:
            import question_bank
            dsn = question_bank.get_dsn()
        except ValueError as e:
            self._send_json(500, {
                "error": "Chưa cấu hình RPMC_DB_DSN trong file .env hoặc biến môi trường."
            })
            return
        except Exception as e:
            self._send_json(500, {
                "error": f"Lỗi đọc cấu hình cơ sở dữ liệu: {type(e).__name__}"
            })
            return

        # 3. Kết nối PostgreSQL và lưu đề
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                bank_id = question_bank.save_questions(
                    conn, questions, title,
                    subject=(str(payload.get("subject", "")).strip() or None),
                    source_file=str(payload.get("filename", ""))[:255] or None,
                    file_sha256=sha, created_by="exam-editor",
                )
        except ValueError as e:
            self._send_json(409, {"error": str(e)})
            return
        except (psycopg.OperationalError, TimeoutError, OSError) as e:
            traceback.print_exc()
            self._send_json(500, {
                "error": "Không thể kết nối tới cơ sở dữ liệu PostgreSQL. Vui lòng kiểm tra dịch vụ PostgreSQL đang chạy và DSN trong .env."
            })
            return
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {
                "error": f"Lỗi cơ sở dữ liệu ({type(e).__name__}). Vui lòng kiểm tra log terminal của máy chủ."
            })
            return

        self._send_json(200, {"ok": True, "bank_id": bank_id, "count": len(questions)})

    def log_message(self, fmt, *args):  # log gọn
        print(f"[exam-editor] {self.address_string()} {fmt % args}")


def main() -> None:
    load_env()
    if not os.environ.get("RPMC_ADMIN_TOKEN"):
        raise SystemExit("Thiếu RPMC_ADMIN_TOKEN (đặt trong .env hoặc biến môi trường)")
    host = os.environ.get("EXAM_EDITOR_HOST", "127.0.0.1").strip()
    port = int(os.environ.get("EXAM_EDITOR_PORT", "8082"))
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Trang nhập đề: http://{host}:{port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
