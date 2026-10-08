from __future__ import annotations

import json
import os
import socket
import threading
from collections.abc import Callable

from common.protocol import CommandType, Frame, FrameCodec, FrameType
from common.security import require_loopback, require_private_network


class ConsoleNetworkClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        token: str = "",
        actor: str = "console",
    ):
        self.host = host
        allow_private_network = os.environ.get("RPMC_ALLOW_PRIVATE_NETWORK", "0") in {"1", "true", "TRUE", "yes"}
        if allow_private_network:
            require_private_network(host)
        else:
            require_loopback(host)
        self.port = port
        self.token = token
        self.actor = actor

    def request(self, operation: str, **fields) -> dict:
        if len(self.token) < 16:
            raise ValueError("Enter the console token (at least 16 characters)")
        with socket.create_connection((self.host, self.port), timeout=10) as sock:
            sock.settimeout(25)
            hello = json.dumps(
                {"token": self.token, "actor": self.actor},
                separators=(",", ":"),
            ).encode("utf-8")
            sock.sendall(FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.SESSION_HELLO, hello)))
            auth = FrameCodec.read_frame(sock)
            self._raise_if_error(auth)

            payload = json.dumps(
                {"op": operation, **fields},
                separators=(",", ":"),
            ).encode("utf-8")
            sock.sendall(FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.GENERIC_RESPONSE, payload)))
            response = FrameCodec.read_frame(sock)
            self._raise_if_error(response)
            result = json.loads(response.payload.decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("Server returned an invalid response")
            return result

    def stream_screen(
        self,
        client_id: str,
        stop_event: threading.Event,
        on_frame: Callable[[dict], None],
    ) -> None:
        if len(self.token) < 16:
            raise ValueError("Enter the console token (at least 16 characters)")
        with socket.create_connection((self.host, self.port), timeout=10) as sock:
            sock.settimeout(None)
            watcher = threading.Thread(
                target=self._close_when_stopped,
                args=(sock, stop_event),
                daemon=True,
            )
            watcher.start()
            try:
                hello = json.dumps(
                    {"token": self.token, "actor": self.actor},
                    separators=(",", ":"),
                ).encode("utf-8")
                sock.sendall(
                    FrameCodec.encode(
                        Frame(FrameType.CONTROL, CommandType.SESSION_HELLO, hello)
                    )
                )
                auth = FrameCodec.read_frame(sock)
                self._raise_if_error(auth)
                request = json.dumps(
                    {"op": "screen.stream", "client_id": client_id},
                    separators=(",", ":"),
                ).encode("utf-8")
                sock.sendall(
                    FrameCodec.encode(
                        Frame(FrameType.CONTROL, CommandType.GENERIC_RESPONSE, request)
                    )
                )
                start = FrameCodec.read_frame(sock)
                self._raise_if_error(start)
                if start.command_type != CommandType.GENERIC_RESPONSE:
                    raise RuntimeError("Server did not acknowledge the screen stream")
                while not stop_event.is_set():
                    frame = FrameCodec.read_frame(sock)
                    self._raise_if_error(frame)
                    if frame.command_type != CommandType.SCREEN_TILE_DATA:
                        raise RuntimeError("Received an unexpected screen-stream frame")
                    payload = json.loads(frame.payload.decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("Received invalid screen-stream data")
                    on_frame(payload)
            finally:
                stop_event.set()
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                watcher.join(timeout=1)

    @staticmethod
    def _close_when_stopped(sock: socket.socket, stop_event: threading.Event) -> None:
        stop_event.wait()
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    @staticmethod
    def _raise_if_error(frame: Frame) -> None:
        if frame.command_type != CommandType.ERROR_RESPONSE:
            return
        try:
            error = json.loads(frame.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("Server rejected the request") from None
        raise RuntimeError(error.get("message", "Server rejected the request"))
