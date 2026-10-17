from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

# Đảm bảo nhận thư mục gốc dự án khi chạy file trực tiếp
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agent.handler import CommandHandler  # Xử lý lệnh từ Server
from common.env import load_dotenv
from common.protocol import CommandType, Frame, FrameCodec, FrameType  # Định nghĩa giao thức truyền tin
from common.security import require_loopback, require_private_network  # Kiểm tra địa chỉ mạng an toàn


# Local agent runtime. It authenticates to the server and handles the request loop for remote control commands.
class AgentClient:
    def __init__(
        self,
        host: str = "127.0.0.1",  # Địa chỉ Server
        port: int = 8090,  # Cổng kết nối
        token: str | None = None,  # Token xác thực
        client_id: str | None = None,  # ID của Agent
        root_dir: str | None = None,  # Thư mục làm việc
        allow_termination: bool = False,  # Cho phép kết thúc tiến trình
    ):
        load_dotenv()
        self.host = host
        # Kiểm tra Server có thuộc mạng được phép kết nối hay không
        allow_private_network = os.environ.get("RPMC_ALLOW_PRIVATE_NETWORK", "0") in {"1", "true", "TRUE", "yes"}
        if allow_private_network:
            require_private_network(host)
        else:
            require_loopback(host)

        self.port = port
        self.token = token or os.environ.get("RPMC_AGENT_TOKEN", "")  # Lấy token xác thực
        self.client_id = client_id or os.environ.get("RPMC_CLIENT_ID", socket.gethostname())  # Lấy ID máy
        self.root_dir = root_dir or os.environ.get("RPMC_AGENT_ROOT", str(Path.cwd()))  # Chọn thư mục gốc

        # Khởi tạo bộ xử lý lệnh
        self.handler = CommandHandler(
            self.root_dir,
            allow_termination=allow_termination
            or os.environ.get("RPMC_ALLOW_PROCESS_TERMINATION") == "1",
        )

    def connect(self) -> None:
        # Kiểm tra độ dài token
        if len(self.token) < 16:
            raise RuntimeError("Set RPMC_AGENT_TOKEN to a secret of at least 16 characters")

        # Tạo kết nối TCP đến Server
        with socket.create_connection((self.host, self.port), timeout=10) as sock:
            sock.settimeout(None)

            # Đóng gói thông tin xác thực thành JSON
            hello = json.dumps(
                {"client_id": self.client_id, "token": self.token},
                separators=(",", ":"),
            ).encode("utf-8")

            # Gửi yêu cầu xác thực đến Server
            sock.sendall(FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.AUTH_REQUEST, hello)))

            # Nhận phản hồi xác thực
            response = FrameCodec.read_frame(sock)
            if response.command_type != CommandType.AUTH_RESPONSE:
                raise PermissionError(response.payload.decode("utf-8", errors="replace"))

            print(f"Agent {self.client_id} connected to {self.host}:{self.port}")

            # Liên tục nhận lệnh, xử lý và gửi kết quả về Server
            while True:
                request = FrameCodec.read_frame(sock)
                reply = self.handler.handle(request)
                sock.sendall(FrameCodec.encode(reply))


def main() -> None:
    load_dotenv()
    # Đọc địa chỉ và cổng Server từ biến môi trường
    host = os.environ.get("RPMC_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))

    # Khởi tạo Agent Client
    client = AgentClient(host, port)

    # Yêu cầu token hợp lệ trước khi chạy
    if len(client.token) < 16:
        raise RuntimeError("Set RPMC_AGENT_TOKEN to a secret of at least 16 characters")

    delay = 1  # Thời gian chờ kết nối lại
    while True:
        try:
            client.connect()  # Kết nối đến Server
        except KeyboardInterrupt:
            print("Agent stopped")
            return
        except PermissionError:
            raise  # Dừng nếu xác thực thất bại
        except OSError as exc:
            # Thử kết nối lại với thời gian chờ tăng dần
            print(f"Agent connection failed: {exc}; retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 30)


if __name__ == "__main__":
    main()  # Chạy chương trình Agent