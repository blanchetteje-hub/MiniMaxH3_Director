import io
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import desktop_app


BASE_SETTINGS = {
    "segment_length": "5",
    "total_length": "60",
    "megapixels": "0.5",
    "resume": "1",
    "steps": "6",
    "context_frames": "7",
    "refresh": "6",
    "repair": None,
    "model": "ministral",
    "first_frame": False,
    "loras": [],
}


class _CompletedProcess:
    def __init__(self, output="finished\n", return_code=0):
        self.stdout = io.StringIO(output)
        self.pid = 4321
        self.returncode = None
        self._final_return_code = return_code

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = self._final_return_code
        return self.returncode


class _RunningProcess:
    def __init__(self):
        self.stdout = io.StringIO("")
        self.pid = 5432
        self.returncode = None
        self.stopped = threading.Event()
        self.sent_signal = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if timeout is None:
            self.stopped.wait(2)
        elif not self.stopped.wait(timeout):
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode

    def send_signal(self, sent_signal):
        self.sent_signal = sent_signal
        self.returncode = 130
        self.stopped.set()


class DesktopBridgeTests(unittest.TestCase):
    def make_bridge(self):
        return desktop_app.MiniMaxBridge(
            script_path=Path(__file__),
            python_executable=sys.executable,
        )

    def test_build_command_matches_current_cli(self):
        settings = dict(BASE_SETTINGS)
        settings.update(
            {
                "resume": "3",
                "steps": "8",
                "context_frames": "12",
                "refresh": "5",
                "model": "qwen",
                "first_frame": True,
                "loras": [
                    {"name": "style.safetensors", "strength": "0.7"},
                    {"name": "motion.safetensors", "strength": "-0.25"},
                ],
            }
        )

        command = self.make_bridge().build_command(settings)

        self.assertEqual(command[:3], [sys.executable, "-u", str(Path(__file__).resolve())])
        self.assertEqual(command[3:6], ["5", "60", "0.5"])
        self.assertIn("--ff", command)
        self.assertEqual(
            [command[index + 1] for index, value in enumerate(command) if value == "--lora"],
            ["style.safetensors:0.7", "motion.safetensors:-0.25"],
        )
        self.assertEqual(command[command.index("--model") + 1], "qwen")

    def test_repair_rejects_non_default_resume(self):
        settings = dict(BASE_SETTINGS, repair="3", resume="2")
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            self.make_bridge().build_command(settings)

    def test_invalid_numbers_are_rejected(self):
        for value in ("", "0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                settings = dict(BASE_SETTINGS, megapixels=value)
                with self.assertRaises(ValueError):
                    self.make_bridge().build_command(settings)

    @mock.patch("desktop_app.subprocess.Popen")
    def test_start_collects_output_and_finishes(self, popen):
        process = _CompletedProcess("line one\nSEGMENT 2/12 (5 seconds)\nline two\n")
        popen.return_value = process
        bridge = self.make_bridge()

        result = bridge.start_generation(BASE_SETTINGS)
        deadline = time.monotonic() + 1
        while bridge.get_status()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertTrue(result["ok"])
        self.assertEqual(bridge.get_status()["state"], "succeeded")
        self.assertIn("SEGMENT 2/12", bridge.get_log_output()["text"])
        self.assertEqual(bridge.get_status()["current_segment"], 2)
        self.assertEqual(bridge.get_status()["total_segments"], 12)
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        self.assertEqual(kwargs["cwd"], str(Path(__file__).resolve().parent))
        self.assertTrue(kwargs["text"])
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            self.assertTrue(kwargs["start_new_session"])

    @mock.patch("desktop_app.subprocess.Popen")
    def test_second_run_is_rejected_and_stop_is_cancelled(self, popen):
        process = _RunningProcess()
        popen.return_value = process
        bridge = self.make_bridge()
        self.assertTrue(bridge.start_generation(BASE_SETTINGS)["ok"])

        second = bridge.start_generation(BASE_SETTINGS)
        self.assertFalse(second["ok"])
        self.assertEqual(popen.call_count, 1)

        if os.name == "nt":
            result = bridge.stop_generation()
            self.assertEqual(process.sent_signal, signal.CTRL_BREAK_EVENT)
        else:
            with mock.patch("desktop_app.os.killpg") as kill_group:
                def stop_group(_pid, sent_signal):
                    self.assertEqual(sent_signal, signal.SIGINT)
                    process.returncode = 130
                    process.stopped.set()

                kill_group.side_effect = stop_group
                result = bridge.stop_generation()
        self.assertTrue(result["ok"])

        deadline = time.monotonic() + 1
        while bridge.get_status()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(bridge.get_status()["state"], "cancelled")

    def test_file_api_is_allowlisted_and_saves_atomically(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story.txt"
            definition = {"story": ("Story", path, True)}
            with mock.patch.dict(desktop_app.FILE_DEFINITIONS, definition, clear=True):
                result = bridge.save_file("story", "A short story.\n")
                self.assertTrue(result["ok"])
                self.assertEqual(bridge.read_file("story")["content"], "A short story.\n")
                with self.assertRaisesRegex(ValueError, "Unknown project file"):
                    bridge.read_file("../../outside")

    def test_shutdown_stops_an_active_generation(self):
        bridge = self.make_bridge()
        with mock.patch.object(bridge, "is_running", return_value=True), mock.patch.object(
            bridge, "stop_generation"
        ) as stop:
            bridge.shutdown()
        stop.assert_called_once_with()

    def test_main_loads_absolute_file_uri_and_registers_close_cleanup(self):
        class FakeEvent:
            def __init__(self):
                self.handlers = []

            def __iadd__(self, handler):
                self.handlers.append(handler)
                return self

        with tempfile.TemporaryDirectory() as directory:
            index_path = Path(directory) / "index.html"
            index_path.write_text("<!doctype html>", encoding="utf-8")
            closed = FakeEvent()
            window = types.SimpleNamespace(
                events=types.SimpleNamespace(closed=closed)
            )
            fake_webview = types.SimpleNamespace(
                create_window=mock.Mock(return_value=window),
                start=mock.Mock(),
            )
            with mock.patch.object(
                desktop_app, "FRONTEND_INDEX", index_path
            ), mock.patch.dict(sys.modules, {"webview": fake_webview}):
                desktop_app.main()

        create_kwargs = fake_webview.create_window.call_args.kwargs
        self.assertEqual(create_kwargs["url"], index_path.as_uri())
        self.assertIsInstance(create_kwargs["js_api"], desktop_app.MiniMaxBridge)
        self.assertEqual(closed.handlers, [create_kwargs["js_api"].shutdown])
        fake_webview.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
