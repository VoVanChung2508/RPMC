from __future__ import annotations

import os
import threading
import time
import unittest
import urllib.request
import json

from common.exam_models import StudentStatus
from common.protocol import CommandType, Frame, FrameCodec, FrameType
from scripts.student_tcp_client import StudentTCPClient
from server.exam_manager import ExamManager
from server.exam_web_server import ExamWebServer
from server.listener import ServerListener


class TestLiveIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["RPMC_ADMIN_TOKEN"] = "admin_secret_token_12345678"
        os.environ["RPMC_AGENT_TOKEN"] = "agent_secret_token_12345678"
        cls.tcp_port = 8095
        cls.http_port = 8085

        cls.server_listener = ServerListener(
            host="127.0.0.1",
            port=cls.tcp_port,
            admin_token=os.environ["RPMC_ADMIN_TOKEN"],
            agent_token=os.environ["RPMC_AGENT_TOKEN"],
        )
        cls.tcp_thread = threading.Thread(target=cls.server_listener.start, daemon=True)
        cls.tcp_thread.start()

        cls.web_server = ExamWebServer(host="127.0.0.1", port=cls.http_port)
        cls.web_server.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.web_server.stop()
        cls.server_listener.stop()

    def test_tcp_student_client_flow(self):
        """Kiểm tra thí sinh kết nối qua TCP Socket thuần"""
        client = StudentTCPClient(host="127.0.0.1", port=self.tcp_port, student_id="TEST_TCP_01", name="Học Sinh TCP")
        client.connect()
        try:
            reg_res = client.register()
            self.assertEqual(reg_res.get("student_id"), "TEST_TCP_01")
            self.assertEqual(reg_res.get("score"), 10.0)

            v_res = client.report_violation("TAB_SWITCH", "Chuyển tab thử nghiệm")
            self.assertEqual(v_res.get("student", {}).get("violation_count"), 1)
            self.assertEqual(v_res.get("student", {}).get("score"), 9.0)
        finally:
            client.close()

    def test_http_web_client_flow(self):
        """Kiểm tra Web client truy cập REST API qua HTTP"""
        # 1. Config
        url_cfg = f"http://127.0.0.1:{self.http_port}/api/exam/config"
        req = urllib.request.urlopen(url_cfg)
        cfg_data = json.loads(req.read().decode("utf-8"))
        self.assertEqual(cfg_data.get("initial_score"), 10.0)

        # 2. Register
        url_reg = f"http://127.0.0.1:{self.http_port}/api/exam/register"
        post_data = json.dumps({"student_id": "TEST_WEB_01", "name": "Học Sinh Web"}).encode("utf-8")
        req_reg = urllib.request.Request(url_reg, data=post_data, headers={"Content-Type": "application/json"})
        resp_reg = urllib.request.urlopen(req_reg)
        reg_data = json.loads(resp_reg.read().decode("utf-8"))
        self.assertEqual(reg_data.get("status"), "ok")
        self.assertEqual(reg_data.get("student", {}).get("student_id"), "TEST_WEB_01")

        # 3. Violation
        url_viol = f"http://127.0.0.1:{self.http_port}/api/exam/violation"
        post_viol = json.dumps({
            "student_id": "TEST_WEB_01",
            "event": "EXIT_FULLSCREEN",
            "detail": "Thoát toàn màn hình qua web",
        }).encode("utf-8")
        req_viol = urllib.request.Request(url_viol, data=post_viol, headers={"Content-Type": "application/json"})
        resp_viol = urllib.request.urlopen(req_viol)
        viol_data = json.loads(resp_viol.read().decode("utf-8"))
        self.assertEqual(viol_data.get("student", {}).get("violation_count"), 1)
        self.assertEqual(viol_data.get("student", {}).get("score"), 9.0)


if __name__ == "__main__":
    unittest.main()
