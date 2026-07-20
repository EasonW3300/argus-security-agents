from __future__ import annotations


ROLE_PERMISSIONS = {
    "security_analyst": {"scan_ports", "scan_vulnerabilities", "query_asset", "query_threat_intel", "create_ticket"},
    "security_admin": {"scan_ports", "scan_vulnerabilities", "query_asset", "query_threat_intel", "block_ip", "unblock_ip", "create_ticket", "delete_alert"},
    "operator": {"query_asset"},
}


class ToolRegistry:
    def __init__(self, case):
        self.case = case
        self.tools = {item["name"]: item for item in case.get("tool_definitions", [])}

    def has(self, name):
        return name in self.tools

    def allowed(self, role, name):
        if not self.has(name):
            return False
        required = self.tools[name].get("required_permission")
        if required and required == role:
            return True
        return name in ROLE_PERMISSIONS.get(role, set())

    def public_tools(self):
        return list(self.tools.values())
