from pathlib import Path

from config import load_config
from run_eval import run_eval


def test_run_eval_offline_mock_agent_writes_reports(tmp_path):
    config = load_config(
        {
            "GENERATOR_PROVIDER": "mock",
            "GENERATOR_MODEL": "mock-scenario-02-agent",
            "GENERATOR_API_KEY": "dummy",
            "JUDGE_PROVIDER": "mock",
            "JUDGE_MODEL": "mock-scenario-02-judge",
            "JUDGE_API_KEY": "dummy",
        }
    )

    exit_code = run_eval(
        Path("Eval_data_1.json"),
        tmp_path / "run",
        config,
        limit=2,
        skip_model_graders=True,
        use_mock_agent=True,
    )

    assert exit_code == 0
    assert (tmp_path / "run" / "eval_results.json").exists()
    assert (tmp_path / "run" / "eval_summary.csv").exists()
    assert (tmp_path / "run" / "checkpoints" / "S02-001.json").exists()

