from __future__ import annotations

import copy


class MockToolServer:
    def __init__(self, case):
        self.responses = list((case.get("mock_tool_responses") or {}).values())
        self.consumed = set()

    def execute(self, tool_name, params):
        for index, item in enumerate(self.responses):
            if index in self.consumed or item.get("tool") != tool_name:
                continue
            if item.get("params") == params:
                self.consumed.add(index)
                return copy.deepcopy(item.get("response") or {"status": "error", "error_code": "INVALID_PARAMS"})
        return {
            "status": "error",
            "error_code": "INVALID_PARAMS",
            "error_message": "no mock response matched tool and params",
        }

    def remaining(self):
        return [item for index, item in enumerate(self.responses) if index not in self.consumed]
