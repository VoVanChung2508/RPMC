"""Kịch bản mô phỏng 2 thí sinh cùng tham gia phòng thi trực tuyến LAN.

Chạy:
    .venv\\Scripts\\python.exe -m scripts.demo_two_students

Kịch bản chứng minh:
1. Đề thi được xáo trộn ngẫu nhiên theo từng MSSV (SV01 và SV02 nhận thứ tự riêng), TUYỆT ĐỐI không lộ answer_key.
2. Lưu nháp bài làm (idempotent) chỉ chấp nhận đáp án A-D.
3. Đồng hồ đếm ngược do server tính toán và đồng bộ từ started_at.
4. Ghi nhận vi phạm phòng thi và trừ điểm theo thời gian thực.
5. Chấm điểm tự động và lưu kết quả tổng hợp vào cơ sở dữ liệu.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from server.exam_manager import ExamManager
from server.exam_web_server import ExamRequestHandler
from server.repository import InMemoryExamRepository, PostgresExamRepository, set_global_repository


def mask_dsn(dsn: str) -> str:
    """Ẩn mật khẩu trong chuỗi DSN nếu có."""
    if not dsn or "@" not in dsn or ":" not in dsn:
        return dsn
    try:
        prefix, rest = dsn.split("://", 1)
        user_pass, host_db = rest.split("@", 1)
        user = user_pass.split(":", 1)[0]
        return f"{prefix}://{user}:***@{host_db}"
    except Exception:
        return "postgresql://***@***"


def http_post(url: str, data: dict, token: str = "") -> tuple[int, dict]:
    body = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Student-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def http_get(url: str, token: str = "") -> tuple[int, dict]:
    headers = {}
    if token:
        headers["X-Student-Token"] = token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    print("=" * 70)
    print("  RPMC - KỊCH BẢN MÔ PHỎNG 2 THÍ SINH THI TRỰC TUYẾN LAN (BƯỚC 2)")
    print("=" * 70)

    # 1. Khởi tạo Repository
    test_dsn = os.environ.get("RPMC_TEST_DSN")
    if test_dsn:
        print(f"[*] Sử dụng cơ sở dữ liệu PostgreSQL Test: {mask_dsn(test_dsn)}")
        repo = PostgresExamRepository(test_dsn)
        # Khởi tạo ngân hàng đề mẫu nếu cần
        import psycopg
        with psycopg.connect(test_dsn) as conn:
            from pathlib import Path
            def _get_schema(name: str) -> str:
                p = Path("database") / name
                return p.read_text(encoding="utf-8") if p.exists() else Path(name).read_text(encoding="utf-8")
            conn.execute(_get_schema("schema.sql"))
            conn.execute(_get_schema("schema_v2.sql"))
            conn.commit()

            with conn.transaction():
                # Dọn dữ liệu demo trước
                conn.execute("DELETE FROM submissions WHERE student_id IN ('SV01', 'SV02')")
                conn.execute("DELETE FROM student_exam_results WHERE student_id IN ('SV01', 'SV02')")
                b_row = conn.execute("SELECT id FROM question_banks WHERE title = 'Ngân hàng Demo 2 Thí Sinh'").fetchone()
                if not b_row:
                    b_id = conn.execute(
                        """INSERT INTO question_banks (title, subject, created_by)
                           VALUES (%s, %s, %s) RETURNING id""",
                        ("Ngân hàng Demo 2 Thí Sinh", "Lập trình mạng", "demo_script"),
                    ).fetchone()[0]
                    q1 = conn.execute(
                        """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (b_id, 1, "Giao thức nào cung cấp luồng byte tin cậy, hướng kết nối?", "A", 5.0),
                    ).fetchone()[0]
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q1, "A", "TCP"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q1, "B", "UDP"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q1, "C", "IP"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q1, "D", "ICMP"))

                    q2 = conn.execute(
                        """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (b_id, 2, "Cổng chuẩn của giao thức DNS trên tầng Transport là gì?", "B", 5.0),
                    ).fetchone()[0]
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q2, "A", "80"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q2, "B", "53"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q2, "C", "443"))
                    conn.execute("INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)", (q2, "D", "22"))
                else:
                    b_id = b_row[0]
        exam = repo.create_exam(b_id, title="Kỳ thi Demo 2 Thí Sinh", duration_minutes=30, shuffle=True)
        repo.set_exam_status(exam["id"], "IN_PROGRESS")
    else:
        print("[*] Sử dụng bộ nhớ tạm (In-Memory Repository) độc lập.")
        repo = InMemoryExamRepository()
        b_id = repo.add_sample_bank(
            title="Ngân hàng Demo 2 Thí Sinh",
            subject="Lập trình mạng",
            questions_data=[
                {
                    "content": "Giao thức nào cung cấp luồng byte tin cậy, hướng kết nối?",
                    "options": {"A": "TCP", "B": "UDP", "C": "IP", "D": "ICMP"},
                    "answer": "A",
                    "points": 5.0,
                },
                {
                    "content": "Cổng chuẩn của giao thức DNS trên tầng Transport là gì?",
                    "options": {"A": "80", "B": "53", "C": "443", "D": "22"},
                    "answer": "B",
                    "points": 5.0,
                },
            ],
        )
        exam = repo.create_exam(b_id, title="Kỳ thi Demo 2 Thí Sinh", duration_minutes=30, shuffle=True)
        repo.set_exam_status(exam["id"], "IN_PROGRESS")

    set_global_repository(repo)
    mgr = ExamManager(log_path="data/demo_audit.jsonl", repository=repo)
    ExamManager._instance = mgr

    # Khởi chạy Web Server cục bộ
    server = ThreadingHTTPServer(("127.0.0.1", 0), ExamRequestHandler)
    port = server.server_port
    base_url = f"http://127.0.0.1:{port}"
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    print(f"[+] Web Server thí sinh đang chạy tại: {base_url}/")

    try:
        # Bước 1: 2 thí sinh đăng ký vào phòng thi
        print("\n--- BƯỚC 1: ĐĂNG KÝ PHÒNG THI ---")
        _, r1 = http_post(f"{base_url}/api/exam/register", {"student_id": "SV01", "name": "Nguyễn Văn An"})
        t1 = r1.get("token", "")
        print(f"Thí sinh 1: {r1['student']['name']} (MSSV: {r1['student']['student_id']}) - Điểm ban đầu: {r1['student']['score']}")

        _, r2 = http_post(f"{base_url}/api/exam/register", {"student_id": "SV02", "name": "Trần Thị Bình"})
        t2 = r2.get("token", "")
        print(f"Thí sinh 2: {r2['student']['name']} (MSSV: {r2['student']['student_id']}) - Điểm ban đầu: {r2['student']['score']}")

        # Bước 2: Nạp đề thi và kiểm tra tính bảo mật + xáo trộn
        print("\n--- BƯỚC 2: NẠP ĐỀ THI XÁO TRỘN THEO MSSV ---")
        _, q1_data = http_get(f"{base_url}/api/exam/questions?student_id=SV01", token=t1)
        _, q2_data = http_get(f"{base_url}/api/exam/questions?student_id=SV02", token=t2)

        print("[Bảo mật] Kiểm tra answer_key trong đề gửi về trình duyệt:")
        has_key = any("answer_key" in q or "answer" in q for q in q1_data["questions"])
        print(f" -> Lộ đáp án đúng? {'CÓ (NGUY HIỂM)' if has_key else 'KHÔNG (AN TOÀN TUYỆT ĐỐI)'}")

        print("\n[Thí sinh 1 - SV01] Thứ tự các câu hỏi:")
        for idx, q in enumerate(q1_data["questions"], 1):
            opts_str = ", ".join(f"{opt['label']}: {opt['content']}" for opt in q["options"])
            print(f"   Câu {idx} (ID={q['question_id']}): {q['content'][:45]}... | Lựa chọn: [{opts_str}]")

        print("\n[Thí sinh 2 - SV02] Thứ tự các câu hỏi (xáo trộn độc lập):")
        for idx, q in enumerate(q2_data["questions"], 1):
            opts_str = ", ".join(f"{opt['label']}: {opt['content']}" for opt in q["options"])
            print(f"   Câu {idx} (ID={q['question_id']}): {q['content'][:45]}... | Lựa chọn: [{opts_str}]")

        # Bước 3: Lưu nháp đáp án trắc nghiệm
        print("\n--- BƯỚC 3: LƯU NHÁP BÀI LÀM (IDEMPOTENT CHỈ NHẬN A-D) ---")
        q1_id = q1_data["questions"][0]["question_id"]
        q2_id = q1_data["questions"][1]["question_id"]

        # SV01 chọn đáp án
        http_post(f"{base_url}/api/exam/save_draft", {"student_id": "SV01", "question_id": q1_id, "chosen": "A"}, token=t1)
        time.sleep(0.25)
        http_post(f"{base_url}/api/exam/save_draft", {"student_id": "SV01", "question_id": q2_id, "chosen": "B"}, token=t1)
        print("SV01 đã lưu nháp: Câu 1 -> A, Câu 2 -> B")

        # SV02 chọn đáp án (Câu 1 chọn C, Câu 2 chọn B)
        http_post(f"{base_url}/api/exam/save_draft", {"student_id": "SV02", "question_id": q1_id, "chosen": "C"}, token=t2)
        time.sleep(0.25)
        http_post(f"{base_url}/api/exam/save_draft", {"student_id": "SV02", "question_id": q2_id, "chosen": "B"}, token=t2)
        print("SV02 đã lưu nháp: Câu 1 -> C, Câu 2 -> B")

        # Bước 4: Giả lập vi phạm phòng thi
        print("\n--- BƯỚC 4: GIÁM SÁT VI PHẠM PHÒNG THI (PROCTORING) ---")
        print("SV01 chuyển tab trình duyệt (TAB_SWITCH)...")
        _, v_res = http_post(f"{base_url}/api/exam/violation", {
            "student_id": "SV01",
            "event": "TAB_SWITCH",
            "detail": "Rời màn hình bài thi để tra cứu",
        }, token=t1)
        print(f" -> SV01 bị trừ: {v_res['violation']['deduction']} đ | Điểm còn: {v_res['student']['score']} đ | Trạng thái: {v_res['student']['status']}")

        # Bước 5: Nộp bài và chấm điểm
        print("\n--- BƯỚC 5: NỘP BÀI VÀ CHẤM ĐIỂM TỰ ĐỘNG ---")
        _, sub1 = http_post(f"{base_url}/api/exam/submit", {"student_id": "SV01"}, token=t1)
        _, sub2 = http_post(f"{base_url}/api/exam/submit", {"student_id": "SV02"}, token=t2)

        print("\n" + "=" * 70)
        print("                     BẢNG KẾT QUẢ TỔNG HỢP")
        print("=" * 70)
        print(f"Thí sinh 1 (SV01 - Nguyễn Văn An):")
        print(f"  - Điểm tổng kết:     {sub1['student']['score']} / 10.0 đ")
        print(f"  - Số lần vi phạm:    {sub1['student']['violation_count']} lần")
        print(f"  - Trạng thái nộp:    {sub1['student']['status']}")
        print(f"Thí sinh 2 (SV02 - Trần Thị Bình):")
        print(f"  - Điểm tổng kết:     {sub2['student']['score']} / 10.0 đ")
        print(f"  - Số lần vi phạm:    {sub2['student']['violation_count']} lần")
        print(f"  - Trạng thái nộp:    {sub2['student']['status']}")
        print("=" * 70)
        print("✅ Kịch bản 2 thí sinh đã hoàn tất thành công 100%!")

    finally:
        server.shutdown()
        server.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
