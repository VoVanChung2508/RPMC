"""Bộ kiểm tra tiền khởi động (Preflight Check) cho hệ thống RPMC.

Kiểm tra:
1. File cấu hình .env và các biến môi trường bắt buộc.
2. Cảnh báo bảo mật nếu còn sử dụng token mặc định.
3. Kết nối PostgreSQL và tự động tạo bảng (schema migration) nếu chưa có.
4. Kiểm tra các cổng mạng (8090, 8081, 8082) có bị chiếm dụng không.
5. Tự phát hiện IP mạng LAN và in banner / QR code hướng dẫn kết nối.
"""
from __future__ import annotations

import os
import re
import secrets
import socket
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ADMIN_TOKEN = "AdminTokenNgauNhien32KyTu"
DEFAULT_AGENT_TOKEN = "AgentTokenNgauNhien32KyTu"


def mask_dsn(dsn: str) -> str:
    """Che mật khẩu trong chuỗi kết nối DSN."""
    if not dsn:
        return ""
    return re.sub(r":([^:@/]+)@", ":******@", dsn)


def get_lan_ip() -> str:
    """Tự động phát hiện địa chỉ IPv4 trong mạng nội bộ (LAN / Wi-Fi)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def is_port_free(port: int, host: str = "0.0.0.0") -> bool:
    """Kiểm tra cổng mạng có đang rảnh không bằng cách thử bind tạm thời."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def check_env_file(env_path: Path = PROJECT_ROOT / ".env") -> tuple[bool, dict[str, str], list[str]]:
    """Kiểm tra sự tồn tại và tính hợp lệ của file .env."""
    warnings: list[str] = []
    if not env_path.exists():
        example_path = PROJECT_ROOT / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
            warnings.append("Chưa có file .env, hệ thống đã tự tạo .env từ .env.example.")
        else:
            return False, {}, ["Không tìm thấy file .env và .env.example."]

    content = env_path.read_text(encoding="utf-8")
    env_vars: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'\"")
        if k:
            env_vars[k] = v
            if k not in os.environ:
                os.environ[k] = v

    required_keys = ["RPMC_ADMIN_TOKEN", "RPMC_AGENT_TOKEN", "RPMC_SERVER_PORT", "EXAM_HTTP_PORT"]
    missing = [k for k in required_keys if not env_vars.get(k)]
    if missing:
        return False, env_vars, [f"Thiếu các biến cấu hình bắt buộc trong .env: {', '.join(missing)}"]

    # Cảnh báo token mặc định
    admin_tok = env_vars.get("RPMC_ADMIN_TOKEN", "")
    if admin_tok == DEFAULT_ADMIN_TOKEN:
        warnings.append(
            f"Đang sử dụng Admin Token mặc định ('{DEFAULT_ADMIN_TOKEN}'). "
            "Khuyến nghị chạy 'python rpmc.py init' để tự sinh token ngẫu nhiên bảo mật."
        )

    return True, env_vars, warnings


def check_database(auto_migrate: bool = True) -> tuple[bool, str]:
    """Kiểm tra kết nối PostgreSQL và tự động tạo bảng nếu chưa có."""
    dsn = os.environ.get("RPMC_DB_DSN", "").strip()
    if not dsn:
        return False, (
            "Chưa cấu hình RPMC_DB_DSN trong .env.\n"
            "👉 Cách sửa: Thêm dòng sau vào file .env:\n"
            "   RPMC_DB_DSN=postgresql://postgres:matkhau@localhost:5432/rpmc"
        )

    try:
        import psycopg
    except ImportError:
        return False, (
            "Chưa cài đặt thư viện psycopg.\n"
            "👉 Cách sửa: Chạy lệnh: pip install \"psycopg[binary]\""
        )

    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

            if auto_migrate:
                # Kiểm tra xem đã có các bảng chính chưa
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name IN ('question_banks', 'exams')"
                    )
                    count = cur.fetchone()[0]

                if count < 2:
                    try:
                        import question_bank
                        question_bank.init_schema(conn)
                        return True, "Kết nối PostgreSQL thành công. Đã tự động khởi tạo cấu trúc bảng (schema)."
                    except Exception as schema_err:
                        return False, f"Không thể khởi tạo cấu trúc bảng: {schema_err}"

            return True, f"Kết nối PostgreSQL thành công ({mask_dsn(dsn)})."
    except Exception as exc:
        err_msg = str(exc)
        return False, (
            f"Không thể kết nối tới cơ sở dữ liệu PostgreSQL ({mask_dsn(dsn)}).\n"
            f"Chi tiết: {type(exc).__name__}: {err_msg}\n"
            "👉 Hướng dẫn khắc phục:\n"
            "   1. Đảm bảo dịch vụ PostgreSQL đang chạy (Service 'postgresql-x64-XX' trên Windows).\n"
            "   2. Đảm bảo mật khẩu và cổng (mặc định 5432) trong RPMC_DB_DSN là chính xác.\n"
            "   3. Đảm bảo database 'rpmc' đã được tạo. Chạy lệnh:\n"
            "      psql -U postgres -c \"CREATE DATABASE rpmc;\""
        )


