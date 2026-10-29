#!/usr/bin/env python3
"""RPMC - Điểm vào quản trị và điều phối duy nhất (Unified Entrypoint).

Cách dùng:
    python rpmc.py all                Khởi động toàn bộ: Server -> Console -> Trình duyệt thí sinh
    python rpmc.py server             Chạy riêng Máy chủ Server (TCP Socket + Web thi + Soạn đề)
    python rpmc.py console            Chạy riêng Bảng điều khiển Giám thị / Quản trị (GUI)
    python rpmc.py agent              Chạy Agent máy trạm con để quản trị từ xa
    python rpmc.py editor             Chạy riêng Máy chủ soạn đề thi từ Word
    python rpmc.py demo               Chạy kịch bản mô phỏng 2 thí sinh thi cùng lúc
    python rpmc.py student <MSSV> "<Họ tên>" [--host IP] [--port PORT]
    python rpmc.py init               Sinh token bảo mật ngẫu nhiên và khởi tạo database
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.env import load_dotenv
from common.preflight import (
    DEFAULT_ADMIN_TOKEN,
    DEFAULT_AGENT_TOKEN,
    get_lan_ip,
    init_tokens_in_env,
    run_preflight,
)


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 12.0) -> bool:
    """Đợi cổng mạng mở và chấp nhận kết nối TCP (polling)."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def cmd_init(args) -> None:
    """Khởi tạo token bảo mật ngẫu nhiên và cấu trúc bảng database."""
    print("======================================================================")
    print("  RPMC - KHỞI TẠO HỆ THỐNG & BẢO MẬT TOKEN")
    print("======================================================================")
    init_tokens_in_env()
    load_dotenv()

    # Kiểm tra và nạp database
    dsn = os.environ.get("RPMC_DB_DSN", "")
    if dsn:
        try:
            import psycopg
            import question_bank
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                question_bank.init_schema(conn)
            print("✅ Đã kết nối PostgreSQL và khởi tạo cấu trúc bảng thành công!")
        except Exception as exc:
            print(f"⚠️  Chưa thể kết nối database ({exc}). Bạn có thể cấu hình lại DSN trong file .env.")
    else:
        print("ℹ️  Chưa cấu hình RPMC_DB_DSN trong .env.")
    print("======================================================================\n")


def cmd_server(args) -> None:
    """Khởi chạy Máy chủ RPMC Server."""
    from server.server_main import main as server_main
    # Truyền lại tham số nếu có
    sys.argv = [sys.argv[0]]
    if getattr(args, "no_editor", False):
        sys.argv.append("--no-editor")
    if getattr(args, "skip_preflight", False):
        sys.argv.append("--skip-preflight")
    server_main()


def cmd_console(args) -> None:
    """Khởi chạy Bảng điều khiển Console GUI."""
    from console.app import main as console_main
    console_main()


def cmd_agent(args) -> None:
    """Khởi chạy máy con Agent."""
    load_dotenv()
    from agent.agent_main import AgentClient
    host = args.host or os.environ.get("RPMC_SERVER_HOST", "127.0.0.1")
    port = args.port or int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    client_id = args.id or os.environ.get("RPMC_CLIENT_ID", socket.gethostname())

    print(f"[*] Khởi động Agent [{client_id}] kết nối tới Server {host}:{port}...")
    client = AgentClient(host=host, port=port, client_id=client_id)
    try:
        client.run()
    except KeyboardInterrupt:
        print("\nStopping Agent...")


def cmd_editor(args) -> None:
    """Khởi chạy riêng Máy chủ soạn đề từ Word."""
    load_dotenv()
    from tools.exam_editor.exam_editor_server import main as editor_main
    if args.port:
        os.environ["EXAM_EDITOR_PORT"] = str(args.port)
    if args.host:
        os.environ["EXAM_EDITOR_HOST"] = str(args.host)
    editor_main()


def cmd_student(args) -> None:
    """Mô phỏng Thí sinh thi bằng TCP Socket thuần."""
    from scripts.student_tcp_client import StudentTCPClient
    host = args.host or "127.0.0.1"
    port = args.port or int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    student_id = args.student_id
    name = args.name

    client = StudentTCPClient(host=host, port=port, student_id=student_id, name=name)
    try:
        client.connect()
        client.register()
        print("\n[*] Đang chạy vòng lặp mô phỏng vi phạm...")
        time.sleep(1)
        client.report_violation("TAB_SWITCH", "Thí sinh chuyển sang tab trình duyệt khác")
        time.sleep(1)
        client.report_violation("BLUR", "Thí sinh bấm chuột ra ngoài cửa sổ bài thi (Alt+Tab)")
        time.sleep(1)
        client.report_violation("EXIT_FULLSCREEN", "Thí sinh bấm phím ESC thoát toàn màn hình")
    except Exception as ex:
        print(f"[-] Lỗi trong quá trình truyền nhận TCP: {ex}")
    finally:
        client.close()


def cmd_demo(args) -> None:
    """Chạy kịch bản mô phỏng 2 thí sinh cùng thi."""
    from scripts.demo_two_students import main as demo_main
    demo_main()


