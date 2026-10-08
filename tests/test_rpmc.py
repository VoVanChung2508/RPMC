from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.agent_main import AgentClient
from agent.handler import CommandHandler
from agent.screen import ScreenCaptureService
from common.protocol import CommandType, Frame, FrameCodec, FrameType
from common.security import PathValidator, SecurityError, require_loopback, require_private_network
from console.network import ConsoleNetworkClient
from server.audit import AuditLogger
from server.listener import ServerListener
from server.rbac import RBACEnforcer, Role


class ProtocolTests(unittest.TestCase):
    def test_read_frame_handles_fragmented_transport(self):
        left, right = socket.socketpair()
        frame = Frame(FrameType.CONTROL, CommandType.SYSTEM_INFO_REQUEST, b"")
        encoded = FrameCodec.encode(frame)

        def send_fragments():
            for byte in encoded:
                right.sendall(bytes([byte]))

        sender = threading.Thread(target=send_fragments)
        sender.start()
        decoded = FrameCodec.read_frame(left)
        sender.join(timeout=2)
        left.close()
        right.close()
        self.assertEqual(decoded, frame)

    def test_decode_rejects_trailing_bytes(self):
        encoded = FrameCodec.encode(Frame(FrameType.CONTROL, CommandType.GENERIC_RESPONSE, b"x"))
        with self.assertRaises(ValueError):
            FrameCodec.decode(encoded + b"extra")


class AgentAndSecurityTests(unittest.TestCase):
    def test_screen_stream_sends_only_changed_tiles(self):
        from PIL import Image

        service = ScreenCaptureService()
        desktop = Image.new("RGB", (128, 64), "black")
        with patch("agent.screen.ImageGrab.grab", return_value=desktop):
            width, height, first = service.capture_delta_tiles(force_full=True)
            _, _, unchanged = service.capture_delta_tiles()
            desktop.putpixel((2, 2), (255, 0, 0))
            _, _, changed = service.capture_delta_tiles()
        self.assertEqual((width, height), (128, 64))
        self.assertEqual(len(first), 2)
        self.assertEqual(unchanged, [])
        self.assertEqual([(tile["x"], tile["y"]) for tile in changed], [(0, 0)])
        service.stop()
        with patch("agent.screen.ImageGrab.grab", return_value=desktop):
            _, _, after_stop = service.capture_delta_tiles()
        self.assertEqual(len(after_stop), 2)

    def test_file_service_stays_inside_agent_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "allowed.txt").write_text("ok", encoding="utf-8")
            handler = CommandHandler(directory)
            response = handler.handle(
                Frame(
                    FrameType.CONTROL,
                    CommandType.FILE_LIST_REQUEST,
                    json.dumps({"path": "."}).encode(),
                )
            )
            files = json.loads(response.payload)["files"]
            self.assertEqual(files[0]["name"], "allowed.txt")
            with self.assertRaises(SecurityError):
                PathValidator.validate(directory, "../outside.txt")

    def test_role_permissions_fail_closed(self):
        permissions = RBACEnforcer()
        self.assertTrue(permissions.can(Role.ADMIN, "terminate"))
        self.assertFalse(permissions.can(Role.VIEWER, "terminate"))
        self.assertFalse(permissions.can("UNKNOWN", "read"))

    def test_clients_reject_non_loopback_hosts(self):
        require_loopback("127.0.0.1")
        require_loopback("localhost")
        with self.assertRaises(ValueError):
            require_loopback("192.0.2.10")

    def test_private_network_hosts_are_allowed_for_lan_mode(self):
        require_private_network("127.0.0.1")
        require_private_network("localhost")
        require_private_network("192.168.1.25")
        require_private_network("10.0.0.5")
        with self.assertRaises(ValueError):
            require_private_network("8.8.8.8")

    def test_process_termination_requires_local_opt_in(self):
        handler = CommandHandler()
        response = handler.handle(
            Frame(
                FrameType.CONTROL,
                CommandType.PROCESS_KILL_REQUEST,
                json.dumps({"pid": 12345}).encode(),
            )
        )
        self.assertEqual(response.command_type, CommandType.ERROR_RESPONSE)
        self.assertIn("disabled", json.loads(response.payload)["message"])

    def test_audit_log_persists_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            logger = AuditLogger(str(path))
            logger.log("tester", "client.list", "ok", {"count": 0})
            self.assertEqual(AuditLogger(str(path)).verify()[0], True)
            entry = json.loads(path.read_text(encoding="utf-8"))
            entry["result"] = "changed"
            path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            self.assertFalse(AuditLogger(str(path)).verify()[0])


