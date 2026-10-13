import io
import json
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
    "generation_mode": "existing",
    "segment_length": "5",
    "total_segments": "12",
    "megapixels": "0.5",
    "resume": "1",
    "steps": "6",
    "context_frames": "7",
    "trim_frames": "2",
    "refresh": "6",
    "repair": None,
    "model": "mistral",
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
    def setUp(self):
        self.source_check = mock.patch.object(desktop_app.MiniMaxBridge, "_require_source")
        self.source_check.start()
        self.addCleanup(self.source_check.stop)

    def test_generation_mode_and_vram_actions(self):
        bridge = self.make_bridge()
        for mode in ("new", "existing"):
            for vram in ("16", "32"):
                with self.subTest(mode=mode, vram=vram):
                    settings = dict(BASE_SETTINGS, generation_mode=mode, vram_mode=vram)
                    prompts = bridge.build_command(settings, action="prompts")
                    self.assertIn("--generate-prompts", prompts)
                    self.assertIn("--" + mode, prompts)
                    self.assertNotIn("--generate-from-prompts", prompts)
                    render = bridge.build_command(settings, action="render")
                    self.assertIn("--generate-from-prompts", render)
                    self.assertNotIn("--generate-prompts", render)
                    self.assertNotIn("--" + mode, render)
                    if vram == "16":
                        with self.assertRaisesRegex(ValueError, "16GB"):
                            bridge.build_command(settings)
                    else:
                        self.assertIn("--" + mode, bridge.build_command(settings))

    def test_visual_style_is_passed_as_one_cli_argument(self):
        command = self.make_bridge().build_command(dict(
            BASE_SETTINGS,
            visual_style="hand-painted storybook animation",
        ))
        index = command.index("--visual-style")
        self.assertEqual(
            command[index + 1],
            "hand-painted storybook animation",
        )

    def test_render_uses_package_without_duration_settings(self):
        command = self.make_bridge().build_command({"generation_mode": "render_only"})
        self.assertEqual(command[3], "--generate-from-prompts")
        self.assertNotIn("--steps", command)
        custom = self.make_bridge().build_command({
            "generation_mode": "render_only", "use_prompts": "saved package.txt",
            "segment_length": "invalid", "total_segments": "invalid",
        })
        self.assertEqual(custom[3:5], ["--use-prompts", "saved package.txt"])

    def test_render_ignores_hidden_settings_from_previous_tabs(self):
        settings = dict(BASE_SETTINGS, generation_mode="render_only")
        for key in ("segment_length", "total_segments", "megapixels", "steps",
                    "trim_frames", "refresh", "vision_continuity", "model", "resume"):
            settings[key] = "invalid"
        settings.update(first_frame=True, retention=True, loras="invalid")
        command = self.make_bridge().build_command(settings)
        self.assertIn("--generate-from-prompts", command)
        for flag in ("--steps", "--ff", "--retention", "--lora", "--resume"):
            self.assertNotIn(flag, command)

    @mock.patch("desktop_app.subprocess.Popen")
    def test_render_requires_saved_package_before_launch(self, popen):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "minimax.py"
            script.write_text("", encoding="utf-8")
            bridge = desktop_app.MiniMaxBridge(script)
            with mock.patch.object(bridge, "_load_settings", return_value=dict(desktop_app.DEFAULT_SETTINGS)):
                result = bridge.start_generation({"generation_mode": "render_only"})
            self.assertFalse(result["ok"])
            self.assertIn("Generate prompts first", result["error"])
            popen.assert_not_called()

    @mock.patch("desktop_app.subprocess.Popen")
    def test_render_custom_relative_package_needs_no_story(self, popen):
        popen.return_value = _CompletedProcess()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "minimax.py"
            script.write_text("", encoding="utf-8")
            (Path(directory) / "saved.txt").write_text("saved prompts", encoding="utf-8")
            bridge = desktop_app.MiniMaxBridge(script)
            with mock.patch.object(bridge, "_load_settings", return_value=dict(desktop_app.DEFAULT_SETTINGS)):
                result = bridge.start_generation({"generation_mode": "render_only", "use_prompts": "saved.txt"})
            self.assertTrue(result["ok"])
            popen.assert_called_once()
            bridge._require_source.assert_not_called()

    def test_low_vram_rejects_mixed_or_diagnostic_modes(self):
        for field, value in (("repair", "3"), ("director_only", True),
                             ("test_prompt_generation", True),
                             ("use_prompts", "custom.txt")):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "16GB"):
                    self.make_bridge().build_command(dict(
                        BASE_SETTINGS, vram_mode="16", action="prompts", **{field: value}))

    @mock.patch("desktop_app.subprocess.Popen")
    def test_invalid_new_run_does_not_clear_beats_or_launch(self, popen):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "minimax.py"
            script.write_text("", encoding="utf-8")
            beats = Path(directory) / "beats.txt"
            beats.write_text("Keep these beats", encoding="utf-8")
            bridge = desktop_app.MiniMaxBridge(script)
            result = bridge.start_generation(dict(BASE_SETTINGS,
                generation_mode="new", total_segments="0"))
            self.assertFalse(result["ok"])
            popen.assert_not_called()
            self.assertEqual(beats.read_text(), "Keep these beats")

    @mock.patch("desktop_app.subprocess.Popen")
    def test_existing_requires_nonempty_beats_before_launch(self, popen):
        self.source_check.stop()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "minimax.py"
            script.write_text("", encoding="utf-8")
            bridge = desktop_app.MiniMaxBridge(script)
            result = bridge.start_generation(BASE_SETTINGS)
            self.assertFalse(result["ok"])
            self.assertIn("existing beats", result["error"])
            popen.assert_not_called()

    @mock.patch("desktop_app.subprocess.Popen")
    def test_existing_rejects_mismatched_beats_without_rewriting(self, popen):
        self.source_check.stop()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "minimax.py"
            script.write_text("", encoding="utf-8")
            beats = Path(directory) / "beats.txt"
            original = "1. One scene\n"
            beats.write_text(original, encoding="utf-8")
            bridge = desktop_app.MiniMaxBridge(script)
            result = bridge.start_generation(BASE_SETTINGS)
            self.assertFalse(result["ok"])
            self.assertIn("exactly 12 beats", result["error"])
            popen.assert_not_called()
            self.assertEqual(beats.read_text(encoding="utf-8"), original)

    def test_diagnostic_fixture_pair_validation_uses_cli(self):
        with self.assertRaisesRegex(ValueError, "capture-h3-fixture"):
            self.make_bridge().build_command(dict(BASE_SETTINGS, capture_h3_segment="2"))

    def test_legacy_saved_defaults_migrate_once(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "gui_settings.json"
            settings_path.write_text(
                '{"refresh": "6", "temp": "0.8"}',
                encoding="utf-8",
            )
            with mock.patch.object(desktop_app, "SETTINGS_FILE", settings_path):
                migrated = bridge.get_settings()
                persisted = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertEqual(migrated["refresh"], "999")
                self.assertNotIn("temp", migrated)
                self.assertNotIn("temp", persisted)
                self.assertEqual(persisted["settings_version"], 2)

                # A legacy saved temperature is ignored; refresh remains an
                # independently saved UI setting.
                persisted["refresh"] = "6"
                persisted["temp"] = "0.8"
                settings_path.write_text(json.dumps(persisted), encoding="utf-8")
                explicit = bridge.get_settings()
                self.assertEqual(explicit["refresh"], "6")
                self.assertNotIn("temp", explicit)

    def test_all_new_settings_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(desktop_app, "SETTINGS_FILE", Path(directory) / "settings.json"):
                settings = {key: value for key, value in desktop_app.DEFAULT_SETTINGS.items()
                            if key not in BASE_SETTINGS}
                self.assertTrue(self.make_bridge().save_settings(settings)["ok"])
                self.assertEqual(self.make_bridge().get_settings()["generation_mode"], "new")

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
                "trim_frames": "5",
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
        self.assertEqual(command[3:6], ["5", "12", "0.5"])
        self.assertIn("--ff", command)
        self.assertEqual(
            [command[index + 1] for index, value in enumerate(command) if value == "--lora"],
            ["style.safetensors:0.7", "motion.safetensors:-0.25"],
        )
        self.assertEqual(command[command.index("--model") + 1], "qwen")
        self.assertEqual(command[command.index("--trim-frames") + 1], "5")

    def test_build_command_forwards_retention_and_lora_directory(self):
        settings = dict(
            BASE_SETTINGS,
            retention=True,
            disable_subject_removal=True,
            lora_dir="/tmp/custom-loras",
        )

        command = self.make_bridge().build_command(settings)

        self.assertIn("--retention", command)
        self.assertIn("--disable-subject-removal", command)
        self.assertEqual(
            command[command.index("--lora_dir") + 1],
            "/tmp/custom-loras",
        )

    def test_build_command_maps_defined_images_to_numbered_arguments(self):
        settings = dict(
            BASE_SETTINGS,
            defined_images=[
                r"H:\Images\input\hero one.png",
                r"H:\Images\input\hero_two.png",
            ],
        )

        command = self.make_bridge().build_command(settings)

        self.assertEqual(
            command[command.index("--image1") + 1],
            r"H:\Images\input\hero one.png",
        )
        self.assertEqual(
            command[command.index("--image2") + 1],
            r"H:\Images\input\hero_two.png",
        )

    def test_more_than_six_defined_images_are_rejected(self):
        settings = dict(
            BASE_SETTINGS,
            defined_images=[f"reference_{index}.png" for index in range(7)],
        )

        with self.assertRaisesRegex(ValueError, "At most six"):
            self.make_bridge().build_command(settings)

    def test_partial_settings_save_persists_loras_and_preserves_configuration(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "gui_settings.json"
            settings_path.write_text(
                '{"comfyui_url": "http://comfy.test", "defined_images": ["hero.png"]}',
                encoding="utf-8",
            )
            loras = [
                {"name": "style.safetensors", "strength": "0.7"},
                {"name": "motion.safetensors", "strength": "-0.25"},
            ]

            with mock.patch.object(desktop_app, "SETTINGS_FILE", settings_path):
                result = bridge.save_settings({"loras": loras})
                persisted = json.loads(settings_path.read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertEqual(persisted["loras"], loras)
            self.assertEqual(persisted["comfyui_url"], "http://comfy.test")
            self.assertEqual(persisted["defined_images"], ["hero.png"])
            self.assertEqual(persisted["steps"], "6")

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
    def test_start_uses_defined_images_saved_by_configuration_panel(self, popen):
        popen.return_value = _CompletedProcess()
        bridge = self.make_bridge()

        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "gui_settings.json"
            settings_path.write_text(
                json.dumps({
                    "defined_images": [
                        r"H:\Images\input\configured hero.png",
                        r"H:\Images\input\configured_detail.png",
                    ]
                }),
                encoding="utf-8",
            )
            with mock.patch.object(desktop_app, "SETTINGS_FILE", settings_path):
                result = bridge.start_generation(BASE_SETTINGS)

        command = popen.call_args.args[0]
        self.assertTrue(result["ok"])
        self.assertEqual(
            command[command.index("--image1") + 1],
            r"H:\Images\input\configured hero.png",
        )
        self.assertEqual(
            command[command.index("--image2") + 1],
            r"H:\Images\input\configured_detail.png",
        )

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

    def test_story_arc_is_available_as_a_read_only_project_file(self):
        bridge = self.make_bridge()

        story_arc = next(
            item
            for item in bridge.get_file_settings()
            if item["key"] == "story_arc"
        )

        self.assertEqual(story_arc["label"], "Story arc")
        self.assertFalse(story_arc["editable"])
        self.assertEqual(Path(story_arc["path"]), desktop_app.PROJECT_DIR / "story_arc.json")

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
        self.assertTrue(create_kwargs["text_select"])
        self.assertEqual(closed.handlers, [create_kwargs["js_api"].shutdown])
        fake_webview.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
