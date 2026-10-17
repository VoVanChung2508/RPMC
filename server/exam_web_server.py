from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/exam/config":
            self._send_json(200, ExamManager.get_instance().get_config().to_dict())
            return

        if path == "/api/exam/status":
            student_id = query.get("student_id", [""])[0]
            student = ExamManager.get_instance().get_student(student_id)
            if not student:
                self._send_json(404, {"error": "Student not found"})
                return
            self._send_json(200, student.to_dict())
            return

        if path == "/api/exam/events":
            self._handle_sse(query.get("student_id", [""])[0])
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
            student = exam_mgr.register_student(student_id, name, client_ip)
            self._send_json(200, {
                "status": "ok",
                "student": student.to_dict(),
                "config": exam_mgr.get_config().to_dict(),
            })
            return

        if path == "/api/exam/violation":
            student_id = data.get("student_id", "").strip()
            event = data.get("event", "UNKNOWN")
            detail = data.get("detail", "Vi phạm không xác định")
            if not student_id:
                self._send_json(400, {"error": "Missing student_id"})
                return
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
            student_id = data.get("student_id", "").strip()
            answers = data.get("answers", {})
            if not student_id:
                self._send_json(400, {"error": "Missing student_id"})
                return
            try:
                student = exam_mgr.submit_exam(student_id, answers)
                self._send_json(200, {
                    "status": "ok",
                    "student": student.to_dict(),
                })
            except KeyError:
                self._send_json(404, {"error": "Student not found"})
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
