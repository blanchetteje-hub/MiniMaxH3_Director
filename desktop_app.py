"""pywebview desktop shell for the existing ``minimax.py`` CLI.

The UI deliberately treats the generator as an external process.  This keeps
the command-line application, its checkpointing, and its emergency-stop
handling as the single source of truth.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from minimax import (
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_STORY_TEMPERATURE,
    LORA_DIRECTORY,
    parse_args,
    require_existing_beats,
)


PROJECT_DIR = Path(__file__).resolve().parent
MINIMAX_SCRIPT = PROJECT_DIR / "minimax.py"
FRONTEND_INDEX = PROJECT_DIR / "frontend" / "dist" / "index.html"
SETTINGS_FILE = PROJECT_DIR / "gui_settings.json"

DEFAULT_SETTINGS = {
    "settings_version": 2,
    "generation_mode": "new",
    "vram_mode": "32",
    "action": "generate",
    "use_prompts": "",
    "test_prompt_generation": False,
    "director_only": False,
    "capture_h3_segment": "",
    "capture_h3_fixture": "",
    "capture_h3_validation_segment": "",
    "capture_h3_validation_fixture": "",
    "comfyui_url": "http://127.0.0.1:8188",
    "llm_host_url": "http://127.0.0.1:1234",
    "defined_images": [],
    "segment_length": "",
    "total_segments": "",
    "megapixels": "0.5",
    "resume": "1",
    "steps": "6",
    "trim_frames": "2",
    "refresh": str(DEFAULT_REFRESH_INTERVAL),
    "vision_continuity": "0",
    "retention": False,
    "disable_subject_removal": False,
    "repair": "",
    "model": "gpt",
    "temp": str(DEFAULT_STORY_TEMPERATURE),
    "first_frame": False,
    "loras": [],
    "beat_count": "",
    "beat_length": "",
    "lora_dir": LORA_DIRECTORY,
}


FILE_DEFINITIONS = {
    "story": ("Story", PROJECT_DIR / "story.txt", True),
    "beats": ("Beats", PROJECT_DIR / "beats.txt", True),
    "generated_prompts": ("Generated prompts", PROJECT_DIR / "generated_prompts.txt", True),
    "canonical_data": ("Canonical data", PROJECT_DIR / "canonical_data.txt", True),
    "subjects": ("Subjects", PROJECT_DIR / "subjects.txt", True),
    "phrase_exclusions": (
        "Phrase exclusions",
        PROJECT_DIR / "phrase_exclusions.txt",
        True,
    ),
    "generation_state": (
        "Generation state",
        PROJECT_DIR / "generation_state.json",
        False,
    ),
    "story_arc": (
        "Story arc",
        PROJECT_DIR / "story_arc.json",
        False,
    ),
    "initial_workflow": (
        "Initial workflow",
        PROJECT_DIR / "Minimax_auto_API.json",
        False,
    ),
    "append_workflow": (
        "Append workflow",
        PROJECT_DIR / "Minimax_auto_append_API.json",
        False,
    ),
    "repair_workflow": ("Repair workflow", PROJECT_DIR / "Minimax_auto_repair_API.json", False),
    "refresh_workflow": (
        "Refresh workflow",
        PROJECT_DIR / "Minimax_auto_refresh_API.json",
        False,
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _story_temperature(value: Any) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Story temperature must be a number.") from error
    if not math.isfinite(value) or value < 0:
        raise ValueError("Story temperature must be finite and zero or greater.")
    return value


def _positive_float(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number.") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return parsed


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number greater than zero.")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label} must be a whole number greater than zero."
        ) from error
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return parsed


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number zero or greater.")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label} must be a whole number zero or greater."
        ) from error
    if parsed < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return parsed


def _number_argument(value: float) -> str:
    return format(value, ".15g")


def _defined_images(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Defined images must be a list.")
    if len(value) > 6:
        raise ValueError("At most six defined images can be used.")

    images = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"Defined image {index} must be a non-empty path.")
        images.append(item.strip())
    return images


class MiniMaxBridge:
    """Thread-safe API exposed to React through ``window.pywebview.api``."""

    def __init__(
        self,
        script_path: Path | str = MINIMAX_SCRIPT,
        python_executable: str = sys.executable,
    ) -> None:
        self.script_path = Path(script_path).resolve()
        self.python_executable = python_executable
        self._lock = threading.RLock()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        self._env = env
        self._process: subprocess.Popen[str] | None = None
        self._logs: list[str] = []
        self._status: dict[str, Any] = {
            "state": "idle",
            "message": "Ready",
            "running": False,
            "pid": None,
            "return_code": None,
            "current_segment": None,
            "total_segments": None,
            "command": [],
            "command_display": "",
            "started_at": None,
            "ended_at": None,
        }

    @staticmethod
    def _load_settings() -> dict[str, Any]:
        if SETTINGS_FILE.is_file():
            try:
                content = SETTINGS_FILE.read_text(encoding="utf-8")
                saved = json.loads(content)
                if isinstance(saved, dict):
                    saved = dict(saved)
                    if (
                        "llm_host_url" not in saved
                        and "lm_studio_url" in saved
                    ):
                        saved["llm_host_url"] = saved.pop("lm_studio_url")
                    if "total_segments" not in saved and saved.get("total_length"):
                        try:
                            saved["total_segments"] = str(math.ceil(
                                float(saved["total_length"]) / float(saved["segment_length"])
                            ))
                        except (ValueError, TypeError, ZeroDivisionError, KeyError):
                            pass
                    saved.pop("total_length", None)
                    saved.pop("generate_all", None)
                    try:
                        settings_version = int(saved.get("settings_version", 1))
                    except (TypeError, ValueError):
                        settings_version = 1
                    if settings_version < 2:
                        # Migrate only the historical defaults once. After the
                        # version bump, an explicit user-selected 6 / 0.8 is kept.
                        if str(saved.get("refresh", "")).strip() == "6":
                            saved["refresh"] = str(DEFAULT_REFRESH_INTERVAL)
                        if str(saved.get("temp", "")).strip() == "0.8":
                            saved["temp"] = str(DEFAULT_STORY_TEMPERATURE)
                        saved["settings_version"] = 2
                        try:
                            SETTINGS_FILE.write_text(
                                json.dumps({**DEFAULT_SETTINGS, **saved}, indent=2),
                                encoding="utf-8",
                            )
                        except OSError:
                            pass
                    return {**DEFAULT_SETTINGS, **saved}
            except (OSError, ValueError):
                pass
        return dict(DEFAULT_SETTINGS)

    @staticmethod
    def _save_settings(settings: dict[str, Any]) -> bool:
        try:
            content = json.dumps(settings, indent=2)
            SETTINGS_FILE.write_text(content, encoding="utf-8")
            return True
        except (OSError, ValueError):
            return False

    def get_settings(self) -> dict[str, Any]:
        return self._load_settings()

    def save_settings(self, settings: Any) -> dict[str, Any]:
        if not isinstance(settings, dict):
            return {"ok": False, "error": "Settings must be an object."}

        unknown_fields = settings.keys() - DEFAULT_SETTINGS.keys()
        if unknown_fields:
            return {
                "ok": False,
                "error": f"Unknown settings: {', '.join(sorted(unknown_fields))}",
            }

        if "defined_images" in settings:
            try:
                settings = dict(settings)
                settings["defined_images"] = _defined_images(
                    settings["defined_images"]
                )
            except ValueError as error:
                return {"ok": False, "error": str(error)}

        if "loras" in settings and not isinstance(settings["loras"], list):
            return {"ok": False, "error": "LoRAs must be a list."}

        with self._lock:
            merged_settings = {**self._load_settings(), **settings}
            saved = self._save_settings(merged_settings)
        if saved:
            return {"ok": True, "settings": merged_settings}
        return {"ok": False, "error": "Failed to save settings."}

    @staticmethod
    def _validate_settings(settings: Any) -> dict[str, Any]:
        if not isinstance(settings, dict):
            raise ValueError("Generation settings must be an object.")

        validated: dict[str, Any] = {
            "segment_length": _positive_float(
                settings.get("segment_length"), "Segment duration"
            ),
            "total_segments": _positive_int(
                settings.get("total_segments"), "Number of segments"
            ),
            "megapixels": _positive_float(
                settings.get("megapixels"), "Megapixels"
            ),
            "steps": _positive_int(settings.get("steps", 6), "Steps"),
            "trim_frames": _non_negative_int(
                settings.get("trim_frames", 2), "Trim frames"
            ),
            "refresh": _positive_int(
                settings.get("refresh", DEFAULT_REFRESH_INTERVAL), "Legacy refresh fallback"
            ),
            "vision_continuity": _non_negative_int(
                settings.get("vision_continuity", 0), "Vision continuity"
            ),
            "retention": bool(settings.get("retention", False)),
            "disable_subject_removal": bool(
                settings.get("disable_subject_removal", False)
            ),
            "resume": _positive_int(
                settings.get("resume", 1), "Resume segment"
            ),
            "first_frame": bool(settings.get("first_frame", False)),
        }

        model = str(settings.get("model", "gpt")).strip().lower()
        if model not in {"gpt", "mistral", "qwen"}:
            raise ValueError("Model formatter must be 'gpt', 'mistral', or 'qwen'.")
        validated["model"] = model
        validated["temp"] = _story_temperature(settings.get("temp", DEFAULT_STORY_TEMPERATURE))

        repair_value = settings.get("repair")
        if repair_value not in (None, ""):
            repair = _positive_int(repair_value, "Repair segment")
            if repair == 1:
                raise ValueError("Repair requires a middle segment, not segment 1.")
            if validated["resume"] != 1:
                raise ValueError("Repair cannot be combined with resume.")
            validated["repair"] = repair
        else:
            validated["repair"] = None

        raw_loras = settings.get("loras", [])
        if raw_loras is None:
            raw_loras = []
        if not isinstance(raw_loras, list):
            raise ValueError("LoRAs must be a list.")
        loras: list[tuple[str, float]] = []
        for index, item in enumerate(raw_loras, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"LoRA {index} must include a name and strength.")
            name = str(item.get("name", "")).strip()
            if not name or ":" in name:
                raise ValueError(
                    f"LoRA {index} needs a name that does not contain ':'."
                )
            try:
                strength = float(item.get("strength"))
            except (TypeError, ValueError) as error:
                raise ValueError(f"LoRA {index} strength must be a number.") from error
            if not math.isfinite(strength):
                raise ValueError(f"LoRA {index} strength must be finite.")
            loras.append((name, strength))
        validated["loras"] = loras
        lora_dir = settings.get("lora_dir", LORA_DIRECTORY)
        validated["lora_dir"] = (
            LORA_DIRECTORY if lora_dir is None else str(lora_dir).strip()
        )
        validated["defined_images"] = _defined_images(
            settings.get("defined_images", [])
        )
        return validated

    def build_command(
        self,
        settings: Any,
        generate_beats: bool = False,
        action: str | None = None,
    ) -> list[str]:
        """Build the exact argv shape consumed by ``minimax.py``."""

        if generate_beats:
            if not isinstance(settings, dict):
                raise ValueError("Generation settings must be an object.")
            if str(settings.get("vram_mode", "32")) == "16":
                raise ValueError("16GB mode only supports generating prompts or video from prompts.")
            beat_count = _positive_int(settings.get("beat_count"), "Story beats")
            beat_length = _positive_float(
                settings.get("beat_length") or settings.get("segment_length"),
                "Beat duration",
            )
            model = str(settings.get("model", "gpt")).strip().lower()
            if model not in {"gpt", "mistral", "qwen"}:
                raise ValueError("Model formatter must be 'gpt', 'mistral', or 'qwen'.")
            return [
                self.python_executable,
                "-u",
                str(self.script_path),
                "--generate-beats",
                str(beat_count),
                _number_argument(beat_length),
                "--model",
                model,
                "--temp",
                _number_argument(_story_temperature(settings.get("temp", DEFAULT_STORY_TEMPERATURE))),
            ]

        if not isinstance(settings, dict):
            raise ValueError("Generation settings must be an object.")
        mode = settings.get("generation_mode", "new")
        vram = str(settings.get("vram_mode", "32"))
        operation = action or settings.get("action", "generate")
        if mode not in {"new", "existing", "render_only"}:
            raise ValueError("Choose New, Existing, or Render-Only.")
        if vram not in {"16", "32"}:
            raise ValueError("VRAM mode must be 16 or 32.")
        if operation not in {"generate", "prompts", "render"}:
            raise ValueError("Unknown generation action.")
        render = mode == "render_only" or operation == "render"
        custom_prompts = str(settings.get("use_prompts") or "").strip()
        diagnostics = any(settings.get(key) for key in (
            "test_prompt_generation", "director_only",
            "capture_h3_segment", "capture_h3_fixture",
            "capture_h3_validation_segment", "capture_h3_validation_fixture",
        ))
        if vram == "16":
            if not render and operation != "prompts":
                raise ValueError("16GB mode requires Generate Prompts (LLM) or Generate Video (ComfyUI).")
            if diagnostics or settings.get("repair") or custom_prompts:
                raise ValueError("16GB mode does not support diagnostics, repair, or custom prompt packages.")
        if render and (diagnostics or settings.get("repair")):
            raise ValueError("Render-Only cannot be combined with diagnostics or repair.")
        if not render and custom_prompts:
            raise ValueError("Custom prompt packages belong in Render-Only.")
        effective = dict(settings)
        if render:
            effective.update(segment_length=1, total_segments=1, megapixels=0.5,
                             steps=6, trim_frames=2, refresh=DEFAULT_REFRESH_INTERVAL, vision_continuity=0,
                             model="gpt", resume=1, first_frame=False,
                             retention=False, disable_subject_removal=False,
                             loras=[], temp=DEFAULT_STORY_TEMPERATURE)
        values = self._validate_settings(effective)
        command = [
            self.python_executable,
            "-u",
            str(self.script_path),
            _number_argument(values["segment_length"]),
            _number_argument(values["total_segments"]),
            _number_argument(values["megapixels"]),
            "--resume",
            str(values["resume"]),
            "--steps",
            str(values["steps"]),
            "--trim-frames",
            str(values["trim_frames"]),
            "--refresh",
            str(values["refresh"]),
            *(("--retention",) if values["retention"] else ()),
            *(("--disable-subject-removal",)
              if values["disable_subject_removal"] else ()),
            "--vision-continuity",
            str(values["vision_continuity"]),
            "--model",
            values["model"],
        ]
        if render:
            # Timing and rendering options come from the saved prompt package.
            command = command[:3]
            command.extend(("--use-prompts", custom_prompts) if custom_prompts
                           else ("--generate-from-prompts",))
        else:
            command.extend(("--temp", _number_argument(values["temp"])))
            command.append("--new" if mode == "new" else "--existing")
            if operation == "prompts":
                command.extend(("--generate-prompts", str(values["total_segments"])))
            for key in ("test_prompt_generation", "director_only"):
                if settings.get(key):
                    command.append("--" + key.replace("_", "-"))
            for key in ("capture_h3_segment", "capture_h3_validation_segment"):
                if settings.get(key) not in (None, ""):
                    command.extend(("--" + key.replace("_", "-"),
                                    str(_positive_int(settings[key], key.replace("_", " ")))))
            for key in ("capture_h3_fixture", "capture_h3_validation_fixture"):
                if settings.get(key):
                    command.extend(("--" + key.replace("_", "-"), str(settings[key]).strip()))
        if values["repair"] is not None:
            command.extend(("--repair", str(values["repair"])))
        if values["first_frame"]:
            command.append("--ff")
        lora_dir = values.get("lora_dir", LORA_DIRECTORY)
        if lora_dir:
            command.extend(("--lora_dir", str(lora_dir)))
        for name, strength in values["loras"]:
            command.extend(("--lora", f"{name}:{_number_argument(strength)}"))
        for image_number, image_path in enumerate(
            values["defined_images"],
            start=1,
        ):
            command.extend((f"--image{image_number}", image_path))
        errors = io.StringIO()
        try:
            with contextlib.redirect_stderr(errors):
                parse_args(command[3:])
        except SystemExit as error:
            detail = errors.getvalue().strip().split("error:")[-1].strip()
            raise ValueError(detail or "Invalid generation arguments.") from error
        return command

    def _require_source(self, source: str, total_segments: int | None = None) -> None:
        source_path = self.script_path.parent / (source + ".txt")
        if not source_path.is_file() or not source_path.read_text(encoding="utf-8").strip():
            raise ValueError(f"{source}.txt must contain {'a story' if source == 'story' else 'existing beats'}.")
        if source == "beats" and total_segments is not None:
            require_existing_beats(str(source_path), total_segments)

    def start_generation(
        self,
        settings: Any,
        generate_beats: bool = False,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Start ``minimax.py`` without blocking the pywebview UI thread."""

        with self._lock:
            if self._status["state"] == "starting" or self._process is not None:
                return {
                    "ok": False,
                    "error": "Generation is already running.",
                    "status": dict(self._status),
                }
            self._status.update(
                {
                    "state": "starting",
                    "message": (
                        "Starting story generation"
                        if generate_beats
                        else "Starting generation"
                    ),
                    "running": True,
                    "operation": "story" if generate_beats else "video",
                    "return_code": None,
                    "current_segment": None,
                    "total_segments": None,
                    "ended_at": None,
                }
            )

        try:
            if generate_beats:
                _label, story_path, _editable = self._get_file_definition("story")
                try:
                    story_source = story_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    story_source = ""
                if not story_source.strip():
                    raise ValueError("story.txt must have a story defined.")
            effective_settings = (
                {**self._load_settings(), **settings}
                if isinstance(settings, dict)
                else settings
            )
            command = self.build_command(
                effective_settings,
                generate_beats=generate_beats,
                action=action,
            )
            if not generate_beats:
                mode = effective_settings.get("generation_mode", "new")
                operation = action or effective_settings.get("action", "generate")
                if mode == "render_only" or operation == "render":
                    package_name = str(effective_settings.get("use_prompts") or "generated_prompts.txt").strip()
                    package_path = Path(package_name).expanduser()
                    if not package_path.is_absolute():
                        package_path = self.script_path.parent / package_path
                    if not package_path.is_file() or not package_path.read_text(encoding="utf-8").strip():
                        raise ValueError(f"Saved prompt package is missing or empty: {package_path}. Generate prompts first.")
                else:
                    source = "story" if mode == "new" else "beats"
                    self._require_source(source, _positive_int(
                        effective_settings.get("total_segments"), "Number of segments"
                    ) if source == "beats" else None)
            if not self.script_path.is_file():
                raise FileNotFoundError(f"Generator not found: {self.script_path}")

            popen_options: dict[str, Any] = {
                "cwd": str(self.script_path.parent),
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
            }
            child_env = self._env.copy()
            if isinstance(effective_settings, dict):
                for environment_name, setting_name in (
                    ("MINIMAX_COMFY_URL", "comfyui_url"),
                    ("MINIMAX_LLM_HOST_URL", "llm_host_url"),
                ):
                    value = str(effective_settings.get(setting_name, "")).strip()
                    if value:
                        child_env[environment_name] = value.rstrip("/")
            popen_options["env"] = child_env
            if os.name == "nt":
                popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_options["start_new_session"] = True

            process = subprocess.Popen(command, **popen_options)
        except Exception as error:
            with self._lock:
                self._status.update(
                    {
                        "state": "error",
                        "message": str(error),
                        "running": False,
                        "return_code": None,
                        "ended_at": _utc_now(),
                    }
                )
                self._logs.append(f"[desktop] Could not start generation: {error}\n")
                status = dict(self._status)
            return {"ok": False, "error": str(error), "status": status}

        display = (
            subprocess.list2cmdline(command)
            if os.name == "nt"
            else shlex.join(command)
        )
        with self._lock:
            self._process = process
            self._logs.append(f"[desktop] Starting: {display}\n")
            self._status = {
                "state": "running",
                "message": (
                    "Story generation is running"
                    if generate_beats
                    else "Generation is running"
                ),
                "running": True,
                "operation": "story" if generate_beats else "video",
                "pid": process.pid,
                "return_code": None,
                "current_segment": None,
                "total_segments": None,
                "command": command,
                "command_display": display,
                "started_at": _utc_now(),
                "ended_at": None,
            }

        reader_thread = threading.Thread(
            target=self._collect_output,
            args=(process,),
            name="minimax-output",
            daemon=True,
        )
        reader_thread.start()
        threading.Thread(
            target=self._watch_process,
            args=(process, reader_thread),
            name="minimax-waiter",
            daemon=True,
        ).start()
        return {"ok": True, "status": self.get_status()}

    def _collect_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        try:
            for line in process.stdout:
                with self._lock:
                    self._logs.append(line)
                    segment_match = re.search(
                        r"\bSEGMENT\s+(\d+)/(\d+)\b",
                        line,
                        flags=re.IGNORECASE,
                    )
                    if segment_match:
                        current, total = map(int, segment_match.groups())
                        self._status.update(
                            {
                                "current_segment": current,
                                "total_segments": total,
                                "message": f"Generating segment {current} of {total}",
                            }
                        )
                    else:
                        repair_match = re.search(
                            r"\bREPAIR SEGMENT\s+(\d+)\b",
                            line,
                            flags=re.IGNORECASE,
                        )
                        if repair_match:
                            current = int(repair_match.group(1))
                            self._status.update(
                                {
                                    "current_segment": current,
                                    "message": f"Repairing segment {current}",
                                }
                            )
        finally:
            process.stdout.close()

    def _watch_process(
        self,
        process: subprocess.Popen[str],
        reader_thread: threading.Thread,
    ) -> None:
        return_code = process.wait()
        if reader_thread is not threading.current_thread():
            reader_thread.join(timeout=1)

        with self._lock:
            if self._process is not process:
                return
            prior_state = self._status["state"]
            if return_code == 0:
                state = "succeeded"
                message = (
                    "Story generation completed"
                    if self._status.get("operation") == "story"
                    else "Generation completed"
                )
            elif prior_state == "stopping":
                state, message = "cancelled", "Generation stopped"
            else:
                state, message = "error", f"Generation exited with code {return_code}"
            self._logs.append(
                f"[desktop] Process finished with exit code {return_code}.\n"
            )
            self._status.update(
                {
                    "state": state,
                    "message": message,
                    "running": False,
                    "return_code": return_code,
                    "ended_at": _utc_now(),
                }
            )
            self._process = None

    def stop_generation(self) -> dict[str, Any]:
        """Request the engine's emergency stop, then kill its tree if needed."""

        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return {"ok": True, "status": dict(self._status)}
            self._status.update(
                {"state": "stopping", "message": "Stopping generation"}
            )
            self._logs.append("[desktop] Stop requested.\n")

        self._signal_process(process)
        return {"ok": True, "status": self.get_status()}

    def _signal_process(self, process: subprocess.Popen[str]) -> None:
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=5)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
            else:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def get_log_output(self, offset: Any = 0) -> dict[str, Any]:
        try:
            start = max(0, int(offset))
        except (TypeError, ValueError):
            start = 0
        with self._lock:
            output = "".join(self._logs)
        if start > len(output):
            start = 0
        return {"text": output[start:], "next_offset": len(output)}

    def clear_log_output(self) -> dict[str, Any]:
        with self._lock:
            self._logs.clear()
        return {"ok": True, "next_offset": 0}

    def is_running(self) -> bool:
        with self._lock:
            return self._status["state"] == "starting" or (
                self._process is not None and self._process.poll() is None
            )

    def get_file_settings(self) -> list[dict[str, Any]]:
        files = []
        for key, (label, path, editable) in FILE_DEFINITIONS.items():
            exists = path.is_file()
            stat = path.stat() if exists else None
            files.append(
                {
                    "key": key,
                    "label": label,
                    "path": str(path),
                    "editable": editable,
                    "exists": exists,
                    "size": stat.st_size if stat else 0,
                    "modified_at": (
                        datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat()
                        if stat
                        else None
                    ),
                }
            )
        return files

    @staticmethod
    def _get_file_definition(file_key: Any) -> tuple[str, Path, bool]:
        try:
            return FILE_DEFINITIONS[str(file_key)]
        except KeyError as error:
            raise ValueError("Unknown project file.") from error

    def read_file(self, file_key: Any) -> dict[str, Any]:
        _label, path, editable = self._get_file_definition(file_key)
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            content = ""
        return {
            "key": str(file_key),
            "content": content,
            "editable": editable,
            "exists": path.is_file(),
        }

    def save_file(self, file_key: Any, content: Any) -> dict[str, Any]:
        _label, path, editable = self._get_file_definition(file_key)
        if not editable:
            return {"ok": False, "error": "This project file is read-only."}
        if self.is_running():
            return {
                "ok": False,
                "error": "Project files cannot be changed during generation.",
            }
        if not isinstance(content, str):
            return {"ok": False, "error": "File content must be text."}

        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.replace(temporary_name, path)
        except OSError as error:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
            return {"ok": False, "error": str(error)}
        return {"ok": True, "file": self.read_file(file_key)}

    def shutdown(self, *_args: Any) -> None:
        if self.is_running():
            self.stop_generation()


def main() -> None:
    if not FRONTEND_INDEX.is_file():
        raise SystemExit(
            "React production build not found at "
            f"{FRONTEND_INDEX}. Run `cd frontend && npm install && npm run build`."
        )
    try:
        import webview
    except ImportError as error:
        raise SystemExit(
            "pywebview is not installed. Run `python -m pip install pywebview`."
        ) from error

    bridge = MiniMaxBridge()
    window = webview.create_window(
        "MiniMaxH3 Continuous Video Automator",
        url=FRONTEND_INDEX.as_uri(),
        js_api=bridge,
        width=1180,
        height=820,
        min_size=(820, 620),
        background_color="#0b1017",
        text_select=True,
    )
    window.events.closed += bridge.shutdown
    try:
        webview.start(debug=os.environ.get("MINIMAX_DESKTOP_DEBUG") == "1")
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    main()
