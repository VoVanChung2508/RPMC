from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from common.exam_models import StudentSession
from server.exam_manager import ExamManager


class ExamRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: Optional[str] = None, **kwargs):
        if directory is None:
            # Point to web/ directory at project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            directory = os.path.join(base_dir, "web")
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:
        # Suppress noisy HTTP request logging
        pass

    def end_headers(self) -> None:
        # Enable CORS for LAN access
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Student-Token")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _extract_token(self, is_sse: bool = False, query: Optional[dict] = None) -> str:
        token = self.headers.get("X-Student-Token", "").strip()
        if not token:
            auth_header = self.headers.get("Authorization", "").strip()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
        # Chỉ chấp nhận token trong query param duy nhất cho SSE (/api/exam/events)
        if not token and is_sse and query and "token" in query:
            token = query["token"][0].strip()
        return token

    def _authenticate_student(
        self,
        query: dict,
        claimed_student_id: Optional[str] = None,
        is_sse: bool = False,
    ) -> tuple[Optional[StudentSession], Optional[tuple[int, dict]]]:
        token = self._extract_token(is_sse=is_sse, query=query)
        if not token:
            return None, (401, {"error": "Thiếu token phiên thí sinh (vui lòng gửi qua header X-Student-Token hoặc Authorization: Bearer)"})

        exam_mgr = ExamManager.get_instance()
        try:
            student = exam_mgr.verify_student_token(token, claimed_student_id)
            return student, None
        except PermissionError as exc:
            msg = str(exc)
            if claimed_student_id and "Token không thuộc về sinh viên" in msg:
                return None, (403, {"error": msg})
            return None, (401, {"error": msg})

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        exam_mgr = ExamManager.get_instance()

        if path == "/api/exam/config":
            cfg = exam_mgr.get_config().to_dict()
            exam = exam_mgr.get_active_exam()
            if exam:
                cfg["exam_title"] = exam.get("title", cfg.get("exam_title"))
                cfg["duration_minutes"] = exam.get("duration_minutes", cfg.get("duration_minutes"))
                cfg["exam_id"] = exam.get("id")
                cfg["status"] = exam.get("status", cfg.get("status"))
                cfg["started_at"] = exam.get("started_at")
            cfg["remaining_seconds"] = exam_mgr.get_remaining_seconds()
            cfg["server_time"] = time.time()
            self._send_json(200, cfg)
            return

        if path == "/api/exam/status":
            claimed_id = query.get("student_id", [""])[0].strip().upper() or None
            student, err = self._authenticate_student(query, claimed_student_id=claimed_id)
            if err:
                self._send_json(err[0], err[1])
                return
            student_id = student.student_id
            res = student.to_dict()
            res["remaining_seconds"] = exam_mgr.get_remaining_seconds()
            res["submissions"] = exam_mgr.get_student_submissions(student_id)
            exam = exam_mgr.get_active_exam()
            res["exam_status"] = exam.get("status") if exam else exam_mgr.get_config().status.value
            self._send_json(200, res)
            return

        if path == "/api/exam/questions":
            claimed_id = query.get("student_id", [""])[0].strip().upper() or None
            student, err = self._authenticate_student(query, claimed_student_id=claimed_id)
            if err:
                self._send_json(err[0], err[1])
                return
            student_id = student.student_id
            try:
                questions = exam_mgr.load_exam_for_student(student_id)
                exam = exam_mgr.get_active_exam()
                self._send_json(200, {
                    "status": "ok",
                    "exam_id": exam["id"] if exam else None,
                    "exam_title": exam["title"] if exam else exam_mgr.get_config().exam_title,
                    "duration_minutes": exam.get("duration_minutes", 45) if exam else 45,
                    "remaining_seconds": exam_mgr.get_remaining_seconds(),
                    "questions": questions,
                })
            except Exception as exc:
                self._send_json(500, {"error": f"Lỗi nạp đề thi: {exc}"})
            return

        if path == "/api/exam/submissions":
            claimed_id = query.get("student_id", [""])[0].strip().upper() or None
            student, err = self._authenticate_student(query, claimed_student_id=claimed_id)
            if err:
                self._send_json(err[0], err[1])
                return
            student_id = student.student_id
            subs = exam_mgr.get_student_submissions(student_id)
            self._send_json(200, {
                "status": "ok",
                "student_id": student_id,
                "submissions": subs,
            })
            return

        if path == "/api/exam/events":
            claimed_id = query.get("student_id", [""])[0].strip().upper() or None
            student, err = self._authenticate_student(query, claimed_student_id=claimed_id, is_sse=True)
            if err:
                self._send_json(err[0], err[1])
                return
            self._handle_sse(student.student_id)
            return

        # Fallback to serving static files from web/
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        exam_mgr = ExamManager.get_instance()
        client_ip = self.client_address[0]

        if path == "/api/exam/register":
            student_id = data.get("student_id", "").strip()
            name = data.get("name", "").strip()
            if not student_id:
                self._send_json(400, {"error": "Mã sinh viên không được để trống"})
                return
            try:
                exam_mgr.ensure_active_exam()
            except Exception:
                pass

            try:
                student = exam_mgr.register_student(student_id, name, client_ip)
            except FileExistsError as exc:
                self._send_json(409, {"error": str(exc)})
                return
            except Exception as exc:
                self._send_json(500, {"error": f"Lỗi đăng ký: {exc}"})
                return

            cfg = exam_mgr.get_config().to_dict()
            cfg["remaining_seconds"] = exam_mgr.get_remaining_seconds()
            self._send_json(200, {
                "status": "ok",
                "token": student.token,
                "student": student.to_dict(),
                "config": cfg,
            })
            return

        if path == "/api/exam/reset_session":
            student_id = data.get("student_id", "").strip().upper()
            reason = data.get("reason", "Giám thị cấp lại phiên thi")
            if not student_id:
                self._send_json(400, {"error": "Thiếu student_id"})
                return
            try:
                student = exam_mgr.reset_student_session(student_id, reason=reason, actor=f"SUPERVISOR_{client_ip}")
                self._send_json(200, {
                    "status": "ok",
                    "message": f"Đã cấp lại phiên thi cho thí sinh {student_id}. Thí sinh có thể đăng nhập lại.",
                })
            except KeyError:
                self._send_json(404, {"error": f"Sinh viên {student_id} chưa đăng ký vào phòng thi"})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
            return

        if path == "/api/exam/save_draft":
            claimed_id = data.get("student_id", "").strip().upper() or None
            student, err = self._authenticate_student({}, claimed_student_id=claimed_id)
            if err:
                self._send_json(err[0], err[1])
                return
            student_id = student.student_id
            question_id = data.get("question_id")
            chosen = str(data.get("chosen", "")).strip().upper()
            if question_id is None:
                self._send_json(400, {"error": "Thiếu question_id"})
                return
            try:
                qid = int(question_id)
            except ValueError:
                self._send_json(400, {"error": "question_id không hợp lệ"})
                return
            if chosen not in ("A", "B", "C", "D"):
                self._send_json(400, {"error": "Đáp án phải thuộc A, B, C hoặc D"})
                return

            try:
                exam_mgr.save_student_answer(student_id, qid, chosen)
                self._send_json(200, {"status": "ok", "question_id": qid, "chosen": chosen})
            except BufferError as exc:
                self._send_json(429, {"error": str(exc)})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                self._send_json(500, {"error": f"Lỗi lưu đáp án: {exc}"})
            return

        if path == "/api/exam/violation":
            claimed_id = data.get("student_id", "").strip().upper() or None
            student, err = self._authenticate_student({}, claimed_student_id=claimed_id)
            if err:
                self._send_json(err[0], err[1])
                return
            student_id = student.student_id
            event = data.get("event", "UNKNOWN")
            detail = data.get("detail", "Vi phạm không xác định")
            student, record = exam_mgr.record_violation(
                student_id=student_id,
                event_type=event,
                detail=detail,
                manual=False,
                actor=f"CLIENT_{client_ip}",
            )
            self._send_json(200, {
                "status": "ok",
                "student": student.to_dict(),
                "violation": record.to_dict(),
            })
            return

        if path == "/api/exam/submit":
            claimed_id = data.get("student_id", "").strip().upper() or None
            student, err = self._authenticate_student({}, claimed_student_id=claimed_id)
            if err:
                self._send_json(err[0], err[1])
                return
            student_id = student.student_id
            answers = data.get("answers", {})
            try:
                student = exam_mgr.submit_exam(student_id, answers)
                self._send_json(200, {
                    "status": "ok",
                    "student": student.to_dict(),
                    "final_score": student.score,
                })
            except KeyError:
                self._send_json(404, {"error": "Student not found"})
            except Exception as exc:
                self._send_json(500, {"error": f"Lỗi nộp bài: {exc}"})
            return

        self._send_json(404, {"error": "Endpoint not found"})

    def _handle_sse(self, student_id: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        exam_mgr = ExamManager.get_instance()
        q = exam_mgr.subscribe()
        try:
            # Send initial ping
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=1.0)
                    # Filter if student_id is specified and event has student target
                    target_id = event.get("student_id") or (event.get("student") or {}).get("student_id")
                    if student_id and target_id and target_id != student_id and event.get("type") in ("DIRECT_WARNING", "STUDENT_LOCKED"):
                        continue
                    event_data = f"data: {json.dumps(event)}\n\n".encode("utf-8")
                    self.wfile.write(event_data)
                    self.wfile.flush()
                except queue.Empty:
                    # Heartbeat comment to keep SSE connection alive
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            exam_mgr.unsubscribe(q)

    def _send_json(self, status_code: int, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ExamWebServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8081):
        self.host = host
        self.port = port
        self.server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        last_error = None
        # Thử cổng được chỉ định, nếu bị xung đột (WinError 10013 hoặc cổng bận) thì tự động chuyển cổng kế tiếp
        for candidate_port in range(self.port, self.port + 10):
            try:
                self.server = ThreadingHTTPServer((self.host, candidate_port), ExamRequestHandler)
                self.port = candidate_port
                self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self._thread.start()
                print(f"[HTTP] Exam Web Server running at http://{self.host}:{self.port}/")
                return
            except OSError as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("[HTTP] Exam Web Server stopped.")
