from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_CONFIG = ROOT / "agent-compose.ui.yml"
README = ROOT / "integration" / "README.md"


class AgentComposeUiConfigTests(unittest.TestCase):
    def test_ui_config_uses_github_workspace_and_four_agents(self):
        text = UI_CONFIG.read_text(encoding="utf-8")

        self.assertIn("provider: git", text)
        self.assertIn("url: https://github.com/EasonW3300/argus-security-agents.git", text)
        self.assertIn("ref: feature/scenario-o2-eval", text)
        self.assertNotIn("GITHUB_READ_TOKEN", text)
        self.assertNotIn("github_pat_", text)
        self.assertEqual(4, len(re.findall(r"^  [a-z-]+-agent:$", text, re.MULTILINE)))

    def test_ui_readme_lists_github_setup_and_safe_commands(self):
        text = README.read_text(encoding="utf-8")

        self.assertIn("无需 GitHub Token", text)
        for scenario in ("scenario-01", "scenario-02", "scenario-03", "scenario-04"):
            self.assertIn(scenario, text)


if __name__ == "__main__":
    unittest.main()
