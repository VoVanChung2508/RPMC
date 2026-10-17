from __future__ import annotations

import os
import sys
from pathlib import Path

# Đảm bảo nhận thư mục gốc dự án khi chạy file trực tiếp
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.env import load_dotenv
from server.exam_web_server import ExamWebServer
from server.listener import ServerListener

# Starts the exam web app and the control listener used by agents and the admin console.
def main() -> None:
    load_dotenv()
    host = os.environ.get("RPMC_BIND_HOST", "127.0.0.1").strip()
    port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    http_port = int(os.environ.get("EXAM_HTTP_PORT", "8081"))

    # Start Student Web Exam Server
    web_server = ExamWebServer(host="0.0.0.0", port=http_port)
    web_server.start()
    actual_http_port = web_server.port
    print(f"[*] Cổng làm bài thi thí sinh (Web): http://localhost:{actual_http_port}/ (hoặc http://<IP_LAN>:{actual_http_port}/)")

    listener = ServerListener(host=host, port=port)
    try:
        listener.start()
    except KeyboardInterrupt:
        print("\nStopping RPMC and Exam server...")
    finally:
        web_server.stop()
        listener.stop()


if __name__ == "__main__":
    main()

