import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "tools" / "chatgpt_llama_bridge.py"
SPEC = importlib.util.spec_from_file_location("chatgpt_llama_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class _FakeProcess:
    def __init__(self):
        self.pid = 12345
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


class ChatGPTLlamaBridgeDeveloperLogTests(unittest.TestCase):
    @mock.patch.object(bridge.time, "sleep")
    @mock.patch.object(bridge.subprocess, "Popen")
    @mock.patch.object(bridge.shutil, "which", return_value="lms")
    def test_acceptance_log_capture_streams_model_io_and_stats(
        self, which, popen, sleep
    ):
        fake_process = _FakeProcess()
        popen.return_value = fake_process

        with tempfile.TemporaryDirectory() as temp:
            result_dir = Path(temp) / "result"
            capture = bridge.start_lmstudio_developer_log(result_dir)

            command = popen.call_args.args[0]
            self.assertEqual(command[:3], ["lms", "log", "stream"])
            self.assertIn("--source", command)
            self.assertIn("model", command)
            self.assertIn("--filter", command)
            self.assertIn("input,output", command)
            self.assertIn("--json", command)
            self.assertIn("--stats", command)

            artifacts = bridge.stop_lmstudio_developer_log(
                capture, result_dir
            )

            self.assertTrue(fake_process.terminated)
            self.assertEqual(
                Path(artifacts["developer_log.jsonl"]),
                Path("files") / "developer_log.jsonl",
            )
            self.assertEqual(
                Path(artifacts["developer_log.stderr.log"]),
                Path("files") / "developer_log.stderr.log",
            )

    @mock.patch.object(bridge.shutil, "which", return_value=None)
    def test_missing_lms_cli_still_publishes_diagnostic_document(self, which):
        with tempfile.TemporaryDirectory() as temp:
            result_dir = Path(temp) / "result"
            with mock.patch.object(Path, "is_file", return_value=False):
                capture = bridge.start_lmstudio_developer_log(result_dir)

            payload = json.loads(
                capture["log_path"].read_text(encoding="utf-8")
            )
            self.assertIn("bridge_log_capture_error", payload)


    def test_acceptance_rejects_nonbaseline_model(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "must use the 'gpt' baseline"):
                bridge.execute_acceptance(
                    {
                        "job_id": "bad-model",
                        "code_branch": "gpt-arc-refresh",
                        "model": "mistral",
                    },
                    Path(temp),
                    Path(temp) / "result",
                )

    def test_acceptance_rejects_nonbaseline_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "must run on 'gpt-arc-refresh'"):
                bridge.execute_acceptance(
                    {
                        "job_id": "bad-branch",
                        "code_branch": "gpt-test-branch",
                        "model": "gpt",
                    },
                    Path(temp),
                    Path(temp) / "result",
                )



class ChatGPTLlamaBridgePytestTests(unittest.TestCase):
    @mock.patch.object(bridge, "run_local_process")
    @mock.patch.object(bridge, "_select_pytest_runner")
    @mock.patch.object(bridge, "ensure_code_test_worktree")
    def test_run_tests_streams_through_managed_process(
        self, ensure_worktree, select_runner, run_process
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_example.py").write_text(
                "def test_example():\n    assert True\n",
                encoding="utf-8",
            )
            ensure_worktree.return_value = root
            select_runner.return_value = ["python", "-m", "pytest"]
            run_process.return_value = {
                "command": ["python", "-m", "pytest"],
                "returncode": 0,
                "stdout": "passed",
                "stderr": "",
                "timed_out": False,
                "timeout_seconds": None,
                "started_at": 1.0,
                "finished_at": 2.0,
            }

            result = bridge.run_pytest_job(
                root,
                {
                    "code_branch": "gpt-arc-refresh",
                    "tests": ["tests/test_example.py"],
                    "timeout_seconds": 120,
                },
            )

        command, cwd, timeout = run_process.call_args.args
        self.assertEqual(command[:4], ["python", "-m", "pytest", "-vv"])
        self.assertEqual(cwd, root)
        self.assertEqual(timeout, 120)
        self.assertTrue(result["passed"])
        self.assertFalse(result["timed_out"])


if __name__ == "__main__":
    unittest.main()
