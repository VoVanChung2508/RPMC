import unittest

from server.listener import ServerListener


class TestServerAuthentication(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
