from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Đảm bảo nhận thư mục gốc dự án khi chạy file trực tiếp
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.env import load_dotenv
from common.preflight import get_lan_ip, print_banner, run_preflight
from server.exam_web_server import ExamWebServer
from server.listener import ServerListener
from tools.exam_editor.exam_editor_server import ExamEditorServer


def main() -> None:
    parser = argparse.ArgumentParser(description="RPMC Server")
    parser.add_argument("--no-editor", action="store_true", help="Không khởi chạy máy chủ soạn đề thi Word")
    parser.add_argument("--skip-preflight", action="store_true", help="Bỏ qua bước kiểm tra tiền khởi động")
    args = parser.parse_args()

    load_dotenv()
    host = os.environ.get("RPMC_BIND_HOST", "0.0.0.0").strip()
    port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    http_port = int(os.environ.get("EXAM_HTTP_PORT", "8081"))
    editor_port = int(os.environ.get("EXAM_EDITOR_PORT", "8082"))

    check_ports = [port, http_port]
    if not args.no_editor:
        check_ports.append(editor_port)

    if not args.skip_preflight:
        if not run_preflight(check_ports_list=check_ports):
            sys.exit(1)

    # 1. Start Student Web Exam Server
    web_server = ExamWebServer(host=host, port=http_port)
    web_server.start()
    actual_http_port = web_server.port

    # 2. Start Exam Editor Server (trong thread riêng, trừ khi có cờ --no-editor)
    editor_server = None
    actual_editor_port = None
    if not args.no_editor:
        try:
            editor_server = ExamEditorServer(host=host, port=editor_port)
            editor_server.start()
            actual_editor_port = editor_server.port
        except Exception as e:
            print(f"[!] Không thể khởi động máy chủ soạn đề: {e}")

    # 3. In banner với IP LAN và QR code
    lan_ip = get_lan_ip()
    print_banner(lan_ip=lan_ip, http_port=actual_http_port, tcp_port=port, editor_port=actual_editor_port)

    # 4. Start Core RPMC TCP Listener
    listener = ServerListener(host=host, port=port)
    try:
        listener.start()
    except KeyboardInterrupt:
        print("\nStopping RPMC and Exam server...")
    finally:
        web_server.stop()
        if editor_server:
            editor_server.stop()
        listener.stop()


if __name__ == "__main__":
    main()
