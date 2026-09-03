"""pywebview desktop shell for the existing ``minimax.py`` CLI.

The UI deliberately treats the generator as an external process.  This keeps
the command-line application, its checkpointing, and its emergency-stop
handling as the single source of truth.
"""

from __future__ import annotations

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


PROJECT_DIR = Path(__file__).resolve().parent
MINIMAX_SCRIPT = PROJECT_DIR / "minimax.py"
FRONTEND_INDEX = PROJECT_DIR / "frontend" / "dist" / "index.html"
SETTINGS_FILE = PROJECT_DIR / "gui_settings.json"

DEFAULT_SETTINGS = {
    "comfyui_url": "http://127.0.0.1:8188",
    "lm_studio_url": "http://127.0.0.1:1234",
    "defined_images": [],
    "segment_length": "",
    "total_length": "",
    "megapixels": "",
    "resume": "1",
    "steps": "6",
    "context_frames": "7",
    "refresh": "6",
    "repair": "",
    "model": "ministral",
    "first_frame": False,
    "loras": [],
}


FILE_DEFINITIONS = {
    "story": ("Story", PROJECT_DIR / "story.txt", True),
    "beats": ("Beats", PROJECT_DIR / "beats.txt", True),
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
    "refresh_workflow": (
        "Refresh workflow",
        PROJECT_DIR / "Minimax_auto_refresh_API.json",
        False,
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _number_argument(value: float) -> str:
    return format(value, ".15g")


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

        if "defined_images" in settings and not isinstance(
            settings["defined_images"], list
        ):
            return {"ok": False, "error": "Defined images must be a list."}

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
            "total_length": _positive_float(
                settings.get("total_length"), "Total duration"
            ),
            "megapixels": _positive_float(
                settings.get("megapixels"), "Megapixels"
            ),
            "steps": _positive_int(settings.get("steps", 6), "Steps"),
            "context_frames": _positive_int(
                settings.get("context_frames", 7), "Context frames"
            ),
            "refresh": _positive_int(
                settings.get("refresh", 6), "Refresh interval"
            ),
            "resume": _positive_int(
                settings.get("resume", 1), "Resume segment"
            ),
            "first_frame": bool(settings.get("first_frame", False)),
        }

        model = str(settings.get("model", "ministral")).strip().lower()
        if model not in {"ministral", "qwen"}:
            raise ValueError("Model formatter must be 'ministral' or 'qwen'.")
        validated["model"] = model

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
        return validated

    def build_command(self, settings: Any) -> list[str]:
        """Build the exact argv shape consumed by ``minimax.py``."""

        values = self._validate_settings(settings)
        command = [
            self.python_executable,
            "-u",
            str(self.script_path),
            _number_argument(values["segment_length"]),
            _number_argument(values["total_length"]),
            _number_argument(values["megapixels"]),
            "--resume",
            str(values["resume"]),
            "--steps",
            str(values["steps"]),
            "--context-frames",
            str(values["context_frames"]),
            "--refresh",
            str(values["refresh"]),
            "--model",
            values["model"],
        ]
        if values["repair"] is not None:
            command.extend(("--repair", str(values["repair"])))
        if values["first_frame"]:
            command.append("--ff")
        for name, strength in values["loras"]:
            command.extend(("--lora", f"{name}:{_number_argument(strength)}"))
        return command

    def start_generation(self, settings: Any) -> dict[str, Any]:
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
                    "message": "Starting generation",
                    "running": True,
                    "return_code": None,
                    "current_segment": None,
                    "total_segments": None,
                    "ended_at": None,
                }
            )

        try:
            command = self.build_command(settings)
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
                "message": "Generation is running",
                "running": True,
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
                state, message = "succeeded", "Generation completed"
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
        "MiniMax H3",
        url=FRONTEND_INDEX.as_uri(),
        js_api=bridge,
        width=1180,
        height=820,
        min_size=(820, 620),
        background_color="#0b1017",
    )
    window.events.closed += bridge.shutdown
    try:
        webview.start(debug=os.environ.get("MINIMAX_DESKTOP_DEBUG") == "1")
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    main()
