from __future__ import annotations

import hmac
import ipaddress
import json
import os
import queue
import select
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field

from common.protocol import CommandType, Frame, FrameCodec, FrameType
from server.audit import AuditLogger
from server.dispatcher import CommandDispatcher
from server.rbac import Role


@dataclass
class AgentConnection:
    client_id: str
    connection: socket.socket
    requests: queue.Queue = field(default_factory=queue.Queue)
    connected_at: float = field(default_factory=time.time)
    active: bool = True


@dataclass
class AgentRequest:
    frame: Frame
    completed: threading.Event = field(default_factory=threading.Event)
    response: Frame | None = None
    error: str | None = None


class ServerListener:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        admin_token: str | None = None,
        agent_token: str | None = None,
        audit_logger: AuditLogger | None = None,
        dispatcher: CommandDispatcher | None = None,
    ):
        self.host = host
        self.port = port
        self.admin_token = admin_token or os.environ.get("RPMC_ADMIN_TOKEN", "")
        self.agent_token = agent_token or os.environ.get("RPMC_AGENT_TOKEN", "")
        self.audit = audit_logger or AuditLogger()
        self.dispatcher = dispatcher or CommandDispatcher()
        self._server_socket: socket.socket | None = None
        self._stop_event = threading.Event()
        self._agents: dict[str, AgentConnection] = {}
        self._agents_lock = threading.RLock()
        self._screen_streams: dict[str, threading.Event] = {}
        self._screen_streams_lock = threading.Lock()

        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = host.lower() == "localhost"
        if not is_loopback:
            raise ValueError("RPMC currently binds to loopback only; remote access requires TLS support")

    @property
    def bound_port(self) -> int:
        if self._server_socket is None:
            raise RuntimeError("Server has not started")
        return self._server_socket.getsockname()[1]

    def start(self) -> None:
        if len(self.admin_token) < 16 or len(self.agent_token) < 16:
            raise RuntimeError(
                "Set RPMC_ADMIN_TOKEN and RPMC_AGENT_TOKEN to separate secrets of at least 16 characters"
            )
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(32)
        self._server_socket.settimeout(0.5)
        print(f"RPMC Server listening on {self.host}:{self.bound_port} (loopback only)")
        try:
            while not self._stop_event.is_set():
                try:
                    conn, _ = self._server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_event.is_set():
                        break
                    raise
                threading.Thread(target=self._handle_connection, args=(conn,), daemon=True).start()
        finally:
            self.stop()

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            try:
                first = FrameCodec.read_frame(conn)
                auth = self._json(first.payload)
                if first.command_type == CommandType.AUTH_REQUEST:
                    self._serve_agent(conn, auth)
                elif first.command_type == CommandType.SESSION_HELLO:
                    self._serve_console(conn, auth)
                else:
                    raise PermissionError("Unsupported connection handshake")
            except (OSError, ConnectionError, ValueError, PermissionError, KeyError) as exc:
                try:
                    conn.sendall(self._encode_error(type(exc).__name__, str(exc)))
                except OSError:
                    pass

    def _serve_agent(self, conn: socket.socket, auth: dict) -> None:
        client_id = str(auth.get("client_id", "")).strip()
        token = str(auth.get("token", ""))
        if len(client_id) < 1 or len(client_id) > 128 or not hmac.compare_digest(token, self.agent_token):
            raise PermissionError("Agent authentication failed")
        agent = AgentConnection(client_id, conn)
        with self._agents_lock:
            previous = self._agents.get(client_id)
            if previous:
                previous.active = False
                try:
                    previous.connection.shutdown(socket.SHUT_RDWR)
                    previous.connection.close()
                except OSError:
                    pass
            self._agents[client_id] = agent
        conn.sendall(FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.AUTH_RESPONSE, b'{"status":"ok"}')))
        try:
            while not self._stop_event.is_set() and agent.active:
                try:
                    request = agent.requests.get(timeout=0.25)
                except queue.Empty:
                    readable, _, _ = select.select([conn], [], [], 0)
                    if readable and not conn.recv(1, socket.MSG_PEEK):
                        agent.active = False
                    elif readable:
                        agent.active = False
                    continue
                try:
                    conn.sendall(FrameCodec.encode(request.frame))
                    request.response = FrameCodec.read_frame(conn)
                except (OSError, ConnectionError, ValueError) as exc:
                    request.error = str(exc)
                    agent.active = False
                finally:
                    request.completed.set()
                if request.error:
                    break
        finally:
            agent.active = False
            with self._agents_lock:
                if self._agents.get(client_id) is agent:
                    del self._agents[client_id]

    def _serve_console(self, conn: socket.socket, auth: dict) -> None:
        if not hmac.compare_digest(str(auth.get("token", "")), self.admin_token):
            raise PermissionError("Console authentication failed")
        conn.sendall(FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.AUTH_RESPONSE, b'{"status":"ok","role":"ADMIN"}')))
        actor = str(auth.get("actor", "console"))[:128]
        while not self._stop_event.is_set():
            try:
                frame = FrameCodec.read_frame(conn)
            except (ConnectionError, OSError):
                return
            if frame.command_type != CommandType.GENERIC_RESPONSE:
                conn.sendall(self._encode_error("INVALID_REQUEST", "Expected a console RPC request"))
                continue
            request = self._json(frame.payload)
            try:
                if request.get("op") == "screen.stream":
                    self._stream_screen(conn, request, actor)
                    continue
                result = self._dispatch_console(request, actor)
                response = Frame(FrameType.CONTROL, CommandType.GENERIC_RESPONSE, json.dumps(result).encode("utf-8"))
                conn.sendall(FrameCodec.encode(response))
            except (KeyError, TypeError, ValueError, PermissionError, OSError, TimeoutError, RuntimeError) as exc:
                self.audit.log(actor, str(request.get("op", "unknown")), "failed", {"error": type(exc).__name__})
                conn.sendall(self._encode_error(type(exc).__name__, str(exc)))

    def _dispatch_console(self, request: dict, actor: str) -> dict:
        operation = str(request.get("op", ""))
        if operation == "client.list":
            with self._agents_lock:
                clients = [
                    {
                        "client_id": agent.client_id,
                        "connected": agent.active,
                        "connected_seconds": round(time.time() - agent.connected_at, 1),
                    }
                    for agent in self._agents.values()
                    if agent.active
                ]
            self.audit.log(actor, operation, "ok", {"count": len(clients)})
            return {"clients": clients}
        if operation == "audit.list":
            entries = self.audit.list_entries()
            self.audit.log(actor, operation, "ok", {"count": len(entries)})
            return {"entries": entries}
        if operation == "audit.verify":
            valid, message = self.audit.verify()
            self.audit.log(actor, operation, "ok" if valid else "failed", {"message": message})
            return {"valid": valid, "message": message}

        command, permission = self.dispatcher.resolve(Role.ADMIN, operation)
        client_id = str(request.get("client_id", "")).strip()
        if not client_id:
            raise ValueError("Select a connected agent")
        with self._agents_lock:
            agent = self._agents.get(client_id)
        if agent is None or not agent.active:
            raise ConnectionError(f"Agent {client_id!r} is not connected")
        if operation == "screen.stop":
            with self._screen_streams_lock:
                stream_event = self._screen_streams.get(client_id)
                if stream_event:
                    stream_event.set()

        payload_fields = {}
        if operation == "file.list":
            payload_fields["path"] = str(request.get("path", "."))
        elif operation == "file.download":
            payload_fields["path"] = str(request["path"])
        elif operation == "process.terminate":
            payload_fields["pid"] = int(request["pid"])
        elif operation == "screen.capture":
            payload_fields["force_full"] = bool(request.get("force_full", False))

        response = self._request_agent(
            agent,
            Frame(
                FrameType.CONTROL,
                command,
                json.dumps(payload_fields).encode("utf-8"),
            ),
        )
        if response.command_type == CommandType.ERROR_RESPONSE:
            error = self._json(response.payload)
            raise RuntimeError(error.get("message", "Agent rejected the request"))
        result = self._json(response.payload)
        self.audit.log(
            actor,
            operation,
            "ok",
            {"client_id": client_id, "permission": permission},
        )
        return result

    def _stream_screen(self, conn: socket.socket, request: dict, actor: str) -> None:
        client_id = str(request.get("client_id", "")).strip()
        self.dispatcher.resolve(Role.ADMIN, "screen.capture")
        if not client_id:
            raise ValueError("Select a connected agent")
        with self._agents_lock:
            agent = self._agents.get(client_id)
        if agent is None or not agent.active:
            raise ConnectionError(f"Agent {client_id!r} is not connected")

        stop_event = threading.Event()
        with self._screen_streams_lock:
            current = self._screen_streams.get(client_id)
            if current is not None and not current.is_set():
                raise RuntimeError(f"A screen stream is already active for {client_id!r}")
            self._screen_streams[client_id] = stop_event

        frames_sent = 0
        force_full = True
        self.audit.log(actor, "screen.stream", "started", {"client_id": client_id})
        try:
            conn.sendall(
                FrameCodec.encode(
                    Frame(
                        FrameType.CONTROL,
                        CommandType.GENERIC_RESPONSE,
                        json.dumps({"status": "STREAMING"}).encode("utf-8"),
                    )
                )
            )
            while not stop_event.is_set() and not self._stop_event.is_set() and agent.active:
                response = self._request_agent(
                    agent,
                    Frame(
                        FrameType.CONTROL,
                        CommandType.SCREEN_START_REQUEST,
                        json.dumps({"force_full": force_full}).encode("utf-8"),
                    ),
                    timeout=10,
                )
                if response.command_type == CommandType.ERROR_RESPONSE:
                    error = self._json(response.payload)
                    raise RuntimeError(error.get("message", "Agent rejected screen capture"))
                if response.command_type != CommandType.SCREEN_TILE_DATA:
                    raise ValueError("Agent returned an invalid screen-stream frame")
                conn.sendall(FrameCodec.encode(response))
                frames_sent += 1
                force_full = False
                stop_event.wait(0.12)
        finally:
            with self._screen_streams_lock:
                if self._screen_streams.get(client_id) is stop_event:
                    self._screen_streams.pop(client_id, None)
            try:
                self._request_agent(
                    agent,
                    Frame(FrameType.CONTROL, CommandType.SCREEN_STOP_REQUEST, b"{}"),
                    timeout=3,
                )
            except (ConnectionError, OSError, TimeoutError, RuntimeError):
                pass
            self.audit.log(
                actor,
                "screen.stream",
                "stopped",
                {"client_id": client_id, "frames_sent": frames_sent},
            )

    @staticmethod
    def _request_agent(
        agent: AgentConnection,
        frame: Frame,
        timeout: float = 20,
    ) -> Frame:
        if not agent.active:
            raise ConnectionError(f"Agent {agent.client_id!r} is disconnected")
        pending = AgentRequest(frame)
        agent.requests.put(pending)
        if not pending.completed.wait(timeout=timeout):
            raise TimeoutError(f"Timed out waiting for agent {agent.client_id!r}")
        if pending.error:
            raise ConnectionError(f"Agent request failed: {pending.error}")
        if pending.response is None:
            raise RuntimeError("Agent returned no response")
        return pending.response

    @staticmethod
    def _json(payload: bytes) -> dict:
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    @staticmethod
    def _encode_error(name: str, message: str) -> bytes:
        payload = json.dumps({"error": name, "message": message}).encode("utf-8")
        return FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.ERROR_RESPONSE, payload))

    def stop(self) -> None:
        self._stop_event.set()
        with self._screen_streams_lock:
            for stream_event in self._screen_streams.values():
                stream_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
        with self._agents_lock:
            agents = list(self._agents.values())
            self._agents.clear()
        for agent in agents:
            agent.active = False
            try:
                agent.connection.shutdown(socket.SHUT_RDWR)
                agent.connection.close()
            except OSError:
                pass
