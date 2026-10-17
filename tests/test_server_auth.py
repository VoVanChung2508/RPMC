import json
import socket
import threading
import unittest

from common.protocol import CommandType, Frame, FrameCodec, FrameType
from server.listener import ServerListener
from server.repository import InMemoryExamRepository, set_global_repository


class TestServerAuthentication(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryExamRepository()
        set_global_repository(self.repo)
        self.bank_id = self.repo.add_sample_bank("Bank Bao Mat")
        self.listener = ServerListener(
            admin_token="admin_secret_token_12345678",
            agent_token="agent_secret_token_12345678",
        )

    def test_agent_auth_rejects_non_ascii_token_without_crashing(self):
        with self.assertRaises(PermissionError):
            self.listener._serve_agent(
                None,
                {"client_id": "test-agent", "token": "agent-token-🔒"},
            )

    def test_console_auth_rejects_non_ascii_token_without_crashing(self):
        with self.assertRaises(PermissionError):
            self.listener._serve_console(None, {"token": "console-token-🔒"})

    def test_student_connection_cannot_execute_admin_exam_rpc(self):
        """
        Chứng minh kết nối thí sinh (TCP student) khi cố tình gửi các RPC quản trị
        như exam.create, exam.banks.list, exam.active.set, exam.status.set
        đều bị từ chối với mã lỗi INVALID_COMMAND.
        """
        s_server, s_client = socket.socketpair()

        def run_server():
            self.listener._handle_connection(s_server)

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        try:
            # 1. Thí sinh đăng ký phiên làm bài hợp lệ
            reg_frame = Frame(
                FrameType.CONTROL,
                CommandType.EXAM_STUDENT_REGISTER,
                json.dumps({"student_id": "SV_HACKER", "name": "Hacker Thi Sinh"}).encode("utf-8"),
            )
            s_client.sendall(FrameCodec.encode(reg_frame))
            resp1 = FrameCodec.read_frame(s_client)
            self.assertEqual(resp1.command_type, CommandType.EXAM_STUDENT_UPDATE)

            # 2. Thí sinh cố tình gọi lệnh exam.banks.list
            hack_rpc1 = Frame(
                FrameType.CONTROL,
                CommandType.GENERIC_RESPONSE,
                json.dumps({"op": "exam.banks.list"}).encode("utf-8"),
            )
            s_client.sendall(FrameCodec.encode(hack_rpc1))
            err_resp1 = FrameCodec.read_frame(s_client)
            self.assertEqual(err_resp1.command_type, CommandType.ERROR_RESPONSE)
            err_data1 = json.loads(err_resp1.payload.decode("utf-8"))
            self.assertEqual(err_data1.get("error"), "INVALID_COMMAND")

            # 3. Thí sinh cố tình gọi lệnh exam.create
            hack_rpc2 = Frame(
                FrameType.CONTROL,
                CommandType.GENERIC_RESPONSE,
                json.dumps({"op": "exam.create", "bank_id": self.bank_id, "title": "Hack Exam"}).encode("utf-8"),
            )
            s_client.sendall(FrameCodec.encode(hack_rpc2))
            err_resp2 = FrameCodec.read_frame(s_client)
            self.assertEqual(err_resp2.command_type, CommandType.ERROR_RESPONSE)
            err_data2 = json.loads(err_resp2.payload.decode("utf-8"))
            self.assertEqual(err_data2.get("error"), "INVALID_COMMAND")

            # 4. Thí sinh cố tình gọi lệnh exam.status.set
            hack_rpc3 = Frame(
                FrameType.CONTROL,
                CommandType.GENERIC_RESPONSE,
                json.dumps({"op": "exam.status.set", "status": "FINISHED"}).encode("utf-8"),
            )
            s_client.sendall(FrameCodec.encode(hack_rpc3))
            err_resp3 = FrameCodec.read_frame(s_client)
            self.assertEqual(err_resp3.command_type, CommandType.ERROR_RESPONSE)
            err_data3 = json.loads(err_resp3.payload.decode("utf-8"))
            self.assertEqual(err_data3.get("error"), "INVALID_COMMAND")
        finally:
            s_client.close()
            t.join(timeout=1.0)

    def test_unauthenticated_connection_cannot_execute_exam_admin_rpc(self):
        """
        Chứng minh kết nối không có token hợp lệ mà gửi thẳng RPC exam.create
        sẽ bị server ngắt và trả về lỗi PermissionError.
        """
        s_server, s_client = socket.socketpair()

        def run_server():
            self.listener._handle_connection(s_server)

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        try:
            # Gửi thẳng RPC mà không SESSION_HELLO
            rpc_frame = Frame(
                FrameType.CONTROL,
                CommandType.GENERIC_RESPONSE,
                json.dumps({"op": "exam.create", "bank_id": self.bank_id}).encode("utf-8"),
            )
            s_client.sendall(FrameCodec.encode(rpc_frame))
            resp = FrameCodec.read_frame(s_client)
            self.assertEqual(resp.command_type, CommandType.ERROR_RESPONSE)
            err = json.loads(resp.payload.decode("utf-8"))
            self.assertEqual(err.get("error"), "PermissionError")
            self.assertIn("Unsupported connection handshake", err.get("message", ""))
        finally:
            s_client.close()
            t.join(timeout=1.0)

    def test_console_with_invalid_token_is_rejected(self):
        """
        Chứng minh kết nối SESSION_HELLO với sai admin token sẽ bị từ chối.
        """
        s_server, s_client = socket.socketpair()

        def run_server():
            self.listener._handle_connection(s_server)

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        try:
            hello_frame = Frame(
                FrameType.CONTROL,
                CommandType.SESSION_HELLO,
                json.dumps({"token": "sai_mat_khau_admin"}).encode("utf-8"),
            )
            s_client.sendall(FrameCodec.encode(hello_frame))
            resp = FrameCodec.read_frame(s_client)
            self.assertEqual(resp.command_type, CommandType.ERROR_RESPONSE)
            err = json.loads(resp.payload.decode("utf-8"))
            self.assertEqual(err.get("error"), "PermissionError")
            self.assertIn("Console authentication failed", err.get("message", ""))
        finally:
            s_client.close()
            t.join(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
