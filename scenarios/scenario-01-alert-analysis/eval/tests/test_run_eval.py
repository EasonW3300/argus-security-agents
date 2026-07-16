import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_config
from schemas import LLMCallResult
from run_eval import (
    build_manifest,
    load_cases,
    main,
    manifest_fingerprint,
    run_case,
    run_eval,
    select_cases,
)


EVAL_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = EVAL_DIR / "Eval-data_v1.json"
SECRET = "runner-test-secret"


def config(model="agent-model"):
    return load_config(
        {
            "AGENT_PROVIDER": "deepseek",
            "AGENT_MODEL": model,
            "DEEPSEEK_API_KEY": SECRET,
            "JUDGE_PROVIDER": "qwen",
            "JUDGE_MODEL": "judge-model",
            "DASHSCOPE_API_KEY": "judge-test-secret",
        }
    )


def valid_output(case):
    return {
        "alert_id": case["input"]["alert_id"],
        "judgment": {
            "severity": case["expected_severity"],
            "attack_type": case["expected_attack_type"],
            "confidence": 0.9,
            "summary": "证据支持该研判结论",
            "evidence_chain": ["输入中的可验证证据"],
            "iocs": [],
        },
        "remediation": ["立即隔离受影响资产并完成后续取证分析"],
        "metadata": {
            "tools_called": case["ground_truth"]["expected_tools_minimum"]
        },
    }


def call(label, parsed):
    return LLMCallResult(
        label=label,
        parsed=parsed,
        raw_text="{}",
        provider="fake",
        model="fake-model",
        response_mode="json_object",
        latency_ms=1,
        attempts=1,
    )


class AgentClient:
    def __init__(self, fail_ids=(), secret_error=False):
        self.fail_ids = set(fail_ids)
        self.secret_error = secret_error
        self.calls = []

    def generate_json(self, messages, schema, label):
        case_id = next(
            case_id
            for case_id in ("A%02d" % index for index in range(1, 31))
            if case_id in messages[1]["content"]
        )
        self.calls.append(case_id)
        if case_id in self.fail_ids:
            message = "provider down"
            if self.secret_error:
                message += " api_key=" + SECRET
            raise RuntimeError(message)
        case = next(item for item in load_cases(DATA_PATH) if item["test_case_id"] == case_id)
        return call(label, valid_output(case))


class JudgeClient:
    def __init__(self, score=4):
        self.score = score
        self.calls = []

    def generate_json(self, messages, schema, label):
        self.calls.append(label)
        if label == "hallucination_check":
            parsed = {
                "total_statements": 1,
                "verifiable": 1,
                "hallucinations": 0,
                "uncertain": 0,
                "details": [
                    {
                        "statement": "输入中的可验证证据",
                        "verdict": "verifiable",
                        "reason": "输入可追溯",
                    }
                ],
            }
        else:
            parsed = {
                "score": self.score,
                "reason": "依据充分",
                "evidence_quotes": ["输入中的可验证证据"],
            }
        return call(label, parsed)


class FalseyAgentClient(AgentClient):
    def __bool__(self):
        return False


class RunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(DATA_PATH)

    def test_select_single_case_limit_and_validation_preserve_order(self):
        self.assertEqual(
            [case["test_case_id"] for case in select_cases(self.cases, "A10")],
            ["A10"],
        )
        self.assertEqual(
            [case["test_case_id"] for case in select_cases(self.cases, limit=3)],
            ["A01", "A02", "A03"],
        )
        with self.assertRaisesRegex(ValueError, "unknown case id"):
            select_cases(self.cases, "A99")
        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "limit must be positive"):
                    select_cases(self.cases, limit=limit)

    def test_load_cases_validates_runtime_contract(self):
        broken_values = [
            self.cases[:-1],
            [dict(case, test_case_id="A01") for case in self.cases],
            [dict(case, scenario=3) if index == 0 else case for index, case in enumerate(self.cases)],
            [dict(case, input={}) if index == 0 else case for index, case in enumerate(self.cases)],
            [dict(case, ground_truth={}) if index == 0 else case for index, case in enumerate(self.cases)],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            for broken in broken_values:
                with self.subTest(kind=str(broken[0])[:40]):
                    path.write_text(json.dumps(broken), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "dataset"):
                        load_cases(path)

    def test_manifest_is_stable_excludes_ephemeral_fields_and_has_no_key(self):
        first = build_manifest(DATA_PATH, config(), "run-one", {"limit": 1})
        second = dict(first, run_id="run-two", started_at="later", fingerprint="junk")
        self.assertEqual(manifest_fingerprint(first), manifest_fingerprint(second))
        old_prompt = dict(first, prompt_version="route-a-v1")
        self.assertEqual(first["fingerprint"], manifest_fingerprint(first))
        self.assertNotEqual(
            first["fingerprint"],
            manifest_fingerprint(old_prompt),
        )
        self.assertNotEqual(
            manifest_fingerprint(first),
            manifest_fingerprint(
                dict(first, agent=dict(first["agent"], model="changed"))
            ),
        )
        rendered = json.dumps(first)
        self.assertNotIn(SECRET, rendered)
        self.assertIn("dataset_sha256", first)
        self.assertIn("prompt_version", first)
        self.assertEqual(first["prompt_version"], "route-a-v2-tool-ids")
        self.assertIn("started_at", first)

        sensitive_config = load_config(
            {
                "AGENT_PROVIDER": "deepseek",
                "AGENT_MODEL": "agent-model",
                "DEEPSEEK_API_KEY": SECRET,
                "AGENT_EXTRA_BODY_JSON": json.dumps(
                    {
                        "authorization": "Bearer " + SECRET,
                        "nested": {"note": "contains " + SECRET},
                        "trace_id": "safe-trace",
                    }
                ),
            }
        )
        sensitive_manifest = build_manifest(
            DATA_PATH, sensitive_config, "safe-run", {}
        )
        self.assertNotIn(SECRET, json.dumps(sensitive_manifest))
        self.assertEqual(
            sensitive_manifest["agent"]["extra_body"]["trace_id"],
            "safe-trace",
        )

    def test_skip_model_graders_writes_checkpoint_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            judge = JudgeClient()
            code = run_eval(
                DATA_PATH,
                run_dir,
                config(),
                case_id="A01",
                skip_model_graders=True,
                agent_client=FalseyAgentClient(),
                judge_client=judge,
            )
            checkpoint = json.loads(
                (run_dir / "checkpoints" / "A01.json").read_text(encoding="utf-8")
            )
            report = json.loads((run_dir / "eval_results.json").read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(checkpoint["status"], "completed")
        self.assertEqual(len(checkpoint["code_graders"]), 6)
        self.assertIsNone(checkpoint["quality_scores"])
        self.assertIsNone(checkpoint["hallucination"])
        self.assertEqual(checkpoint["overall_pass"], "not_evaluated")
        self.assertEqual(judge.calls, [])
        self.assertEqual(len(report["results"]), 1)

    def test_full_model_grading_sets_true_false_and_not_evaluated(self):
        case = self.cases[0]
        passed = run_case(case, AgentClient(), JudgeClient(4), False)
        failed = run_case(case, AgentClient(), JudgeClient(2), False)

        class UncertainJudge(JudgeClient):
            def generate_json(self, messages, schema, label):
                result = super().generate_json(messages, schema, label)
                if label == "evidence_completeness":
                    result.parsed["score"] = None
                return result

        uncertain = run_case(case, AgentClient(), UncertainJudge(), False)
        self.assertIs(passed.overall_pass, True)
        self.assertIs(failed.overall_pass, False)
        self.assertEqual(uncertain.overall_pass, "not_evaluated")

    def test_failure_is_isolated_continues_and_redacts_secret(self):
        agent = AgentClient({"A01"}, secret_error=True)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            code = run_eval(
                DATA_PATH,
                run_dir,
                config(),
                limit=2,
                skip_model_graders=True,
                agent_client=agent,
                judge_client=JudgeClient(),
            )
            first = json.loads((run_dir / "checkpoints" / "A01.json").read_text())
            second = json.loads((run_dir / "checkpoints" / "A02.json").read_text())

        self.assertEqual(code, 2)
        self.assertEqual(agent.calls, ["A01", "A02"])
        self.assertEqual(first["status"], "error")
        self.assertEqual(len(first["code_graders"]), 6)
        self.assertNotIn(SECRET, first["error_message"])
        self.assertEqual(second["status"], "completed")

    def test_judge_failure_checkpoint_keeps_prior_successful_calls(self):
        class FailingSecondJudge(JudgeClient):
            def generate_json(self, messages, schema, label):
                if len(self.calls) == 1:
                    raise RuntimeError("second judge failed")
                return super().generate_json(messages, schema, label)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            code = run_eval(
                DATA_PATH,
                run_dir,
                config(),
                case_id="A01",
                agent_client=AgentClient(),
                judge_client=FailingSecondJudge(),
            )
            checkpoint = json.loads(
                (run_dir / "checkpoints" / "A01.json").read_text()
            )

        self.assertEqual(code, 2)
        self.assertEqual(checkpoint["status"], "error")
        self.assertEqual(
            [item["label"] for item in checkpoint["calls"]],
            ["agent", "severity_rationality"],
        )

    def test_resume_skips_completed_and_reruns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            first = AgentClient({"A02"})
            self.assertEqual(
                run_eval(
                    DATA_PATH,
                    run_dir,
                    config(),
                    limit=2,
                    skip_model_graders=True,
                    agent_client=first,
                    judge_client=JudgeClient(),
                ),
                2,
            )
            resumed = AgentClient()
            code = run_eval(
                DATA_PATH,
                run_dir,
                config(),
                limit=2,
                skip_model_graders=True,
                resume=True,
                agent_client=resumed,
                judge_client=JudgeClient(),
            )

        self.assertEqual(code, 0)
        self.assertEqual(resumed.calls, ["A02"])

    def test_resume_without_manifest_starts_in_completely_new_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            resumed = AgentClient()

            code = run_eval(
                DATA_PATH,
                run_dir,
                config(),
                case_id="A01",
                skip_model_graders=True,
                resume=True,
                agent_client=resumed,
                judge_client=JudgeClient(),
            )

        self.assertEqual(code, 0)
        self.assertEqual(resumed.calls, ["A01"])

    def test_resume_without_manifest_rejects_existing_checkpoints_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_eval(
                DATA_PATH,
                run_dir,
                config(model="old-model"),
                limit=2,
                skip_model_graders=True,
                agent_client=AgentClient(),
                judge_client=JudgeClient(),
            )
            manifest_path = run_dir / "run_manifest.json"
            manifest_path.unlink()
            checkpoint_paths = sorted((run_dir / "checkpoints").glob("*.json"))
            checkpoint_contents = {
                path.name: path.read_bytes() for path in checkpoint_paths
            }
            resumed = AgentClient()

            with self.assertRaisesRegex(ValueError, "manifest.*checkpoint"):
                run_eval(
                    DATA_PATH,
                    run_dir,
                    config(model="new-model"),
                    limit=2,
                    skip_model_graders=True,
                    resume=True,
                    agent_client=resumed,
                    judge_client=JudgeClient(),
                )

            self.assertFalse(manifest_path.exists())
            self.assertEqual(resumed.calls, [])
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in sorted((run_dir / "checkpoints").glob("*.json"))
                },
                checkpoint_contents,
            )

    def test_resume_completed_does_not_construct_or_call_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_eval(
                DATA_PATH,
                run_dir,
                config(),
                case_id="A01",
                skip_model_graders=True,
                agent_client=AgentClient(),
                judge_client=JudgeClient(),
            )
            with patch("run_eval.OpenAICompatibleLLMClient") as constructor:
                code = run_eval(
                    DATA_PATH,
                    run_dir,
                    config(),
                    case_id="A01",
                    skip_model_graders=True,
                    resume=True,
                )

        self.assertEqual(code, 0)
        constructor.assert_not_called()

    def test_resume_reruns_invalid_or_wrong_identity_completed_checkpoint(self):
        def corruptions(valid):
            missing_agent = dict(valid, agent_output=None)
            missing_grader = dict(valid)
            missing_grader["code_graders"] = dict(valid["code_graders"])
            missing_grader["code_graders"].pop("severity_match")
            cross_case = run_case(
                self.cases[1], AgentClient(), JudgeClient(), True
            ).model_dump(mode="json")
            return (
                "not-json",
                [],
                {"status": "completed"},
                cross_case,
                missing_agent,
                missing_grader,
            )

        for corruption_index in range(6):
            with self.subTest(corruption_index=corruption_index):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp) / "run"
                    run_eval(
                        DATA_PATH,
                        run_dir,
                        config(),
                        case_id="A01",
                        skip_model_graders=True,
                        agent_client=AgentClient(),
                        judge_client=JudgeClient(),
                    )
                    checkpoint_path = run_dir / "checkpoints" / "A01.json"
                    valid = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                    corrupted = corruptions(valid)[corruption_index]
                    if isinstance(corrupted, str):
                        checkpoint_path.write_text(corrupted, encoding="utf-8")
                    else:
                        checkpoint_path.write_text(
                            json.dumps(corrupted), encoding="utf-8"
                        )
                    resumed = AgentClient()

                    code = run_eval(
                        DATA_PATH,
                        run_dir,
                        config(),
                        case_id="A01",
                        skip_model_graders=True,
                        resume=True,
                        agent_client=resumed,
                        judge_client=JudgeClient(),
                    )

                self.assertEqual(code, 0)
                self.assertEqual(resumed.calls, ["A01"])

    def test_resume_rejects_malformed_manifest_with_value_error(self):
        malformed_values = ([], {}, {"fingerprint": "bad"})
        for malformed in malformed_values:
            with self.subTest(malformed=malformed):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp) / "run"
                    run_eval(
                        DATA_PATH,
                        run_dir,
                        config(),
                        case_id="A01",
                        skip_model_graders=True,
                        agent_client=AgentClient(),
                        judge_client=JudgeClient(),
                    )
                    (run_dir / "run_manifest.json").write_text(
                        json.dumps(malformed), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        ValueError, "resume manifest"
                    ):
                        run_eval(
                            DATA_PATH,
                            run_dir,
                            config(),
                            case_id="A01",
                            skip_model_graders=True,
                            resume=True,
                            agent_client=AgentClient(),
                            judge_client=JudgeClient(),
                        )

    def test_resume_rejects_fingerprint_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_eval(
                DATA_PATH,
                run_dir,
                config(),
                case_id="A01",
                skip_model_graders=True,
                agent_client=AgentClient(),
                judge_client=JudgeClient(),
            )
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                run_eval(
                    DATA_PATH,
                    run_dir,
                    config(model="different-model"),
                    case_id="A01",
                    skip_model_graders=True,
                    resume=True,
                    agent_client=AgentClient(),
                    judge_client=JudgeClient(),
                )

    def test_invalid_data_fails_before_client_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "bad.json"
            data.write_text("[]", encoding="utf-8")
            with patch("run_eval.OpenAICompatibleLLMClient") as constructor:
                with self.assertRaisesRegex(ValueError, "dataset"):
                    run_eval(data, Path(tmp) / "run", config())
        constructor.assert_not_called()

    def test_default_client_construction_failure_is_isolated_and_retried(self):
        constructed_client = AgentClient()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            with patch(
                "run_eval.OpenAICompatibleLLMClient",
                side_effect=[
                    RuntimeError("constructor failed " + SECRET),
                    constructed_client,
                ],
            ) as constructor:
                code = run_eval(
                    DATA_PATH,
                    run_dir,
                    config(),
                    limit=2,
                    skip_model_graders=True,
                )
            first = json.loads(
                (run_dir / "checkpoints" / "A01.json").read_text()
            )
            second = json.loads(
                (run_dir / "checkpoints" / "A02.json").read_text()
            )

        self.assertEqual(code, 2)
        self.assertEqual(constructor.call_count, 2)
        self.assertEqual(constructed_client.calls, ["A02"])
        self.assertEqual(first["status"], "error")
        self.assertEqual(len(first["code_graders"]), 6)
        self.assertNotIn(SECRET, first["error_message"])
        self.assertEqual(second["status"], "completed")

    def test_main_returns_zero_one_and_two(self):
        with patch("run_eval.load_config", return_value=config()), patch(
            "run_eval.run_eval", side_effect=[0, 2, ValueError("bad dataset")]
        ):
            self.assertEqual(main(["--run-id", "one"]), 0)
            self.assertEqual(main(["--run-id", "two"]), 2)
            self.assertEqual(main(["--run-id", "three"]), 1)


if __name__ == "__main__":
    unittest.main()
