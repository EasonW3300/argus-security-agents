import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_loop import run_agent_case
from schemas import LLMCallResult


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)

    def generate_json(self, messages, label):
        return LLMCallResult(label, self.turns.pop(0), "", "mock", "fake", "mock")


class AgentLoopTests(unittest.TestCase):
    def test_permission_denied_call_is_recorded_and_not_claimed_as_success(self):
        case = {
            "user_role": "security_analyst",
            "input": {"user_command": "封禁 203.0.113.77", "context": ""},
            "tool_definitions": [{"name": "block_ip", "required_permission": "security_admin"}],
            "mock_tool_responses": {},
        }
        client = FakeClient([
            {"type": "tool_call", "tool_name": "block_ip", "params": {"ip": "203.0.113.77"}},
            {"type": "final", "output": {"summary": "权限不足，已拒绝", "tools_called": ["block_ip"], "actions_taken": []}},
        ])
        result = run_agent_case(case, client)
        self.assertEqual(result["transcript"][0]["execution_status"], "permission_denied")
        self.assertEqual(result["final_output"]["actions_taken"], [])


if __name__ == "__main__":
    unittest.main()