def cmd_all(args) -> None:
    """Khởi động toàn bộ: Server -> Console -> Trình duyệt làm bài."""
    load_dotenv()
    tcp_port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    http_port = int(os.environ.get("EXAM_HTTP_PORT", "8081"))
    editor_port = int(os.environ.get("EXAM_EDITOR_PORT", "8082"))

    check_ports = [tcp_port, http_port]
    if not args.no_editor:
        check_ports.append(editor_port)

    # 1. Preflight check
    if not run_preflight(check_ports_list=check_ports):
        print("❌ Preflight check không đạt, không thể tự khởi động hệ thống.")
        sys.exit(1)

    # 2. Khởi động server trong tiến trình con
    server_cmd = [sys.executable, str(PROJECT_ROOT / "rpmc.py"), "server", "--skip-preflight"]
    if args.no_editor:
        server_cmd.append("--no-editor")

    print("[*] Đang khởi động Server ngầm...")
    server_proc = subprocess.Popen(server_cmd)

    try:
        # 3. Chờ các cổng TCP 8090 và HTTP 8081 sẵn sàng
        print(f"[*] Đang chờ Server lắng nghe trên cổng {tcp_port} & {http_port}...")
        if not wait_for_port(tcp_port, timeout=10.0) or not wait_for_port(http_port, timeout=10.0):
            print("❌ Lỗi: Server khởi động quá thời gian quy định hoặc thất bại.")
            server_proc.terminate()
            sys.exit(1)

        print("✅ Server đã sẵn sàng!\n")

        # 4. Mở trình duyệt Web cho thí sinh (nếu không tắt)
        if not args.no_browser:
            exam_url = f"http://localhost:{http_port}/"
            print(f"[*] Đang mở trình duyệt bài thi: {exam_url}")
            webbrowser.open(exam_url)

        # 5. Mở Bảng điều khiển Console GUI
        print("[*] Đang mở Bảng điều khiển Console...")
        from console.app import main as console_main
        console_main()

        # Khi người dùng đóng cửa sổ Console:
        if args.keep_server:
            print("\nℹ️  Console đã đóng. Server vẫn đang chạy nền (PID: %d)." % server_proc.pid)
            print("   Nhấn Ctrl+C để dừng Server bất cứ lúc nào.")
            server_proc.wait()
        else:
            print("\n[*] Đang tắt Server ngầm...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server_proc.kill()
            print("✅ Đã tắt toàn bộ hệ thống RPMC an toàn.")

    except KeyboardInterrupt:
        print("\n[*] Nhận tín hiệu dừng từ người dùng. Đang dọn dẹp...")
        if server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server_proc.kill()
        print("✅ Đã dừng Server.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rpmc",
        description="RPMC - Nền tảng quản trị máy tính từ xa & Giám sát thi trực tuyến qua LAN",
    )
    subparsers = parser.add_subparsers(dest="command", help="Lệnh cần thực thi")

    # all
    p_all = subparsers.add_parser("all", help="Khởi động trọn gói: Server + Console + Web Thí sinh")
    p_all.add_argument("--keep-server", action="store_true", help="Không tự tắt Server khi đóng cửa sổ Console")
    p_all.add_argument("--no-editor", action="store_true", help="Không khởi chạy kèm máy chủ soạn đề Word")
    p_all.add_argument("--no-browser", action="store_true", help="Không tự động mở trình duyệt web")
    p_all.set_defaults(func=cmd_all)

    # server
    p_server = subparsers.add_parser("server", help="Khởi chạy Máy chủ RPMC Server")
    p_server.add_argument("--no-editor", action="store_true", help="Không khởi chạy kèm máy chủ soạn đề Word")
    p_server.add_argument("--skip-preflight", action="store_true", help="Bỏ qua bước kiểm tra tiền khởi động")
    p_server.set_defaults(func=cmd_server)

    # console
    p_console = subparsers.add_parser("console", help="Khởi chạy Bảng điều khiển Console GUI")
    p_console.set_defaults(func=cmd_console)

    # agent
    p_agent = subparsers.add_parser("agent", help="Khởi chạy Agent máy con")
    p_agent.add_argument("--host", type=str, help="Địa chỉ IP Server")
    p_agent.add_argument("--port", type=int, help="Cổng TCP Server")
    p_agent.add_argument("--id", type=str, help="ID định danh Agent máy con")
    p_agent.set_defaults(func=cmd_agent)

    # editor
    p_editor = subparsers.add_parser("editor", help="Khởi chạy riêng Máy chủ soạn đề từ Word")
    p_editor.add_argument("--host", type=str, default="127.0.0.1", help="Địa chỉ lắng nghe")
    p_editor.add_argument("--port", type=int, default=8082, help="Cổng lắng nghe")
    p_editor.set_defaults(func=cmd_editor)

    # student
    p_student = subparsers.add_parser("student", help="Mô phỏng Thí sinh kết nối bằng TCP Socket")
    p_student.add_argument("student_id", type=str, help="Mã số sinh viên (MSSV)")
    p_student.add_argument("name", type=str, help="Họ và tên thí sinh")
    p_student.add_argument("--host", type=str, default="127.0.0.1", help="Địa chỉ IP Server")
    p_student.add_argument("--port", type=int, default=8090, help="Cổng TCP Server")
    p_student.set_defaults(func=cmd_student)

    # demo
    p_demo = subparsers.add_parser("demo", help="Chạy kịch bản mô phỏng 2 thí sinh thi cùng lúc")
    p_demo.set_defaults(func=cmd_demo)

    # init
    p_init = subparsers.add_parser("init", help="Sinh token bảo mật ngẫu nhiên và khởi tạo database")
    p_init.set_defaults(func=cmd_init)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

