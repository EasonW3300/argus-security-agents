import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mock_tool_server import MockToolServer


class MockToolServerTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "tool_definitions": [{"name": "scan_ports"}],
            "mock_tool_responses": {
                "step_1": {
                    "tool": "scan_ports",
                    "params": {"target_ip": "10.0.0.1", "port_range": "1-65535"},
                    "response": {"status": "error", "error_code": "TIMEOUT"},
                },
                "step_2": {
                    "tool": "scan_ports",
                    "params": {"target_ip": "10.0.0.1", "port_range": "22,80,443"},
                    "response": {"status": "success", "data": {"open_ports": ["80"]}},
                },
            },
        }

    def test_matches_exact_params_in_declaration_order(self):
        server = MockToolServer(self.case)
        first = server.execute("scan_ports", {"target_ip": "10.0.0.1", "port_range": "1-65535"})
        second = server.execute("scan_ports", {"target_ip": "10.0.0.1", "port_range": "22,80,443"})
        self.assertEqual(first["error_code"], "TIMEOUT")
        self.assertEqual(second["status"], "success")

    def test_unmatched_params_return_structured_error(self):
        response = MockToolServer(self.case).execute("scan_ports", {"target_ip": "10.0.0.2", "port_range": "80"})
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error_code"], "INVALID_PARAMS")


if __name__ == "__main__":
    unittest.main()