def check_ports(ports: list[int]) -> tuple[bool, list[str]]:
    """Kiểm tra danh sách cổng xem có cổng nào đang bị chiếm dụng không."""
    busy_ports = []
    for p in ports:
        if not is_port_free(p):
            busy_ports.append(p)
    if busy_ports:
        msgs = []
        for p in busy_ports:
            msgs.append(
                f"❌ Cổng {p} đang bị chiếm dụng bởi tiến trình khác!\n"
                f"   👉 Cách sửa: Đóng tiến trình cũ hoặc đổi cổng trong file .env."
            )
        return False, msgs
    return True, []


def print_banner(lan_ip: str, http_port: int, tcp_port: int, editor_port: Optional[int] = None) -> None:
    """In banner trực quan địa chỉ kết nối LAN cho thí sinh và giám thị."""
    divider = "=" * 70
    print(f"\n{divider}")
    print(" 🚀  RPMC - HỆ THỐNG QUẢN TRỊ TỪ XA & GIÁM SÁT THI TRỰC TUYẾN LAN")
    print(divider)
    print(f" 🌐  Thí sinh vào thi:     http://{lan_ip}:{http_port}/ (hoặc http://localhost:{http_port}/)")
    print(f" 🛡️  Giám thị kết nối:    {lan_ip}:{tcp_port} (hoặc 127.0.0.1:{tcp_port})")
    if editor_port:
        print(f" 📝  Soạn đề Word:        http://{lan_ip}:{editor_port}/ (hoặc http://localhost:{editor_port}/)")
    print(divider)

    # In QR code nếu thư viện qrcode đã được cài đặt (tùy chọn)
    try:
        import qrcode
        exam_url = f"http://{lan_ip}:{http_port}/"
        qr = qrcode.QRCode(border=1)
        qr.add_data(exam_url)
        print("\n📱 Quét mã QR dưới đây để vào thi nhanh trên điện thoại/máy tính bảng:")
        qr.print_ascii(invert=True)
    except Exception:
        pass
    print()


def run_preflight(check_ports_list: list[int] | None = None, require_db: bool = True) -> bool:
    """
    Thực thi toàn bộ quy trình tiền kiểm tra trước khi khởi động Server.
    Trả về True nếu sẵn sàng, False nếu phát hiện lỗi ngăn cản.
    """
    print("[*] Đang kiểm tra môi trường hệ thống (Preflight Check)...")

    # 1. Kiểm tra .env
    ok, env_vars, warnings = check_env_file()
    if not ok:
        print("\n❌ LỖI CẤU HÌNH .ENV:")
        for w in warnings:
            print(f"   {w}")
        return False

    for w in warnings:
        print(f"⚠️  {w}")

    # 2. Kiểm tra cổng mạng
    if check_ports_list:
        ports_ok, port_errors = check_ports(check_ports_list)
        if not ports_ok:
            print("\n❌ XUNG ĐỘT CỔNG MẠNG:")
            for pe in port_errors:
                print(f"   {pe}")
            return False

    # 3. Kiểm tra DB
    if require_db:
        db_ok, db_msg = check_database(auto_migrate=True)
        if not db_ok:
            print(f"\n❌ LỖI CƠ SỞ DỮ LIỆU:\n{db_msg}\n")
            return False
        else:
            print(f"✅ {db_msg}")

    print("✅ Kiểm tra môi trường hoàn tất: Hệ thống đã sẵn sàng.\n")
    return True


def init_tokens_in_env(env_path: Path = PROJECT_ROOT / ".env") -> None:
    """Tự động sinh token ngẫu nhiên bảo mật 32 ký tự nếu còn là giá trị mặc định."""
    if not env_path.exists():
        example_path = PROJECT_ROOT / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise FileNotFoundError("Không tìm thấy .env hoặc .env.example để khởi tạo.")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    admin_changed = False
    agent_changed = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("RPMC_ADMIN_TOKEN="):
            val = stripped.split("=", 1)[1].strip().strip("'\"")
            if not val or val == DEFAULT_ADMIN_TOKEN:
                new_token = secrets.token_urlsafe(32)
                new_lines.append(f"RPMC_ADMIN_TOKEN={new_token}")
                admin_changed = True
                continue
        elif stripped.startswith("RPMC_AGENT_TOKEN="):
            val = stripped.split("=", 1)[1].strip().strip("'\"")
            if not val or val == DEFAULT_AGENT_TOKEN:
                new_token = secrets.token_urlsafe(32)
                new_lines.append(f"RPMC_AGENT_TOKEN={new_token}")
                agent_changed = True
                continue
        new_lines.append(line)

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    if admin_changed or agent_changed:
        print("✅ Đã sinh token ngẫu nhiên bảo mật mới và cập nhật vào file .env.")
    else:
        print("ℹ️  File .env đã sử dụng token tùy chỉnh riêng, không cần thay đổi.")

