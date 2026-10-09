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


    def test_acceptance_rejects_unsupported_model(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "supported formatter model"):
                bridge.execute_acceptance(
                    {
                        "job_id": "bad-model",
                        "code_branch": "gpt-arc-refresh",
                        "model": "unsupported",
                    },
                    Path(temp),
                    Path(temp) / "result",
                )

    @mock.patch.object(bridge, "start_lmstudio_developer_log", return_value={})
    @mock.patch.object(bridge, "stop_lmstudio_developer_log", return_value={})
    @mock.patch.object(bridge, "copy_acceptance_artifacts", return_value={})
    @mock.patch.object(bridge, "run_local_process")
    @mock.patch.object(bridge, "ensure_exec_worktree")
    @mock.patch.object(bridge, "safe_source_path")
    def test_acceptance_allows_qwen_model(
        self, safe_source_path, ensure_worktree, run_process, _copy, _stop, _start
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "amy.jpg"
            image.write_bytes(b"image")
            safe_source_path.return_value = image
            ensure_worktree.return_value = root
            run_process.return_value = {
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
                "timeout_seconds": None,
                "started_at": 0,
                "finished_at": 1,
            }
            bridge.execute_acceptance(
                {
                    "job_id": "qwen-model",
                    "code_branch": "gpt-arc-refresh",
                    "model": "qwen",
                },
                root,
                root / "result",
            )
            command = run_process.call_args.args[0]
            self.assertIn("--model", command)
            self.assertEqual(command[command.index("--model") + 1], "qwen")

    @mock.patch.object(bridge, "start_lmstudio_developer_log", return_value={})
    @mock.patch.object(bridge, "stop_lmstudio_developer_log", return_value={})
    @mock.patch.object(bridge, "copy_acceptance_artifacts", return_value={})
    @mock.patch.object(bridge, "run_local_process")
    @mock.patch.object(bridge, "ensure_exec_worktree")
    def test_acceptance_director_plan_dir_requires_fixture_and_forwards_path(
        self, ensure_worktree, run_process, _copy, _stop, _start
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "amy.jpg").write_bytes(b"image")
            ensure_worktree.return_value = root
            run_process.return_value = {"returncode": 0}

            plan_dir = (
                root / "tests" / "acceptance" / "fixtures" / "tavern_run21_plan"
            )
            plan_dir.mkdir(parents=True)
            (plan_dir / "story_arc.json").write_text("{}\n", encoding="utf-8")
            (plan_dir / "beats.txt").write_text("Beat 1\n", encoding="utf-8")
            (plan_dir / "expanded_story.txt").write_text(
                "The saved expanded story.\n", encoding="utf-8"
            )

            job = {
                "job_id": "director-plan-fixture",
                "code_branch": bridge.ACCEPTANCE_CODE_BRANCH,
                "model": "gpt",
                "director_plan_dir": "tests/acceptance/fixtures/tavern_run21_plan",
            }
            bridge.execute_acceptance(job, root, root / "result")
            command = run_process.call_args.args[0]
            self.assertIn("--director-plan-dir", command)
            self.assertEqual(
                command[command.index("--director-plan-dir") + 1],
                str(plan_dir.resolve()),
            )

            outside_dir = root / "tests" / "acceptance" / "gold" / "plan"
            outside_dir.mkdir(parents=True)
            (outside_dir / "story_arc.json").write_text("{}\n", encoding="utf-8")
            (outside_dir / "beats.txt").write_text("Beat 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "under tests/acceptance/fixtures"):
                bridge.execute_acceptance(
                    {**job, "director_plan_dir": "tests/acceptance/gold/plan"},
                    root,
                    root / "result",
                )

            incomplete_dir = (
                root / "tests" / "acceptance" / "fixtures" / "incomplete_plan"
            )
            incomplete_dir.mkdir()
            (incomplete_dir / "story_arc.json").write_text("{}\n", encoding="utf-8")
            (incomplete_dir / "beats.txt").write_text("Beat 1\n", encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "expanded_story.txt"):
                bridge.execute_acceptance(
                    {
                        **job,
                        "director_plan_dir": (
                            "tests/acceptance/fixtures/incomplete_plan"
                        ),
                    },
                    root,
                    root / "result",
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



class ChatGPTLlamaBridgeGracefulStopTests(unittest.TestCase):
    def setUp(self):
        bridge._GRACEFUL_STOP_REQUESTED.clear()
        bridge._ACTIVE_LOCAL_PROCESS = None

    def tearDown(self):
        bridge._GRACEFUL_STOP_REQUESTED.clear()
        bridge._ACTIVE_LOCAL_PROCESS = None

    @mock.patch.object(bridge, "_terminate_active_local_process")
    def test_ctrl_q_request_sets_graceful_stop_without_hard_exit(self, terminate):
        bridge.request_bridge_graceful_stop()
        self.assertTrue(bridge._GRACEFUL_STOP_REQUESTED.is_set())
        terminate.assert_called_once_with()

    def test_run_local_process_marks_graceful_interrupt(self):
        bridge._GRACEFUL_STOP_REQUESTED.set()

        fake = _FakeProcess()
        fake.stdout = []
        fake.returncode = 130

        with mock.patch.object(bridge.subprocess, "Popen", return_value=fake):
            result = bridge.run_local_process(
                ["python", "-c", "pass"],
                Path.cwd(),
                timeout=1,
            )

        self.assertTrue(result["interrupted"])

    @mock.patch.object(bridge, "commit_result")
    @mock.patch.object(bridge, "execute_job")
    @mock.patch.object(bridge, "sync_branch")
    def test_process_once_publishes_interrupted_job_and_stops_before_next(
        self,
        sync_branch,
        execute_job,
        commit_result,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            worktree = root / "mailbox"
            jobs = worktree / "bridge" / "jobs"
            jobs.mkdir(parents=True)
            (jobs / "job-1.json").write_text(
                json.dumps({"job_id": "job-1", "kind": "run_tests"}),
                encoding="utf-8",
            )
            (jobs / "job-2.json").write_text(
                json.dumps({"job_id": "job-2", "kind": "run_tests"}),
                encoding="utf-8",
            )

            def interrupted_job(*args, **kwargs):
                bridge._GRACEFUL_STOP_REQUESTED.set()
                return {
                    "job_id": "job-1",
                    "kind": "run_tests",
                    "interrupted": True,
                    "bridge_stop_requested": True,
                }

            execute_job.side_effect = interrupted_job

            handled = bridge.process_once(
                root,
                worktree,
                "gpt-runtime",
                "http://127.0.0.1:1234",
                1024,
            )

            self.assertEqual(handled, 1)
            self.assertEqual(execute_job.call_count, 1)
            payload = json.loads(
                (
                    worktree
                    / "bridge"
                    / "results"
                    / "job-1"
                    / "result.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["status"], "interrupted")
            self.assertTrue(payload["interrupted"])
            commit_result.assert_called_once()


if __name__ == "__main__":
    unittest.main()
