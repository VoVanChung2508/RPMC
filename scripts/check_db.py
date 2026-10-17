"""Script kiểm tra môi trường cơ sở dữ liệu PostgreSQL cho RPMC.

Chạy:
    .venv\\Scripts\\python.exe -m scripts.check_db
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def mask_dsn(dsn: str) -> str:
    """Che mật khẩu trong chuỗi kết nối DSN."""
    # postgresql://username:password@host:port/database
    return re.sub(r":([^:@/]+)@", ":******@", dsn)


def get_configured_dsn() -> tuple[str | None, str]:
    """Tìm DSN từ biến môi trường hoặc file .env."""
    dsn = os.environ.get("RPMC_DB_DSN")
    source = "biến môi trường"
    if not dsn:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("RPMC_DB_DSN="):
                    dsn = line.split("=", 1)[1].strip()
                    source = "file .env"
                    break
    return dsn, source


def main() -> int:
    print("=" * 65)
    print("      RPMC - KIỂM TRA MÔI TRƯỜNG CƠ SỞ DỮ LIỆU POSTGRESQL      ")
    print("=" * 65)

    all_passed = True

    # -------------------------------------------------------------
    # BƯỚC 1: Kiểm tra thư viện psycopg
    # -------------------------------------------------------------
    try:
        import psycopg
        print(f"✅ [1/4] Thư viện psycopg: ĐÃ CÀI ĐẶT (phiên bản {psycopg.__version__})")
    except ImportError:
        print("❌ [1/4] Thư viện psycopg: CHƯA CÀI ĐẶT")
        print("   👉 Gợi ý sửa:")
        print("      Chạy lệnh: .venv\\Scripts\\python.exe -m pip install \"psycopg[binary]\"")
        print("=" * 65)
        return 1

    # -------------------------------------------------------------
    # BƯỚC 2: Kiểm tra biến cấu hình RPMC_DB_DSN
    # -------------------------------------------------------------
    dsn, source = get_configured_dsn()
    if dsn:
        masked = mask_dsn(dsn)
        print(f"✅ [2/4] Cấu hình RPMC_DB_DSN: ĐÃ TÌM THẤY (nguồn: {source})")
        print(f"       DSN: {masked}")
    else:
        print("❌ [2/4] Cấu hình RPMC_DB_DSN: CHƯA CẤU HÌNH")
        print("   👉 Gợi ý sửa:")
        print("      Thêm dòng sau vào file .env (hoặc thiết lập biến môi trường):")
        print("      RPMC_DB_DSN=postgresql://postgres:matkhau@localhost:5432/rpmc")
        print("      (Lưu ý: nếu mật khẩu có ký tự đặc biệt, hãy mã hóa URL, ví dụ @ -> %40)")
        print("=" * 65)
        return 1

    # -------------------------------------------------------------
    # BƯỚC 3: Kiểm tra kết nối tới cơ sở dữ liệu PostgreSQL
    # -------------------------------------------------------------
    conn = None
    try:
        conn = psycopg.connect(dsn, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            res = cur.fetchone()
        print("✅ [3/4] Kết nối PostgreSQL: THÀNH CÔNG (SELECT 1 trả lời tốt)")
    except Exception as exc:
        all_passed = False
        print("❌ [3/4] Kết nối PostgreSQL: THẤT BẠI")
        print(f"       Chi tiết lỗi: {type(exc).__name__}: {exc}")
        print("   👉 Gợi ý sửa:")
        print("      1. Kiểm tra dịch vụ PostgreSQL đã được khởi động chưa (cổng 5432).")
        print("      2. Kiểm tra tên database trong DSN đã được tạo chưa (CREATE DATABASE rpmc;).")
        print("      3. Kiểm tra username/password trong file .env đã chính xác chưa.")
        print("=" * 65)
        return 1

    # -------------------------------------------------------------
    # BƯỚC 4: Kiểm tra các bảng & cột của schema.sql và schema_v2.sql
    # -------------------------------------------------------------
    required_tables = [
        "question_banks",
        "questions",
        "question_options",
        "exams",
        "submissions",
        "student_exam_results",
    ]
    required_exam_columns = ["status", "is_active", "started_at", "ended_at"]

    try:
        with conn.cursor() as cur:
            # Lấy danh sách các bảng hiện có trong public schema
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            existing_tables = {row[0] for row in cur.fetchall()}

            missing_tables = [t for t in required_tables if t not in existing_tables]

            missing_columns = []
            if "exams" in existing_tables:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'exams'
                    """
                )
                existing_exam_cols = {row[0] for row in cur.fetchall()}
                missing_columns = [c for c in required_exam_columns if c not in existing_exam_cols]

        if not missing_tables and not missing_columns:
            print("✅ [4/4] Bảng cơ sở dữ liệu: ĐẦY ĐỦ BẢNG VÀ CỘT")
            print("       Đã kiểm tra: " + ", ".join(required_tables))
        else:
            all_passed = False
            print("❌ [4/4] Bảng cơ sở dữ liệu: CHƯA ĐẦY ĐỦ")
            if missing_tables:
                print("       Bảng còn thiếu: " + ", ".join(missing_tables))
            if missing_columns:
                print("       Cột còn thiếu trong bảng 'exams': " + ", ".join(missing_columns))
            print("   👉 Gợi ý sửa:")
            print("      Chạy lệnh sau để khởi tạo toàn bộ schema:")
            print("      .venv\\Scripts\\python.exe -m question_bank init")
    except Exception as exc:
        all_passed = False
        print(f"❌ [4/4] Kiểm tra bảng thất bại: {exc}")
    finally:
        if conn:
            conn.close()

    print("=" * 65)
    if all_passed:
        print("🎉 TẤT CẢ KIỂM TRA ĐỀU ĐẠT! Cơ sở dữ liệu đã sẵn sàng cho RPMC.")
        return 0
    else:
        print("⚠️  Có bước kiểm tra chưa đạt. Vui lòng thực hiện theo gợi ý ở trên.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
