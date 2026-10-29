"""Lưu / đọc ngân hàng đề trên PostgreSQL (psycopg 3).

Cài đặt:  python -m pip install "psycopg[binary]" python-docx
Cấu hình: thêm vào .env
    RPMC_DB_DSN=postgresql://postgres:matkhau@localhost:5432/rpmc

Dùng:
    python -m question_bank init
    python -m question_bank import de_mang_may_tinh.docx --title "Mạng máy tính - GK" --subject "Lập trình mạng" --dry-run
    python -m question_bank import de_mang_may_tinh.docx --title "Mạng máy tính - GK"
    python -m question_bank list
"""
from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
from pathlib import Path
from typing import Optional

from docx_parser import ParsedQuestion, parse_docx, validate_questions

def _resolve_schema_path(filename: str) -> Path:
    db_path = Path(__file__).parent / "database" / filename
    if db_path.exists():
        return db_path
    return Path(__file__).with_name(filename)


SCHEMA_FILE = _resolve_schema_path("schema.sql")
SCHEMA_V2_FILE = _resolve_schema_path("schema_v2.sql")
SCHEMA_V3_FILE = _resolve_schema_path("schema_v3.sql")


def get_dsn() -> str:
    """
    Lấy chuỗi kết nối PostgreSQL từ biến môi trường hoặc file .env.
    Ném ValueError (không dùng SystemExit) để các caller như web server có thể xử lý an toàn.
    """
    dsn = os.environ.get("RPMC_DB_DSN")
    if not dsn:
        env = Path(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("RPMC_DB_DSN="):
                    dsn = line.split("=", 1)[1].strip()
                    break
    if not dsn:
        raise ValueError("Chưa cấu hình RPMC_DB_DSN trong file .env hoặc biến môi trường")
    return dsn


def init_schema(conn) -> None:
    """
    Khởi tạo hoặc cập nhật schema cơ sở dữ liệu theo đúng thứ tự:
    1. schema.sql: Cấu trúc ngân hàng đề, câu hỏi, bài nộp ban đầu
    2. schema_v2.sql: Cột trạng thái kỳ thi (status, is_active, started_at, ended_at) và bảng kết quả
    3. schema_v3.sql: Quy chế thi, vi phạm, quản lý máy trạm (agents) và kiểm toán băm SHA-256
    An toàn khi chạy lại nhiều lần (IF NOT EXISTS).
    """
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy file {SCHEMA_FILE.name}")
    schema1 = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.execute(schema1)

    if SCHEMA_V2_FILE.exists():
        schema2 = SCHEMA_V2_FILE.read_text(encoding="utf-8")
        conn.execute(schema2)

    if SCHEMA_V3_FILE.exists():
        schema3 = SCHEMA_V3_FILE.read_text(encoding="utf-8")
        conn.execute(schema3)

    conn.commit()


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def import_docx(conn, path: str, title: str, subject: str | None = None,
                created_by: str | None = None, points: float = 1.0) -> int:
    """Nhập thẳng file Word (không qua form). Trả về bank_id."""
    result = parse_docx(path)
    if not result.ok:
        raise ValueError("File có lỗi:\n- " + "\n- ".join(result.errors))
    return save_questions(conn, result.questions, title, subject,
                          source_file=Path(path).name, file_sha256=sha256_file(path),
                          created_by=created_by, points=points)


def save_questions(conn, questions: list[ParsedQuestion], title: str,
                   subject: str | None = None, source_file: str | None = None,
                   file_sha256: str | None = None, created_by: str | None = None,
                   points: float = 1.0) -> int:
    """Lưu danh sách câu hỏi (đã kiểm tra) vào ngân hàng đề trong MỘT transaction."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Thiếu tên ngân hàng đề")
    errors = validate_questions(questions)
    if errors:
        raise ValueError("Đề có lỗi:\n- " + "\n- ".join(errors))

    with conn.transaction():
        if file_sha256:
            row = conn.execute(
                "SELECT id FROM question_banks WHERE file_sha256 = %s", (file_sha256,)
            ).fetchone()
            if row:
                raise ValueError(f"File này đã được nhập trước đó (bank_id={row[0]})")

        bank_id = conn.execute(
            """INSERT INTO question_banks (title, subject, source_file, file_sha256, created_by)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (title, subject, source_file, file_sha256, created_by),
        ).fetchone()[0]

        for q in questions:
            qid = conn.execute(
                """INSERT INTO questions (bank_id, q_no, content, answer_key, points)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (bank_id, q.no, q.content, q.answer, points),
            ).fetchone()[0]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO question_options (question_id, label, content) VALUES (%s, %s, %s)",
                    [(qid, label, text) for label, text in sorted(q.options.items())],
                )
    return bank_id


def load_exam_for_student(conn, bank_id: int, student_id: str,
                          count: int | None = None, shuffle: bool = True) -> list[dict]:
    """Dựng đề cho một thí sinh. KHÔNG trả đáp án đúng ra ngoài (không có answer_key).

    Xáo trộn dùng seed theo MSSV nên mỗi thí sinh có thứ tự riêng nhưng ổn định
    khi tải lại trang. Nhãn đáp án được gán lại A-D theo thứ tự mới; trả kèm
    `orig` để server chấm điểm đối chiếu với answer_key.
    """
    rows = conn.execute(
        "SELECT id, q_no, content FROM questions WHERE bank_id = %s ORDER BY q_no", (bank_id,)
    ).fetchall()
    rng = random.Random(f"{bank_id}:{student_id}")
    if shuffle:
        rng.shuffle(rows)
    if count:
        rows = rows[:count]

    exam = []
    for qid, q_no, content in rows:
        opts = conn.execute(
            "SELECT label, content FROM question_options WHERE question_id = %s ORDER BY label",
            (qid,),
        ).fetchall()
        if shuffle:
            rng.shuffle(opts)
        exam.append({
            "question_id": qid,
            "content": content,
            "options": [
                {"label": "ABCD"[i], "orig": orig, "content": text}
                for i, (orig, text) in enumerate(opts)
            ],
        })
    return exam


def grade(conn, bank_id: int, answers: dict[int, str]) -> float:
    """answers: {question_id: nhãn GỐC (orig) mà thí sinh chọn}. Trả về tổng điểm."""
    keys = dict(conn.execute(
        "SELECT id, answer_key FROM questions WHERE bank_id = %s", (bank_id,)
    ).fetchall())
    pts = dict(conn.execute(
        "SELECT id, points FROM questions WHERE bank_id = %s", (bank_id,)
    ).fetchall())
    return float(sum(pts[q] for q, a in answers.items() if keys.get(q) == a))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="question_bank")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="tạo bảng (schema.sql + schema_v2.sql)")
    sub.add_parser("list", help="liệt kê ngân hàng đề")
    imp = sub.add_parser("import", help="nhập file .docx")
    imp.add_argument("file")
    imp.add_argument("--title", required=True)
    imp.add_argument("--subject")
    imp.add_argument("--dry-run", action="store_true", help="chỉ kiểm tra file, không ghi DB")
    args = ap.parse_args(argv)

    if args.cmd == "import" and args.dry_run:
        res = parse_docx(args.file)
        print(f"Đọc được {len(res.questions)} câu.")
        for e in res.errors:
            print("  LỖI:", e)
        return 0 if res.ok else 1

    try:
        import psycopg
    except ImportError:
        print("[LỖI] Chưa cài đặt thư viện 'psycopg'. Vui lòng chạy:", file=sys.stderr)
        print("      .venv\\Scripts\\python.exe -m pip install \"psycopg[binary]\"", file=sys.stderr)
        return 1

    try:
        dsn = get_dsn()
    except ValueError as e:
        print(f"[LỖI] {e}", file=sys.stderr)
        print("      Hãy cấu hình RPMC_DB_DSN trong file .env:", file=sys.stderr)
        print("      RPMC_DB_DSN=postgresql://postgres:matkhau@localhost:5432/rpmc", file=sys.stderr)
        return 1

    try:
        with psycopg.connect(dsn) as conn:
            if args.cmd == "init":
                init_schema(conn)
                print("✅ Đã áp dụng thành công schema.sql, schema_v2.sql và schema_v3.sql.")
            elif args.cmd == "list":
                for r in conn.execute(
                    """SELECT b.id, b.title, b.subject, count(q.id), b.created_at::date
                       FROM question_banks b LEFT JOIN questions q ON q.bank_id = b.id
                       GROUP BY b.id ORDER BY b.id"""
                ):
                    print(r)
            elif args.cmd == "import":
                try:
                    bank_id = import_docx(conn, args.file, args.title, args.subject)
                except ValueError as e:
                    print(f"[LỖI] {e}", file=sys.stderr)
                    return 1
                print(f"✅ Đã nhập thành công, bank_id = {bank_id}")
    except Exception as exc:
        print(f"[LỖI KẾT NỐI POSTGRESQL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
