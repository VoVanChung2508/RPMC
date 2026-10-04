from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from agent.handler import CommandHandler
from common.protocol import CommandType, Frame, FrameCodec, FrameType
from common.security import require_loopback


class AgentClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        token: str | None = None,
        client_id: str | None = None,
        root_dir: str | None = None,
        allow_termination: bool = False,
    ):
        self.host = host
        require_loopback(host)
        self.port = port
        self.token = token or os.environ.get("RPMC_AGENT_TOKEN", "")
        self.client_id = client_id or os.environ.get("RPMC_CLIENT_ID", socket.gethostname())
        self.root_dir = root_dir or os.environ.get("RPMC_AGENT_ROOT", str(Path.cwd()))
        self.handler = CommandHandler(
            self.root_dir,
            allow_termination=allow_termination
            or os.environ.get("RPMC_ALLOW_PROCESS_TERMINATION") == "1",
        )

    def connect(self) -> None:
        if len(self.token) < 16:
            raise RuntimeError("Set RPMC_AGENT_TOKEN to a secret of at least 16 characters")
        with socket.create_connection((self.host, self.port), timeout=10) as sock:
            sock.settimeout(None)
            hello = json.dumps(
                {"client_id": self.client_id, "token": self.token},
                separators=(",", ":"),
            ).encode("utf-8")
            sock.sendall(FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.AUTH_REQUEST, hello)))
            response = FrameCodec.read_frame(sock)
            if response.command_type != CommandType.AUTH_RESPONSE:
                raise PermissionError(response.payload.decode("utf-8", errors="replace"))
            print(f"Agent {self.client_id} connected to {self.host}:{self.port}")
            while True:
                request = FrameCodec.read_frame(sock)
                reply = self.handler.handle(request)
                sock.sendall(FrameCodec.encode(reply))


def main() -> None:
    host = os.environ.get("RPMC_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    client = AgentClient(host, port)
    if len(client.token) < 16:
        raise RuntimeError("Set RPMC_AGENT_TOKEN to a secret of at least 16 characters")
    delay = 1
    while True:
        try:
            client.connect()
        except KeyboardInterrupt:
            print("Agent stopped")
            return
        except PermissionError:
            raise
        except OSError as exc:
            print(f"Agent connection failed: {exc}; retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 30)


if __name__ == "__main__":
    main()
