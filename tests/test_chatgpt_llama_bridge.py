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


if __name__ == "__main__":
    unittest.main()