class LocalRpcIntegrationTests(unittest.TestCase):
    def test_console_to_server_to_agent_rpc(self):
        admin_token = "test-admin-token-123456"
        agent_token = "test-agent-token-123456"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.txt").write_text("RPMC works", encoding="utf-8")
            listener = ServerListener(
                port=0,
                admin_token=admin_token,
                agent_token=agent_token,
                audit_logger=AuditLogger(str(root / "audit.jsonl")),
            )
            server_thread = threading.Thread(target=listener.start, daemon=True)
            server_thread.start()
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    port = listener.bound_port
                    if port:
                        break
                except RuntimeError:
                    pass
                time.sleep(0.01)
            else:
                self.fail("Server did not bind")

            agent = AgentClient(
                host="127.0.0.1",
                port=port,
                token=agent_token,
                client_id="test-agent",
                root_dir=directory,
            )
            agent_errors = []

            def run_agent():
                try:
                    agent.connect()
                except (ConnectionError, OSError):
                    pass
                except Exception as exc:
                    agent_errors.append(exc)

            agent_thread = threading.Thread(target=run_agent, daemon=True)
            agent_thread.start()
            client = ConsoleNetworkClient("127.0.0.1", port, admin_token)
            try:
                deadline = time.time() + 5
                while time.time() < deadline:
                    clients = client.request("client.list")["clients"]
                    if clients:
                        break
                    time.sleep(0.05)
                self.assertEqual(clients[0]["client_id"], "test-agent")

                system = client.request("system.info", client_id="test-agent")
                self.assertTrue(system["hostname"])
                listed = client.request("file.list", client_id="test-agent", path=".")["files"]
                self.assertIn("sample.txt", [item["name"] for item in listed])
                downloaded = client.request(
                    "file.download", client_id="test-agent", path="sample.txt"
                )
                self.assertEqual(downloaded["content_base64"], "UlBNQyB3b3Jrcw==")
                with self.assertRaises(RuntimeError):
                    client.request("file.list", client_id="test-agent", path="../")
                processes = client.request("process.list", client_id="test-agent")["processes"]
                self.assertTrue(processes)
                streamed_frames = []
                stream_errors = []
                stream_stop = threading.Event()

                def stream_worker():
                    try:
                        client.stream_screen(
                            "test-agent",
                            stream_stop,
                            lambda frame: streamed_frames.append(frame),
                        )
                    except OSError as exc:
                        if not stream_stop.is_set():
                            stream_errors.append(exc)

                with patch(
                    "agent.screen.ScreenCaptureService.capture_delta_tiles",
                    return_value=(64, 64, []),
                ):
                    stream_thread = threading.Thread(target=stream_worker, daemon=True)
                    stream_thread.start()
                    deadline = time.time() + 5
                    while len(streamed_frames) < 2 and time.time() < deadline:
                        time.sleep(0.02)
                    self.assertGreaterEqual(len(streamed_frames), 2)
                    self.assertEqual(
                        client.request("screen.stop", client_id="test-agent")["status"],
                        "STREAMING_STOPPED",
                    )
                    stream_stop.set()
                    stream_thread.join(timeout=3)
                self.assertFalse(stream_thread.is_alive())
                self.assertEqual(stream_errors, [])
                self.assertTrue(client.request("audit.verify")["valid"])
            finally:
                listener.stop()
                server_thread.join(timeout=2)
                agent_thread.join(timeout=2)
                self.assertEqual(agent_errors, [])


if __name__ == "__main__":
    unittest.main()
