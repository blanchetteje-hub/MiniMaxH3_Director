PREVIOUS_STATE_FIELDS = (
    "Location/environment",
    "Character positions",
    "Character appearance/physical condition",
    "Clothing",
    "Props/objects",
    "Camera/framing",
    "Ongoing physical action",
    "Ongoing audio",
)
import argparse
import base64
import copy
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, UnidentifiedImageError

from ministral_formatter import (
    MinistralFormatter,
    extract_inline_dialogue_subjects,
    normalize_summary_subject_references,
    validate_h3_dialogue_format,
)
from qwen_formatter import QwenFormatter


FORMATTER_CLASSES = {
    "ministral": MinistralFormatter,
    "qwen": QwenFormatter,
}
ACTIVE_FORMATTER = MinistralFormatter()


def get_formatter(model):
    """Return the requested response formatter."""

    try:
        formatter_class = FORMATTER_CLASSES[str(model).strip().lower()]
    except KeyError as error:
        supported = ", ".join(FORMATTER_CLASSES)
        raise ValueError(
            f"Unsupported formatter model {model!r}; choose one of: {supported}."
        ) from error
    return formatter_class()


def configure_formatter(model):
    """Select the formatter used by the existing generation pipeline."""

    global ACTIVE_FORMATTER, format_ministral_prompt, validate_ministral_prompt
    ACTIVE_FORMATTER = get_formatter(model)
    # Keep these established names as compatibility seams for callers/tests.
    format_ministral_prompt = ACTIVE_FORMATTER.format_prompt
    validate_ministral_prompt = ACTIVE_FORMATTER.validate_prompt
    return ACTIVE_FORMATTER


configure_formatter("ministral")


# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LM_STUDIO_URL = os.environ.get(
    "MINIMAX_LM_STUDIO_URL",
    "http://192.168.0.203:1234"
).rstrip("/")
VISION_LM_STUDIO_URL = os.environ.get(
    "MINIMAX_VISION_LM_STUDIO_URL",
    LM_STUDIO_URL,
).rstrip("/")
# Optional. When blank, LM Studio uses its currently selected/loaded model,
# matching the existing text-model request behavior.
VISION_MODEL = os.environ.get("MINIMAX_VISION_MODEL", "").strip()
COMFY_URL = os.environ.get(
    "MINIMAX_COMFY_URL",
    "http://127.0.0.1:8188"
).rstrip("/")

if os.name == "nt":
    DEFAULT_COMFY_OUTPUT = r"H:\images\output"
    DEFAULT_COMFY_INPUT = r"H:\images\input"
else:
    DEFAULT_COMFY_OUTPUT = os.path.expanduser("~/AI/ComfyUI/output")
    DEFAULT_COMFY_INPUT = os.path.expanduser("~/AI/ComfyUI/input")

COMFY_OUTPUT = os.path.abspath(
    os.path.expandvars(
        os.path.expanduser(
            os.environ.get("MINIMAX_COMFYUI_OUTPUT", DEFAULT_COMFY_OUTPUT)
        )
    )
)
COMFY_INPUT = os.path.abspath(
    os.path.expandvars(
        os.path.expanduser(
            os.environ.get("MINIMAX_COMFYUI_INPUT", DEFAULT_COMFY_INPUT)
        )
    )
)
COMFY_ROOT = os.path.abspath(
    os.path.expandvars(
        os.path.expanduser(
            os.environ.get(
                "MINIMAX_COMFYUI_ROOT",
                os.path.dirname(COMFY_OUTPUT),
            )
        )
    )
)
LORA_DIRECTORY = "/mnt/h/StableDiffusion/loras"

VIDEO_OUTPUT = os.path.abspath(
    os.path.expandvars(
        os.path.expanduser(
            os.environ.get(
                "MINIMAX_VIDEO_OUTPUT",
                os.path.join(COMFY_OUTPUT, "video")
            )
        )
    )
)

H3_LATENT_SAVE_NODE_NAME = "H3 AV Save Latent"
H3_LATENT_LOAD_NODE_NAME = "H3 AV Load Latent"
H3_LATENT_FILENAME_PREFIX = "h3_context/segment"
H3_REPAIR_LATENT_FILENAME_PREFIX = "h3_repair/segment"

INITIAL_WORKFLOW_FILE = os.path.join(SCRIPT_DIR, "Minimax_auto_API.json")
APPEND_WORKFLOW_FILE = os.path.join(SCRIPT_DIR, "Minimax_auto_append_API.json")
REFRESH_WORKFLOW_FILE = os.path.join(SCRIPT_DIR, "Minimax_auto_refresh_API.json")
STORY_FILE = os.path.join(SCRIPT_DIR, "story.txt")
STORY_ARC_FILE = os.path.join(SCRIPT_DIR, "story_arc.json")
STORY_ARC_HASH_FILE = STORY_ARC_FILE + ".sha256"
BEATS_FILE = os.path.join(SCRIPT_DIR, "beats.txt")
PHRASE_EXCLUSIONS_FILE = os.path.join(SCRIPT_DIR, "phrase_exclusions.txt")
SUBJECT_DEFINITIONS_FILE = os.path.join(SCRIPT_DIR, "subjects.txt")
GENERATION_STATE_FILE = os.path.join(SCRIPT_DIR, "generation_state.json")
PROMPT_HISTORY_FILE = os.path.join(SCRIPT_DIR, "prompt_history.txt")
FINAL_VIDEO = os.path.join(VIDEO_OUTPUT, "final.mp4")
VISION_FRAME_OUTPUT = os.path.join(VIDEO_OUTPUT, "vision_frames")
PROMPT_HISTORY_LOCK = threading.Lock()
_WINDOWS_CONSOLE_HANDLER = None
_WINDOWS_JOB_HANDLE = None


def cleanup_generated_frames(
    vision_frame_paths=None,
    refresh_frame_names=None,
    *,
    input_directory=None,
    vision_segment=None,
):
    """Remove temporary frames created by visual continuity and auto-refresh.

    Only paths created by this application are accepted here.  Missing files
    are harmless so cleanup can safely run after a failed render or request.
    """
    deleted = []
    paths = [os.fspath(path) for path in (vision_frame_paths or [])]
    input_directory = os.path.abspath(input_directory or COMFY_INPUT)
    paths.extend(
        os.path.join(input_directory, os.path.basename(os.fspath(name)))
        for name in (refresh_frame_names or [])
    )

    if vision_segment is not None:
        segment_directory = os.path.join(
            os.path.abspath(VISION_FRAME_OUTPUT),
            f"segment_{int(vision_segment):04d}",
        )
        if os.path.isdir(segment_directory):
            paths.extend(
                os.path.join(segment_directory, name)
                for name in os.listdir(segment_directory)
            )

    for path in dict.fromkeys(os.path.abspath(path) for path in paths):
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
                deleted.append(path)
        except OSError as error:
            print(f"WARNING: could not clean up generated frame {path}: {error}")

    if vision_segment is not None:
        segment_directory = os.path.join(
            os.path.abspath(VISION_FRAME_OUTPUT),
            f"segment_{int(vision_segment):04d}",
        )
        try:
            if os.path.isdir(segment_directory) and not os.listdir(segment_directory):
                os.rmdir(segment_directory)
        except OSError as error:
            print(
                f"WARNING: could not remove empty vision-frame directory "
                f"{segment_directory}: {error}"
            )
    return deleted


def _immediate_interrupt_handler(_signum, _frame):
    """Exit immediately instead of waiting for background worker threads.

    ThreadPoolExecutor context managers wait for running requests and renders
    during normal exception unwinding.  A hard exit is intentional here so a
    Ctrl+C emergency stop cannot be delayed by those long-running workers.
    Generation-state writes use temporary files plus ``os.replace``, so the
    last fully committed checkpoint remains resumable.
    """

    try:
        os.write(
            2,
            b"\nEmergency stop requested; exiting immediately.\n",
        )
    finally:
        os._exit(130)


def _install_windows_console_handler():
    """Use Win32 console events instead of relying only on Python signals."""

    global _WINDOWS_CONSOLE_HANDLER
    if os.name != "nt" or _WINDOWS_CONSOLE_HANDLER is not None:
        return _WINDOWS_CONSOLE_HANDLER is not None

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    @handler_type
    def console_handler(control_type):
        # CTRL_C_EVENT = 0 and CTRL_BREAK_EVENT = 1.  Windows invokes this
        # callback on a system-created thread, so it still runs when Python's
        # main thread is blocked in requests, Future.result(), or subprocess.
        if control_type in (0, 1):
            _immediate_interrupt_handler(None, None)
            return True
        return False

    kernel32.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
    # CREATE_NEW_PROCESS_GROUP and some launchers inherit an ignore-Ctrl+C
    # setting.  Explicitly clear it before registering our handler.
    kernel32.SetConsoleCtrlHandler(None, False)
    if not kernel32.SetConsoleCtrlHandler(console_handler, True):
        return False
    # ctypes callbacks must remain strongly referenced for their full lifetime.
    _WINDOWS_CONSOLE_HANDLER = console_handler
    return True


def _install_windows_kill_on_exit_job():
    """Put this process and child ffmpeg processes in a kill-on-close job."""

    global _WINDOWS_JOB_HANDLE
    if os.name != "nt" or _WINDOWS_JOB_HANDLE is not None:
        return _WINDOWS_JOB_HANDLE is not None

    import ctypes
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        return False
    limits = ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
    configured = kernel32.SetInformationJobObject(
        job_handle,
        9,  # JobObjectExtendedLimitInformation
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    )
    assigned = configured and kernel32.AssignProcessToJobObject(
        job_handle,
        kernel32.GetCurrentProcess(),
    )
    if not assigned:
        kernel32.CloseHandle(job_handle)
        return False
    _WINDOWS_JOB_HANDLE = job_handle
    return True


def install_immediate_interrupt_handlers():
    """Make Ctrl+C (and Ctrl+Break on Windows) hard-stop this process."""

    signal.signal(signal.SIGINT, _immediate_interrupt_handler)
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _immediate_interrupt_handler)
        _install_windows_console_handler()
        _install_windows_kill_on_exit_job()


def start_emergency_stop_listener():
    """On Windows, make Ctrl+Q stop even while the main thread is blocked."""

    if os.name != "nt":
        return None

    import msvcrt

    def watch_keyboard():
        while True:
            try:
                key = msvcrt.getwch()
            except (EOFError, OSError):
                return
            if key == "\x11":  # Ctrl+Q
                _immediate_interrupt_handler(None, None)

    listener = threading.Thread(
        target=watch_keyboard,
        name="emergency-stop-listener",
        daemon=True,
    )
    listener.start()
    return listener


FRAME_RATE = 24
TRIM_FRAMES_AFTER_FIRST = 2
TRIM_SECONDS_AFTER_FIRST = TRIM_FRAMES_AFTER_FIRST / FRAME_RATE
DEFAULT_CONTEXT_FRAMES = 7
MAX_COMFY_SEED = (2 ** 63) - 1
MAX_LLM_SEED = (2 ** 31) - 1

COMFY_QUEUE_RETRIES = 10
COMFY_QUEUE_RETRY_DELAY = 10
COMFY_HISTORY_MAX_ERRORS = 30
COMFY_HISTORY_RETRY_DELAY = 10
COMFY_RENDER_TIMEOUT = 15 * 60
COMFY_RENDER_RETRIES = 10
COMFY_RETRY_MEGAPIXEL_STEP = 0.02
RESUME_CHECKPOINT_WAIT_SECONDS = 30
RESUME_CHECKPOINT_POLL_SECONDS = 0.25
CONTINUITY_STATE_VERSION = 5
VISION_END_FRAME_OFFSETS = (8, 4, 0)
VISION_REQUEST_RETRIES = 3
VISION_REQUEST_MAX_TOKENS = 2500

PERSISTENT_SUBJECT_LIST_FIELDS = (
    "attached_objects",
    "injuries",
    "substances",
    "persistent_effects",
)

CURRENT_SUBJECT_SCALAR_FIELDS = (
    "position",
    "pose_action",
    "physical_condition",
)

PERSISTENT_SUBJECT_SCALAR_FIELDS = (
    "topology",
    "body_state",
)

CURRENT_SUBJECT_LIST_FIELDS = (
    "spatial_relationships",
)

SUBJECT_LIST_FIELDS = (
    *PERSISTENT_SUBJECT_LIST_FIELDS,
    *CURRENT_SUBJECT_LIST_FIELDS,
    "held_props",
)

LLM_INPUT_TOKEN_BUDGET = 14000
CHARS_PER_TOKEN_ESTIMATE = 3.5
STORY_CONTEXT_MAX_CHARS = 12000
DEFAULT_BEAT_LOOKAHEAD = 1
RECENT_SEGMENTS_MAX = 1
DIALOGUE_HISTORY_SEGMENTS_MAX = 5
SUMMARY_CONTENT_ATTEMPTS = 3
BEAT_PHASE_GENERATION_ATTEMPTS = 10
BEAT_PHASE_REPAIR_ROUNDS = 10
# Whole-plan audit repairs must stay local. Broad audit complaints are too
# ambiguous to justify rewriting a large portion of an otherwise usable plan.
MAX_TARGETED_BEAT_REPAIR_SPAN = 4
# The post-generation semantic phase check adds two large LLM requests
# (beat_phase_validation and, on failure, beat_phase_repair) without improving
# the locally valid beat list reliably. Keep the implementation available for
# now, but do not invoke either request during normal beat generation.
ENABLE_BEAT_PHASE_LLM_VALIDATION = False
BEAT_LLM_SAMPLING_PARAMETERS = {
    "temperature": 0.65,
    "top_p": 0.90,
    "presence_penalty": 0.15,
    "frequency_penalty": 0.15,
    "repeat_penalty": 1.05,
}
BEAT_AUDIT_LLM_SAMPLING_PARAMETERS = {
    "temperature": 0.15,
    "top_p": 0.90,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "repeat_penalty": 1.05,
}

# Continuity safety rails. These are deliberately conservative: when the
# text-only continuity updater is uncertain, preserving the last committed
# state is safer than inventing a new irreversible body configuration.
CONTINUITY_REJECT_UNEVIDENCED_STRUCTURAL_CHANGES = os.environ.get(
    "MINIMAX_CONTINUITY_STRICT", "1"
).strip().lower() not in {"0", "false", "no", "off"}

# These titles are intentionally used instead of numeric ComfyUI node IDs.
DURATION_NODE_NAME = "Float (duration)"
PROMPT_NODE_NAME = "Prompt"
NOISE_NODE_NAME = "RandomNoise"
SAVE_VIDEO_NODE_NAME = "Save Video"
LORA_NODE_NAME = "Load LoRA"
RESOLUTION_NODE_NAME = "Resolution Selector"
SCHEDULER_NODE_NAME = "BasicScheduler"
IMAGE_BATCH_NODE_NAME = "Image Batch Multi"
MATH_NODE_NAME = "Math Expression"
VIDEO_EXTEND_NODE_NAME = "MiniMax H3 Video Extend (Backported)"
ENCODE_AV_NODE_NAME = "MiniMax H3 Encode AV (Backported)"
LOAD_VIDEO_NODE_NAME = "Load Video (Path) 🎥🅥🅗🅢"
REFRESH_FIRST_FRAME_NODE_NAME = "Refresh First Frame"
REPAIR_LAST_FRAME_NODE_NAME = "Repair Last Frame"
REFRESH_CONDITIONING_NODE_NAME = "MiniMax H3 Hybrid Cond (R2V + I2V)"
INITIAL_REFERENCE_CONDITIONING_NODE_NAME = "MiniMax H3 Reference to Video"
REFERENCE_IMAGE_NODE_NAMES = tuple(
    f"Reference Image {image_number}"
    for image_number in range(1, 7)
)
REFERENCE_IMAGE_OVERRIDES = {}


def generate_random_seed():
    return secrets.randbelow(MAX_COMFY_SEED) + 1


def generate_random_llm_seed():
    return secrets.randbelow(MAX_LLM_SEED) + 1


# ============================================================
# COMMAND LINE
# ============================================================

def normalize_command_line(arguments):
    normalized = []
    for argument in arguments:
        normalized.extend(
            piece.strip()
            for piece in argument.split(",")
            if piece.strip()
        )
    return normalized


def parse_args(arguments=None):
    parser = argparse.ArgumentParser(
        description="Generate a complete video story using LM Studio + ComfyUI."
    )
    parser.add_argument("segment_length", type=float, nargs="?")
    parser.add_argument("total_length", type=float, nargs="?")
    parser.add_argument("megapixels", type=float, nargs="?")
    parser.add_argument(
        "--resume",
        type=int,
        default=1,
        metavar="SEGMENT",
        help="continue at this one-based segment number (default: 1)"
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=6,
        metavar="STEPS",
        help="set the BasicScheduler step count (default: 6)"
    )
    parser.add_argument(
        "--context-frames",
        type=int,
        default=DEFAULT_CONTEXT_FRAMES,
        metavar="FRAMES",
        help=(
            "set latent context frames for video extension "
            f"(default: {DEFAULT_CONTEXT_FRAMES})"
        ),
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=6,
        metavar="SEGMENTS",
        help=(
            "regenerate from the preceding segment's last frame on every "
            "SEGMENTS-th segment (default: 6)"
        ),
    )
    parser.add_argument(
        "--vision-continuity",
        type=int,
        default=0,
        metavar="N",
        help=(
            "run rendered-frame vision continuity on a cadence: 0 disables it "
            "entirely (default), 1 checks every segment, and values > 1 "
            "check every Nth segment with a forced check before every clean "
            "refresh"
        ),
    )
    parser.add_argument(
        "--repair",
        type=int,
        default=None,
        metavar="SEGMENT",
        help="rerender only this existing one-based middle segment",
    )
    parser.add_argument(
        "--generate-beats",
        type=int,
        default=None,
        metavar="COUNT",
        help=(
            "write COUNT story beats and story_arc.json from story.txt, then "
            "exit without running H3 or ComfyUI"
        ),
    )
    parser.add_argument(
        "--model",
        choices=tuple(FORMATTER_CLASSES),
        default="ministral",
        help="select the response formatter (default: ministral)",
    )
    for image_number in range(1, 7):
        parser.add_argument(
            f"--image{image_number}",
            default=None,
            metavar="PATH",
            help=(
                f"override Reference Image {image_number} in the initial, "
                "append, and refresh workflows"
            ),
        )
    parser.add_argument(
        "--lora",
        action="append",
        default=[],
        type=parse_lora_spec,
        metavar="LORA_NAME:STRENGTH",
        help=(
            "apply this LoRA to every beat; repeat --lora to apply multiple "
            "LoRAs in order"
        ),
    )
    parser.add_argument(
        "--lora_dir",
        default=LORA_DIRECTORY,
        metavar="DIRECTORY",
        help=(
            "directory containing LoRA files (default: LORA_DIRECTORY or "
            "/mnt/h/StableDiffusion/loras)"
        ),
    )
    parser.add_argument(
        "ff",
        nargs="?",
        choices=("ff",),
        default=False,
        help="add first-frame instructions to segment 1"
    )
    parser.add_argument(
        "--ff",
        dest="first_frame",
        action="store_true",
        help="add first-frame instructions to segment 1"
    )

    if arguments is None:
        arguments = sys.argv[1:]

    args = parser.parse_args(normalize_command_line(arguments))
    args.ff = args.ff == "ff" or args.first_frame

    if args.generate_beats is not None:
        if args.generate_beats <= 0:
            parser.error("--generate-beats must be greater than zero.")
        if args.repair is not None:
            parser.error("--generate-beats cannot be combined with --repair.")
        if any(
            value is not None
            for value in (args.segment_length, args.total_length, args.megapixels)
        ):
            parser.error(
                "--generate-beats accepts only its COUNT argument, not video "
                "generation positionals."
            )
        return args

    if any(
        value is None
        for value in (args.segment_length, args.total_length, args.megapixels)
    ):
        parser.error(
            "segment_length, total_length, and megapixels are required unless "
            "--generate-beats COUNT is used."
        )
    if args.segment_length <= 0:
        parser.error("segment_length must be greater than 0.")
    if args.total_length <= 0:
        parser.error("total_length must be greater than 0.")
    if args.megapixels <= 0:
        parser.error("megapixels must be greater than 0.")
    if args.resume <= 0:
        parser.error("--resume must be a one-based segment number.")
    if args.steps <= 0:
        parser.error("--steps must be greater than zero.")
    if args.context_frames <= 0:
        parser.error("--context-frames must be greater than zero.")
    if args.refresh is not None and args.refresh <= 0:
        parser.error("--refresh must be greater than zero.")
    if args.vision_continuity < 0:
        parser.error("--vision-continuity must be zero or a positive integer.")
    if args.repair is not None and args.repair <= 0:
        parser.error("--repair must be a positive one-based segment number.")
    if args.repair == 1:
        parser.error("--repair requires a middle segment; Segment 1 is not repairable.")
    if args.repair is not None and args.resume != 1:
        parser.error("--repair cannot be combined with --resume other than 1.")

    return args


def get_segments_to_generate(resume_segment, total_segments):
    if resume_segment > total_segments:
        raise ValueError(
            f"--resume {resume_segment} exceeds the {total_segments} "
            "segments in this run."
        )
    return range(resume_segment, total_segments + 1)


def is_refresh_segment(segment_number, refresh_interval):
    """Return whether this non-opening segment uses the refresh workflow."""

    return bool(
        refresh_interval
        and segment_number > 1
        and segment_number % refresh_interval == 0
    )


def should_run_vision_continuity(segment_number, cadence, refresh_interval=None):
    """Return whether the rendered-frame visual continuity gate should run."""

    segment_number = int(segment_number)
    if segment_number < 1:
        return False
    cadence = int(cadence) if cadence is not None else 1
    if cadence == 0:
        return False
    if cadence == 1:
        return True
    if refresh_interval:
        next_segment_is_refresh = is_refresh_segment(
            segment_number + 1,
            refresh_interval,
        )
        if next_segment_is_refresh:
            return True
    return segment_number % cadence == 0


CONDITIONING_MODES = frozenset({
    "initial",
    "latent_continuation",
    "clean_refresh",
})


def conditioning_mode_for_segment(segment_number, refresh_interval=None):
    """Return the H3 visual-conditioning mode selected by workflow scheduling."""

    segment_number = int(segment_number)
    if segment_number < 1:
        raise ValueError("Segment numbers must be one-based.")
    if segment_number == 1:
        return "initial"
    if is_refresh_segment(segment_number, refresh_interval):
        return "clean_refresh"
    return "latent_continuation"


def validate_conditioning_mode(conditioning_mode, segment_number):
    """Validate an explicitly supplied Director conditioning mode."""

    segment_number = int(segment_number)
    if conditioning_mode is None:
        conditioning_mode = conditioning_mode_for_segment(segment_number)
    conditioning_mode = str(conditioning_mode).strip()
    if conditioning_mode not in CONDITIONING_MODES:
        choices = ", ".join(sorted(CONDITIONING_MODES))
        raise ValueError(
            f"Unknown conditioning mode {conditioning_mode!r}; expected: {choices}."
        )
    if segment_number == 1 and conditioning_mode != "initial":
        raise ValueError("Segment 1 must use conditioning mode 'initial'.")
    if segment_number > 1 and conditioning_mode == "initial":
        raise ValueError("Only segment 1 may use conditioning mode 'initial'.")
    return conditioning_mode


# ============================================================
# STRUCTURED LLM OUTPUT
# ============================================================

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "video_segment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "detailed_description": {"type": "string"},
                "overall_soundscape": {"type": "string"},
                "non_diegetic_music": {"type": "string"},
                "completed_beat_ids": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1}
                }
            },
            "required": [
                "detailed_description",
                "overall_soundscape",
                "non_diegetic_music",
                "completed_beat_ids"
            ],
            "additionalProperties": False
        }
    }
}

# The combined continuity call intentionally uses a flexible/arbitrary JSON
# shape, so a fixed JSON schema is inappropriate. JSON-object mode still
# constrains LM Studio to syntactically valid JSON without dictating
# continuity fields.
JSON_OBJECT_RESPONSE_FORMAT = {"type": "json_object"}


# ============================================================
# FILE / WORKFLOW HELPERS
# ============================================================


def validate_runtime_environment():
    missing = [
        tool for tool in ("ffmpeg", "ffprobe")
        if shutil.which(tool) is None
    ]
    if missing:
        raise RuntimeError(
            "Required command-line tool(s) not found on PATH: "
            + ", ".join(missing)
        )
    if not os.path.isdir(COMFY_OUTPUT):
        raise FileNotFoundError(
            f"ComfyUI output folder not found: {COMFY_OUTPUT}"
        )


def load_text_file(path, required=True):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        if required:
            raise FileNotFoundError(f"Required file not found: {path}") from None
        return ""


def load_phrase_exclusions(path=PHRASE_EXCLUSIONS_FILE):
    """Load distinct, nonblank newline-delimited beat exclusions."""
    raw = load_text_file(path, required=False)
    exclusions = []
    seen = set()
    for raw_line in raw.splitlines():
        exclusion = " ".join(raw_line.split()).strip()
        key = exclusion.casefold()
        if exclusion and key not in seen:
            exclusions.append(exclusion)
            seen.add(key)
    return exclusions


def load_workflow(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Workflow file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Workflow is invalid JSON: {path} "
            f"(line {e.lineno}, column {e.colno})"
        ) from e

    if not isinstance(workflow, dict):
        raise RuntimeError(f"Workflow must contain a JSON object: {path}")

    apply_reference_image_overrides(workflow, f"workflow '{path}'")
    return workflow


def configure_reference_image_overrides(arguments):
    """Set the six optional command-line image overrides for this process."""

    global REFERENCE_IMAGE_OVERRIDES
    overrides = {}
    for image_number in range(1, 7):
        value = getattr(arguments, f"image{image_number}", None)
        if value is None:
            continue
        value = str(value).strip()
        if not value:
            raise ValueError(f"--image{image_number} must not be empty.")
        overrides[image_number] = value
    REFERENCE_IMAGE_OVERRIDES = overrides
    return dict(overrides)


def apply_reference_image_overrides(workflow, workflow_label):
    """Apply configured CLI image paths to named LoadImage nodes."""

    for image_number, image_path in REFERENCE_IMAGE_OVERRIDES.items():
        node_name = f"Reference Image {image_number}"
        _, image_node = find_workflow_node(
            workflow,
            node_name,
            workflow_label,
            "LoadImage",
        )
        image_node.setdefault("inputs", {})["image"] = image_path
    return workflow


def copy_reference_image_inputs(source_workflow, destination_workflow, label):
    """Copy all six named reference-image filenames between workflows."""

    for node_name in REFERENCE_IMAGE_NODE_NAMES:
        _, source = find_workflow_node(
            source_workflow,
            node_name,
            "reference source workflow",
            "LoadImage",
        )
        image_name = source["inputs"].get("image")
        if not isinstance(image_name, str) or not image_name.strip():
            raise RuntimeError(
                f"Node '{node_name}' in the reference source workflow has no image."
            )
        set_node_input(
            destination_workflow,
            node_name,
            "image",
            image_name.strip(),
            label,
            "LoadImage",
        )


def _resolve_comfy_input_image(image_name, input_directory):
    """Resolve a LoadImage value while tolerating ComfyUI's folder suffix."""

    cleaned = re.sub(
        r"\s+\[(?:input|output|temp)\]\s*$",
        "",
        str(image_name or ""),
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return ""
    cleaned = os.path.expandvars(os.path.expanduser(cleaned))
    if os.path.isabs(cleaned):
        return os.path.abspath(cleaned)
    return os.path.abspath(os.path.join(input_directory, cleaned))


def _validate_comfy_input_image(image_name, input_directory):
    """Return a resolved path and a decode error for a ComfyUI image input."""

    image_path = _resolve_comfy_input_image(image_name, input_directory)
    if not image_path or not os.path.isfile(image_path):
        return image_path, "file was not found"
    try:
        with Image.open(image_path) as image:
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as error:
        return image_path, f"image decoder rejected the file: {error}"
    return image_path, None


def _reference_destination(workflow, workflow_label, workflow_kind):
    """Return the reference target node and its six exact input names."""

    if workflow_kind == "append":
        destination_name = IMAGE_BATCH_NODE_NAME
        destination_class = "ImageBatchMulti"
        input_names = [f"image_{number}" for number in range(1, 7)]
    elif workflow_kind == "initial":
        destination_name = INITIAL_REFERENCE_CONDITIONING_NODE_NAME
        destination_class = "MiniMaxH3ReferenceToVideo"
        input_names = [f"ref_images.ref_image_{number}" for number in range(6)]
    elif workflow_kind == "refresh":
        destination_name = REFRESH_CONDITIONING_NODE_NAME
        destination_class = "MiniMaxH3HybridRefAndKeyframe"
        input_names = [f"ref_images.ref_image_{number}" for number in range(6)]
    else:
        raise ValueError(f"Unknown workflow kind: {workflow_kind!r}")

    _, destination = find_workflow_node(
        workflow,
        destination_name,
        workflow_label,
        destination_class,
    )
    return destination_name, destination, input_names


def _reference_input_container(destination, input_name):
    """Return the actual input mapping and key for flat or nested API JSON."""

    inputs = destination["inputs"]
    if input_name in inputs or "." not in input_name:
        return inputs, input_name
    container_name, leaf_name = input_name.split(".", 1)
    nested = inputs.get(container_name)
    if isinstance(nested, dict):
        return nested, leaf_name
    return inputs, input_name


def _synchronize_append_reference_batch(workflow, workflow_label, destination):
    """Connect only an ordered, gap-free image batch to the append model."""

    connected_slots = [
        number
        for number in range(1, 7)
        if isinstance(destination["inputs"].get(f"image_{number}"), list)
        and len(destination["inputs"][f"image_{number}"]) == 2
    ]
    contiguous_slots = list(range(1, len(connected_slots) + 1))
    if not connected_slots or connected_slots != contiguous_slots:
        disconnect_append_reference_batch(
            workflow,
            workflow_label,
            reason=(
                "a missing reference would renumber later Picture slots "
                f"({connected_slots or 'no valid images'})"
            ),
        )
        return False

    batch_id, _ = find_workflow_node(
        workflow,
        IMAGE_BATCH_NODE_NAME,
        workflow_label,
        "ImageBatchMulti",
    )
    _, extend_node = find_workflow_node(
        workflow,
        VIDEO_EXTEND_NODE_NAME,
        workflow_label,
        "MiniMaxH3VideoExtendPatched",
    )
    expected_connection = [batch_id, 0]
    if extend_node["inputs"].get("ref_images") != expected_connection:
        extend_node["inputs"]["ref_images"] = expected_connection
        print(
            f"{workflow_label} connected the valid ordered reference-image "
            "batch to the video extender."
        )
    return True


def _pack_append_reference_images(
    workflow,
    workflow_label,
    destination,
    input_directory,
    excluded_picture_ids=None,
):
    """Pack compatible canonical Pictures into dense append-only H3 slots."""

    excluded = {
        int(value)
        for value in (excluded_picture_ids or ())
        if (isinstance(value, int) or str(value).isdigit())
        and 1 <= int(value) <= 6
    }
    compatible = []
    removed = []
    for picture_id, node_name in enumerate(REFERENCE_IMAGE_NODE_NAMES, start=1):
        node_id, image_node = find_workflow_node(
            workflow,
            node_name,
            workflow_label,
            "LoadImage",
        )
        image_name = image_node["inputs"].get("image")
        image_path, decode_error = _validate_comfy_input_image(
            image_name,
            input_directory,
        )
        if picture_id in excluded:
            removed.append(picture_id)
            #print(
            #    f"{workflow_label} excluded canonical Picture {picture_id} "
            #    "from append H3 reference conditioning."
            #)
        elif decode_error is not None:
            removed.append(picture_id)
            #print(
            #    f"WARNING: {workflow_label} excluded canonical Picture "
            #    f"{picture_id} from append H3 reference conditioning because "
            #    f"{decode_error}: {image_path or image_name!r}"
            #)
        else:
            compatible.append((picture_id, node_id))

    inputs = destination["inputs"]
    for slot_number in range(1, 7):
        inputs.pop(f"image_{slot_number}", None)
    for packed_slot, (picture_id, node_id) in enumerate(compatible, start=1):
        inputs[f"image_{packed_slot}"] = [node_id, 0]
        if packed_slot != picture_id:
            print(
                f"{workflow_label} packed canonical Picture {picture_id} into "
                f"append H3 <Picture {packed_slot}>."
            )

    _synchronize_append_reference_batch(workflow, workflow_label, destination)
    picture_slot_map = {
        picture_id: packed_slot
        for packed_slot, (picture_id, _node_id) in enumerate(
            compatible,
            start=1,
        )
    }
    return removed, picture_slot_map


def prune_missing_reference_images(
    workflow,
    workflow_label,
    workflow_kind,
    input_directory=None,
    excluded_picture_ids=None,
    return_picture_slot_map=False,
):
    """Connect decodable references and disconnect unusable ones before queueing."""

    input_directory = os.path.abspath(input_directory or COMFY_INPUT)
    destination_name, destination, input_names = _reference_destination(
        workflow,
        workflow_label,
        workflow_kind,
    )
    if workflow_kind == "append":
        removed, picture_slot_map = _pack_append_reference_images(
            workflow,
            workflow_label,
            destination,
            input_directory,
            excluded_picture_ids=excluded_picture_ids,
        )
        if return_picture_slot_map:
            return removed, picture_slot_map
        return removed

    removed = []
    for image_number, (node_name, input_name) in enumerate(
        zip(REFERENCE_IMAGE_NODE_NAMES, input_names),
        start=1,
    ):
        node_id, image_node = find_workflow_node(
            workflow,
            node_name,
            workflow_label,
            "LoadImage",
        )
        image_name = image_node["inputs"].get("image")
        image_path, decode_error = _validate_comfy_input_image(
            image_name,
            input_directory,
        )
        container, leaf_name = _reference_input_container(destination, input_name)
        if decode_error is None:
            expected_connection = [node_id, 0]
            if container.get(leaf_name) != expected_connection:
                container[leaf_name] = expected_connection
                print(
                    f"{workflow_label} connected Reference Image {image_number} "
                    f"to '{destination_name}.{input_name}'."
                )
            continue

        connection = container.get(leaf_name)
        if connection is not None:
            del container[leaf_name]
        removed.append(image_number)
        #print(
        #    f"WARNING: {workflow_label} disconnected Reference Image "
        #    f"{image_number} from '{destination_name}.{input_name}' because "
        #    f"{decode_error}: {image_path or image_name!r}"
        #)
    return removed


def disconnect_reference_images(
    workflow,
    workflow_label,
    workflow_kind,
    image_numbers,
    reason="reference incompatibility",
):
    """Disconnect selected Picture slots from one workflow's conditioning."""

    if workflow_kind == "append":
        destination_name = IMAGE_BATCH_NODE_NAME
        input_names = [f"image_{number}" for number in range(1, 7)]
    elif workflow_kind == "initial":
        destination_name = INITIAL_REFERENCE_CONDITIONING_NODE_NAME
        input_names = [f"ref_images.ref_image_{number}" for number in range(6)]
    elif workflow_kind == "refresh":
        destination_name = REFRESH_CONDITIONING_NODE_NAME
        input_names = [f"ref_images.ref_image_{number}" for number in range(6)]
    else:
        raise ValueError(f"Unknown workflow kind: {workflow_kind!r}")

    selected = {
        int(image_number)
        for image_number in image_numbers or ()
        if str(image_number).isdigit() and 1 <= int(image_number) <= 6
    }
    if not selected:
        return []

    _, destination = find_workflow_node(
        workflow,
        destination_name,
        workflow_label,
    )
    removed = []
    for image_number, input_name in enumerate(input_names, start=1):
        if image_number not in selected:
            continue
        inputs = destination["inputs"]
        container = inputs
        leaf_name = input_name
        if input_name not in inputs and "." in input_name:
            container_name, leaf_name = input_name.split(".", 1)
            nested = inputs.get(container_name)
            if not isinstance(nested, dict):
                continue
            container = nested
        if leaf_name not in container:
            continue
        del container[leaf_name]
        removed.append(image_number)
        print(
            f"{workflow_label} disconnected Reference Image {image_number} "
            f"because of {reason}."
        )
    return removed


def disconnect_append_reference_batch(
    workflow,
    workflow_label,
    reason="reference incompatibility",
):
    """Disconnect the optional append ref_images batch as one atomic input.

    ImageBatchMulti requires image_1. Compatible Pictures are packed densely
    before this point, so this is used only when no usable Picture remains or a
    malformed batch cannot safely be sent to MiniMaxH3VideoExtendPatched.
    """
    _, extend_node = find_workflow_node(
        workflow,
        VIDEO_EXTEND_NODE_NAME,
        workflow_label,
    )
    if "ref_images" not in extend_node["inputs"]:
        return False
    del extend_node["inputs"]["ref_images"]
    print(
        f"{workflow_label} disconnected the optional reference-image batch "
        f"because of {reason}. AV latent continuity remains active."
    )
    return True


def verify_reference_images(
    initial_workflow,
    append_workflow,
    input_directory=None,
    refresh_workflow=None,
):
    """Verify existing images on connected workflow image inputs."""
    input_directory = os.path.abspath(input_directory or COMFY_INPUT)

    def active_references(workflow, workflow_label, destination_title, fields):
        _, destination = find_workflow_node(
            workflow,
            destination_title,
            workflow_label,
        )
        image_references = {}
        for image_number, connection in fields:
            source_connection = destination["inputs"].get(connection)
            if source_connection is None and "." in connection:
                container_name, input_name = connection.split(".", 1)
                container = destination["inputs"].get(container_name)
                source_connection = (
                    container.get(input_name)
                    if isinstance(container, dict) else None
                )
            if source_connection is None:
                continue
            if (
                not isinstance(source_connection, list)
                or len(source_connection) != 2
            ):
                print(
                    f"WARNING: {workflow_label} '{destination_title}' input "
                    f"'{connection}' is not connected to an image."
                )
                continue
            source_id, output_index = source_connection
            source = workflow.get(str(source_id), workflow.get(source_id))
            if (
                not isinstance(source, dict)
                or source.get("class_type") != "LoadImage"
                or output_index != 0
            ):
                print(
                    f"WARNING: {workflow_label} '{destination_title}' input "
                    f"'{connection}' does not receive a LoadImage output."
                )
                continue
            image_name = source.get("inputs", {}).get("image")
            if not isinstance(image_name, str) or not image_name.strip():
                print(
                    f"WARNING: {workflow_label} image source for '{connection}' "
                    "has no image filename."
                )
                continue
            image_references[image_number] = image_name.strip()
        return image_references

    initial_references = active_references(
        initial_workflow,
        "initial workflow",
        INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
        [
            (image_number, f"ref_images.ref_image_{image_number - 1}")
            for image_number in range(1, 7)
        ],
    )
    append_references = active_references(
        append_workflow,
        "append workflow",
        IMAGE_BATCH_NODE_NAME,
        [
            (image_number, f"image_{image_number}")
            for image_number in range(1, 7)
        ],
    )
    refresh_references = {}
    if refresh_workflow is not None:
        refresh_references = active_references(
            refresh_workflow,
            "refresh workflow",
            REFRESH_CONDITIONING_NODE_NAME,
            [
                (image_number, f"ref_images.ref_image_{image_number - 1}")
                for image_number in range(1, 7)
            ],
        )

    for image_number, initial_name in initial_references.items():
        append_name = append_references.get(image_number)
        if append_name is None:
            print(
                f"WARNING: Image {initial_name} is connected in the initial "
                f"workflow but not in the append workflow."
            )
        elif initial_name != append_name:
            print(
                f"WARNING: Reference Image {image_number} differs between "
                f"workflows: {initial_name!r} vs {append_name!r}."
            )
        refresh_name = refresh_references.get(image_number)
        if refresh_workflow is not None and refresh_name is None:
            print(
                f"WARNING: Image {initial_name} is connected in the initial "
                "workflow but not in the refresh workflow."
            )
        elif refresh_name is not None and initial_name != refresh_name:
            print(
                f"WARNING: Reference Image {image_number} differs between "
                f"initial and refresh workflows: {initial_name!r} vs "
                f"{refresh_name!r}."
            )

    for image_number in range(1, 7):
        image_name = (
            initial_references.get(image_number)
            or append_references.get(image_number)
            or refresh_references.get(image_number)
        )
        if image_name is None:
            continue
        image_path, decode_error = _validate_comfy_input_image(
            image_name,
            input_directory,
        )
        if decode_error is not None:
            print(
                f"WARNING: Image {image_name} for reference slot "
                f"{image_number} is invalid ({decode_error}) and will be "
                f"disconnected before queueing: {image_path}"
            )
            continue
        print(f"Image {image_name} decoded and verified.")


def verify_global_loras(global_loras, lora_directory=None):
    """Verify that command-line LoRAs exist in ComfyUI's LoRA directory."""

    lora_directory = os.path.abspath(lora_directory or LORA_DIRECTORY)
    for lora_name, strength in normalize_lora_list(global_loras):
        relative_name = re.sub(r"[\\/]+", lambda _match: os.sep, lora_name)
        lora_path = os.path.abspath(os.path.join(lora_directory, relative_name))
        try:
            is_within_lora_directory = (
                os.path.commonpath((lora_directory, lora_path))
                == lora_directory
            )
        except ValueError:
            is_within_lora_directory = False
        if not is_within_lora_directory:
            raise ValueError(
                f"Global LoRA must be relative to {lora_directory}: {lora_name!r}."
            )
        if not os.path.isfile(lora_path):
            raise FileNotFoundError(
                f"Global LoRA not found: {lora_name!r} (expected {lora_path})"
            )
        print(f"Global LoRA {lora_name}:{strength:g} verified.")


def build_run_config(
    segment_length,
    total_length,
    megapixels,
    total_segments,
    story="",
    beats=None,
    subject_definitions="",
    global_loras=None,
    refresh_interval=None,
    gen_rules="",
    vision_continuity=1,
):
    # Auto-discovered video subjects are durable continuity metadata, not a
    # user edit to the creative source. Excluding those appended lines keeps a
    # resumable run's source fingerprint stable as its registry grows.
    source_subject_definitions = "\n".join(
        line
        for line in str(subject_definitions or "").splitlines()
        if not re.search(
            r"(?i)\b(?:created|established)\s+in\s+generated\s+video\s+"
            r"segment\s+\d+",
            line,
        )
    )
    source_payload = json.dumps(
        {
            "story": story,
            "beats": serialize_beats(beats),
            "global_loras": [list(lora) for lora in (global_loras or ())],
            "refresh_interval": refresh_interval,
            "vision_continuity": int(vision_continuity),
            "gen_rules": str(gen_rules or ""),
            "subject_definitions": source_subject_definitions,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return {
        "segment_length": float(segment_length),
        "total_length": float(total_length),
        "megapixels": float(megapixels),
        "total_segments": int(total_segments),
        "refresh_interval": refresh_interval,
        "vision_continuity": int(vision_continuity),
        "source_sha256": hashlib.sha256(source_payload).hexdigest(),
    }


def new_continuity_state():
    return {
        "version": CONTINUITY_STATE_VERSION,
        "environment": {
            "location": "N/A",
            "persistent_state": "N/A",
        },
        "camera": "N/A",
        "ongoing_action": "N/A",
        "ongoing_audio": "N/A",
        "subjects": {},
    }


def get_h3_latent_path(segment_number):
    return os.path.abspath(
        os.path.join(
            COMFY_OUTPUT,
            f"{H3_LATENT_FILENAME_PREFIX}_{segment_number:05d}.safetensors",
        )
    )

def normalize_subject_gender(value):
    """Return the supported binary Subject gender, defaulting unknown to N/A."""
    rendered = str(value or "").strip().casefold()
    if rendered in {"male", "man", "boy", "he", "him"}:
        return "male"
    elif rendered in {"female", "woman", "girl", "she", "her"}:
        return "female"
    # Historically some upstream callers used 'unknown' to signal an
    # unspecified animate subject; for compatibility default to 'female'.
    if rendered in {"unknown", "unspecified", ""}:
        return "female"
    return "N/A"


def infer_subject_gender(definition, subject_name=None):
    """Read a Subject gender from definition prose, defaulting unknown to N/A."""
    text = str(definition or "")
    if subject_name:
        windows = []
        for match in re.finditer(re.escape(str(subject_name)), text, re.I):
            windows.append(text[max(0, match.start() - 100):match.end() + 100])
        text = " ".join(windows)
    if re.search(r"(?i)\b(?:male|man|boy|he|him)\b", text):
        return "male"
    elif re.search(r"(?i)\b(?:female|woman|girl|she|her)\b", text):
        return "female"
    return "N/A"


def available_subject_speaker_id(subject_id, records, requested=None):
    """Choose a valid speaker ID unused by the supplied Subject records."""
    used = {
        str(record.get("speaker_id") or "").strip().casefold()
        for record in records
        if isinstance(record, dict) and record.get("speaker_id")
    }
    requested = str(requested or "").strip().upper()
    if re.fullmatch(r"S\d+", requested) and requested.casefold() not in used:
        return requested
    preferred = f"S{subject_id}"
    if preferred.casefold() not in used:
        return preferred
    number = max(
        [
            int(match.group(1))
            for value in used
            if (match := re.fullmatch(r"s(\d+)", value))
        ],
        default=0,
    ) + 1
    while f"s{number}" in used:
        number += 1
    return f"S{number}"


def _subject_identity_key(name):
    """Return a conservative key for matching harmless Subject name variants."""
    normalized = re.sub(r"[^a-z0-9]+", " ", str(name or "").casefold())
    normalized = re.sub(r"^(?:a|an|the)\s+", "", normalized.strip())
    return " ".join(normalized.split())


def _find_existing_subject_name(subjects, proposed_name, subject_id=None, speaker_id=None):
    """Resolve a proposed identity without creating article/case duplicates."""
    if not isinstance(subjects, dict):
        return None
    proposed_key = _subject_identity_key(proposed_name)
    proposed_speaker = str(speaker_id or "").strip().casefold()
    for current_name, record in subjects.items():
        if not isinstance(record, dict):
            continue
        if subject_id is not None and str(record.get("subject_id")) == str(subject_id):
            return current_name
        if (
            proposed_speaker
            and str(record.get("speaker_id") or "").strip().casefold()
            == proposed_speaker
        ):
            return current_name
        if proposed_key and _subject_identity_key(current_name) == proposed_key:
            return current_name
        record_name = str(record.get("name") or "").strip()
        if proposed_key and _subject_identity_key(record_name) == proposed_key:
            return current_name
    return None


def parse_subject_registry(subject_definitions):
    """Parse independent name, gender, Picture, and speaker mappings."""
    registry = {}
    raw_lines = [
        line.strip() for line in str(subject_definitions or "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for line in raw_lines:
        video_origin = False
        match = re.match(
            r"(?i)^\s*<Subject\s+(?P<subject>\d+)>\s+is\s+"
            r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*?)\s*,\s+",
            line,
        )
        if match is None:
            match = re.match(
                r"(?i)^\s*(?:<\s*)?Picture\s+(?P<picture>\d+)\s*(?:>\s*)?"
                r"(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
                r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)"
                r"(?:\s+and\s+aligns\s+with\s+the\s+\d+(?:\.\d+)?-second\s+"
                r"mark\s+of\s+the\s+target\s+video)?\.\s*$",
                line,
            )
            if match is not None:
                subject_id = int(match.group("picture"))
                name = match.group("name").strip()
                picture_ids = [subject_id]
                speaker_id = f"S{subject_id}"
        else:
            subject_id = int(match.group("subject"))
            name = match.group("name").strip()
            picture_ids = [
                int(value)
                for value in re.findall(r"(?i)<Picture\s+(\d+)>", line)
            ]
            picture_ids = list(dict.fromkeys(picture_ids))
            video_origin = bool(re.search(
                r"(?i)(?:\b(?:created|established)\s+(?:by\s+<Video\s+1>|"
                r"in\s+generated\s+video\s+segment\s+\d+)|"
                r"\bcontinued\s+from\s+<Video\s+1>)",
                line,
            ))
            speaker_id = (
                f"S{speaker}"
                if (speaker := next(iter(re.findall(r"(?i)\(S(\d+)\)", line)), None))
                else f"S{subject_id}"
            )
        if match is None:
            continue
        if not picture_ids and not video_origin:
            continue
        picture_ids = list(dict.fromkeys(picture_ids))
        if subject_id in registry:
            raise ValueError(f"Duplicate subject ID: {subject_id}")
        if any(item["name"].lower() == name.lower() for item in registry.values()):
            raise ValueError(f"Duplicate subject name: {name}")
        if speaker_id and any(
            item.get("speaker_id") == speaker_id for item in registry.values()
        ):
            raise ValueError(f"Duplicate speaker ID: {speaker_id}")
        registry_record = {
            "name": name,
            "gender": infer_subject_gender(line),
            "picture_ids": picture_ids,
            "picture_id": picture_ids[0] if picture_ids else None,
            "speaker_id": speaker_id,
        }
        origin_match = re.search(
            r"(?i)\b(?:created|established)\s+in\s+generated\s+video\s+"
            r"segment\s+(\d+)",
            line,
        )
        if origin_match:
            registry_record["origin_segment"] = int(origin_match.group(1))
        registry[subject_id] = registry_record
    #if len(registry) != len(raw_lines):
    #    raise ValueError(
    #        "Every subject definition must declare one <Subject N> and "
    #        "one <Picture N> mapping."
    #    )
    return registry


def new_subject_continuity_record(subject):
    picture_ids = [
        int(picture_id)
        for picture_id in subject.get("picture_ids", [])
        if picture_id is not None
    ]
    picture_id = subject.get("picture_id")
    if picture_id is None and picture_ids:
        picture_id = picture_ids[0]
    return {
        "subject_id": subject.get("subject_id"),
        "name": subject.get("name"),
        "gender": normalize_subject_gender(subject.get("gender")),
        "picture_ids": picture_ids,
        "picture_id": picture_id,
        "speaker_id": (
            subject.get("speaker_id")
            or (
                f"S{subject.get('subject_id')}"
                if str(subject.get("subject_id") or "").isdigit()
                else None
            )
        ),
        "origin_segment": subject.get("origin_segment"),
        # Once generated video establishes a persistent change to the Subject's
        # own physical/topological configuration, a pristine identity reference
        # can become incompatible with later refreshes.
        "persistent_structural_change": bool(
            subject.get("persistent_structural_change", False)
        ),
        "position": "N/A",
        "pose_action": "N/A",
        "wardrobe": {
            "upper": "N/A",
            "lower": "N/A",
            "footwear": "N/A",
            "other": "N/A",
        },
        # Persistent structural relationships of the Subject itself belong here
        # instead of being mixed into transient pose/action prose. Wardrobe,
        # accessories, held props, and garment condition do not.
        "topology": "N/A",
        "body_state": "N/A",
        "physical_condition": "N/A",
        "attached_objects": [],
        "injuries": [],
        "substances": [],
        "spatial_relationships": [],
        "persistent_effects": [],
        "held_props": [],
    }


def continuity_state_for_registry(subject_definitions, state=None):
    """Return state with registered identities plus stable video-only subjects."""
    current = migrate_continuity_state(state) if state else new_continuity_state()
    registry = parse_subject_registry(subject_definitions)
    if isinstance(current.get("subjects"), dict):
        normalized_subjects = {}
        for key, record in current["subjects"].items():
            if not isinstance(record, dict):
                continue
            name = str(key)
            if isinstance(key, str) and key.isdigit() and registry:
                subject_id = int(key)
                registered_name = next(
                    (
                        subject["name"]
                        for subject_id_key, subject in registry.items()
                        if subject_id_key == subject_id
                    ),
                    None,
                )
                name = (
                    registered_name
                    or str(record.get("name", "")).strip()
                    or name
                )
            elif isinstance(key, str) and key.isdigit():
                record_name = str(record.get("name", "")).strip()
                if record_name:
                    name = record_name
            normalized_subjects[name] = record
        current["subjects"] = normalized_subjects
    if not registry and isinstance(current.get("subjects"), dict):
        registry = {
            int(record.get("subject_id", index)): {
                "name": name,
                "gender": normalize_subject_gender(record.get("gender")),
                "picture_ids": record.get(
                        "picture_ids",
                        [record.get("picture_id")],
                    ),
                "picture_id": record.get("picture_id"),
                "speaker_id": record.get("speaker_id"),
            }
            for index, (name, record) in enumerate(
                current["subjects"].items(),
                start=1,
            )
            if isinstance(record, dict) and record.get("picture_id") is not None
        }
    if not registry and str(subject_definitions or "").strip():
        raise RuntimeError(
            "Subject definitions were present but could not be parsed; "
            "refusing to render an empty AUTHORITATIVE OPENING STATE. "
            "Expected one definition per line, for example: "
            "<Subject 1> is Mark, a 40-year-old man referenced in "
            "<Picture 1>. Video-only subjects use: <Subject 2> is creature, "
            "N/A (S2), continued from <Video 1>."
        )
    def copy_continuity_fields(record, existing):
        if not isinstance(existing, dict):
            return
        record["persistent_structural_change"] = bool(
            existing.get("persistent_structural_change", False)
        )
        for field in (
            "position",
            "pose_action",
            "topology",
            "body_state",
            "physical_condition",
        ):
            if isinstance(existing.get(field), str):
                record[field] = existing[field]
        if isinstance(existing.get("held_props"), list):
            record["held_props"] = list(existing["held_props"])
        for field in SUBJECT_LIST_FIELDS:
            if isinstance(existing.get(field), list):
                record[field] = list(existing[field])
        if isinstance(existing.get("wardrobe"), dict):
            for garment in record["wardrobe"]:
                if isinstance(existing["wardrobe"].get(garment), str):
                    record["wardrobe"][garment] = existing["wardrobe"][garment]

    subjects = {}
    used_subject_ids = set()
    for subject_id, subject in registry.items():
        existing_name = _find_existing_subject_name(
            current.get("subjects", {}),
            subject["name"],
            subject_id=subject_id,
            speaker_id=subject.get("speaker_id"),
        )
        existing = current.get("subjects", {}).get(existing_name, {})
        record = new_subject_continuity_record({
            **subject,
            "subject_id": subject_id,
            "origin_segment": subject.get(
                "origin_segment",
                existing.get("origin_segment"),
            ),
        })
        copy_continuity_fields(record, existing)
        subjects[subject["name"]] = record
        used_subject_ids.add(subject_id)

    # A continuing video can establish an important animate Subject without a
    # Picture reference. Preserve it instead of rebuilding only from Pictures.
    next_subject_id = max(used_subject_ids, default=0) + 1
    for name, existing in current.get("subjects", {}).items():
        if (
            not isinstance(existing, dict)
            or _find_existing_subject_name(
                subjects,
                name,
                subject_id=existing.get("subject_id"),
                speaker_id=existing.get("speaker_id"),
            ) is not None
        ):
            continue
        raw_subject_id = existing.get("subject_id")
        try:
            subject_id = int(raw_subject_id)
        except (TypeError, ValueError):
            subject_id = None
        if subject_id is None or subject_id <= 0 or subject_id in used_subject_ids:
            while next_subject_id in used_subject_ids:
                next_subject_id += 1
            subject_id = next_subject_id
            next_subject_id += 1
        picture_ids = [
            int(value)
            for value in existing.get("picture_ids", [])
            if isinstance(value, int) or str(value).isdigit()
        ]
        record = new_subject_continuity_record({
            "subject_id": subject_id,
            "name": name,
            "gender": existing.get("gender"),
            "picture_ids": picture_ids,
            "picture_id": picture_ids[0] if picture_ids else None,
            "speaker_id": existing.get("speaker_id") or f"S{subject_id}",
            "origin_segment": existing.get("origin_segment"),
        })
        copy_continuity_fields(record, existing)
        subjects[name] = record
        used_subject_ids.add(subject_id)
    current["subjects"] = subjects
    current["version"] = CONTINUITY_STATE_VERSION
    return current


_CONTINUITY_TIMESTAMP_RE = re.compile(
    r"(?i)(?:\bat\s+)?\b\d{1,2}:\d{2}(?:\.\d{1,3})?\b"
)

# Structural continuity candidates must be grounded in the newest description.
# Evidence is matched from the candidate's own distinctive words, with a neutral
# region vocabulary preventing evidence about one region from being borrowed for
# another. This supports arbitrary user-supplied material without embedding
# genre-specific or graphic examples in this source file.
_STRUCTURAL_EVIDENCE_STOPWORDS = frozenset({
    "about", "after", "again", "against", "already", "around", "because",
    "before", "being", "between", "current", "during", "final", "frame",
    "front", "into", "near", "newest", "other", "remains", "state", "still",
    "subject", "their", "there", "these", "they", "this", "through", "under",
    "visible", "where", "which", "while", "with",
})

_STRUCTURAL_REGION_PHRASES = (
    "lower body", "upper body",
    "head", "face", "neck", "chest", "abdomen", "waist", "torso", "spine",
    "back", "shoulder", "arm", "wrist", "hand", "finger",
    "leg", "knee", "foot", "hair", "mouth", "jaw",
    "wing", "horn", "tail", "limb",
    "antenna", "panel", "port", "cable", "component", "assembly", "accessory",
)

_STRUCTURAL_REGION_QUALIFIERS = (
    "left", "right", "upper", "lower", "front", "rear", "top", "bottom",
    "inner", "outer",
)


_TERMINAL_ABSENCE_RE = re.compile(
    r"(?i)\b(?:absent|gone|missing|not present|no longer present|"
    r"no longer exists?|ceased to exist|fully (?:dissolved|disintegrated)|"
    r"removed(?: entirely| completely)?)\b"
)
_TERMINAL_DESTRUCTION_RE = re.compile(
    r"(?i)\b(?:destroyed|demolished|irreparably damaged|"
    r"shattered beyond repair)\b"
)
_TERMINAL_PROCESS_RE = re.compile(
    r"(?i)\b(?:dissolv(?:e|es|ing)|disintegrat(?:e|es|ing)|"
    r"break(?:s|ing)? apart|collaps(?:e|es|ing)|fragment(?:s|ing)?)\b"
)
_PERSISTENT_CATEGORICAL_FIELDS = frozenset({
    "topology", "body_state", "attached_objects", "persistent_effects",
    "held_props", "environment.persistent_state",
})


def _terminal_state_status(value):
    """Return the authoritative terminal category expressed by a state fact."""
    text = str(value or "").strip()
    if not text:
        return None
    if _TERMINAL_ABSENCE_RE.search(text):
        return "absent"
    if re.search(
        r"(?i)\bno\s+[^.;:,]{1,80}\s+(?:is|are|remains?)\s+present\b",
        text,
    ):
        return "absent"
    if _TERMINAL_DESTRUCTION_RE.search(text):
        return "destroyed"
    return None


def _terminal_state_label(value):
    """Extract a concise entity/component label from a terminal state fact."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return None
    status_expression = (
        r"(?:absent|gone|missing|not present|no longer present|"
        r"no longer exists?|ceased to exist|fully (?:dissolved|disintegrated)|"
        r"removed(?: entirely| completely)?|destroyed|demolished|"
        r"irreparably damaged|shattered beyond repair)"
    )
    patterns = (
        rf"^(?P<label>[^:;,.]{{1,100}}?)\s*:\s*(?:is\s+)?{status_expression}\b",
        rf"^(?P<label>[^:;,.]{{1,100}}?)\s+(?:is|are|was|were|being|"
        rf"has been|have been|remains?)\s+(?:now\s+|fully\s+|completely\s+|"
        rf"entirely\s+|both\s+)*{status_expression}\b",
        rf"^(?P<label>[^:;,.]{{1,100}}?)\s+{status_expression}(?:\s*$|\s*[,;])",
        rf"^(?:the\s+)?{status_expression}\s+(?P<label>[^:;,.]{{1,100}}?)(?:\s*$|\s*[,;])",
        rf"^no\s+(?P<label>[^:;,.]{{1,100}}?)\s+(?:is|are|remains?)\s+present\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        label = match.group("label").strip(" ,;:-")
        label = re.sub(r"(?i)^(?:the|a|an)\s+", "", label)
        label = re.sub(r"(?i)^(?:its|their)\s+", "", label)
        if label and len(label.split()) <= 12:
            return label
    return None


def _categorical_persistent_state(value, field_name=""):
    """Collapse definitive absence/destruction prose to a current category."""
    text = str(value or "").strip()
    if field_name.startswith("wardrobe."):
        return _terminal_state_status(text) or text
    if field_name not in _PERSISTENT_CATEGORICAL_FIELDS:
        return text
    clauses = [
        clause.strip(" ,;:-")
        for clause in re.split(r"\s*(?:;|\n+)\s*", text)
        if clause.strip(" ,;:-")
    ]
    terminal_by_index = {}
    for index, clause in enumerate(clauses):
        status = _terminal_state_status(clause)
        if status is None:
            continue
        label = _terminal_state_label(clause)
        # Preserve the original clause wording when possible (e.g. "left
        # horn missing") rather than normalizing to "label: absent".
        terminal_by_index[index] = clause if label else status
    if not terminal_by_index:
        return text
    normalized = []
    for index, clause in enumerate(clauses):
        if index in terminal_by_index:
            normalized.append(terminal_by_index[index])
        elif _TERMINAL_PROCESS_RE.search(clause) is None:
            normalized.append(clause)
    return "; ".join(dict.fromkeys(normalized))


def _scrub_snapshot_text(value, field_name=""):
    """Return snapshot-safe prose; historical timestamped actions are discarded."""
    if not isinstance(value, str):
        return value
    cleaned = sanitize_previous_state_value(value).strip()
    if not cleaned:
        return "N/A"

    # pose_action / ongoing_action must describe what is true at the final
    # frame, not replay a timeline from the prior clip. If the updater returns
    # timestamps in these fields, treat that as historical narration and reject
    # it rather than carrying it into the next opening prompt.
    if field_name in {"pose_action", "ongoing_action"} and _CONTINUITY_TIMESTAMP_RE.search(cleaned):
        return "N/A"

    cleaned = re.sub(r"\s*\(\s*at\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*\)", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+at\s+\d{1,2}:\d{2}(?:\.\d{1,3})?", "", cleaned, flags=re.I)
    cleaned = _CONTINUITY_TIMESTAMP_RE.sub("", cleaned)
    cleaned = re.sub(r"\s*;\s*;\s*", "; ", cleaned)
    cleaned = re.sub(r"\s+,\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r"\(\s*[–—-]\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    cleaned = _categorical_persistent_state(cleaned, field_name)
    return cleaned or "N/A"


def _continuity_item_text(item, field_name=""):
    """Convert one continuity-list item to concise natural-language text.

    Older checkpoints and unconstrained LLM responses may contain dictionaries
    inside fields that are supposed to be arrays of strings. Never stringify
    those dictionaries: doing so leaks Python/JSON syntax into H3 prompts.
    Instead, keep only their human-readable semantic values.
    """
    if isinstance(item, str):
        cleaned = _scrub_snapshot_text(item, field_name)
        return None if cleaned == "N/A" else cleaned
    if not isinstance(item, dict):
        return None

    def scalar(key):
        value = item.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            text = str(value).strip()
            if text and text.upper() != "N/A" and text not in {"-", "–", "—"}:
                return text.replace("_", " ")
        return None

    # held_props commonly arrives as {"item": "...", "duration": "..."}.
    if field_name == "held_props":
        text = scalar("item") or scalar("description")
        return _scrub_snapshot_text(text, field_name) if text else None

    description = scalar("description")
    location = scalar("location")
    relation = scalar("relation")
    subject = scalar("subject") or scalar("environment")
    label = (
        scalar("type")
        or scalar("material")
        or (None if scalar("effect_type") in {"visual", "auditory", "mechanical"}
            else scalar("effect_type"))
        or scalar("item")
    )
    source = scalar("source")
    severity = scalar("severity")

    parts = []
    if subject and relation:
        parts.append(f"{subject}: {relation}")
    elif relation:
        parts.append(relation)
    elif label:
        parts.append(label)
    if location:
        if not parts:
            connector = ""
        elif location.casefold().startswith((
            "held by ", "held in ", "inside ", "on ", "in ", "between ",
            "beneath ", "under ", "above ", "across ", "around ",
        )):
            connector = " "
        else:
            connector = " at "
        parts.append(f"{connector}{location}")
    if description and description.casefold() not in " ".join(parts).casefold():
        parts.append((", " if parts else "") + description)
    if source and source.casefold() not in " ".join(parts).casefold():
        parts.append((", from " if parts else "from ") + source)
    if severity and severity.casefold() not in " ".join(parts).casefold():
        parts.append((", " if parts else "") + severity)

    text = "".join(parts).strip(" ,;:-")
    if not text:
        return None
    cleaned = _scrub_snapshot_text(text, field_name)
    return None if cleaned == "N/A" else cleaned


def _scrub_continuity_subject_record(record):
    if not isinstance(record, dict):
        return record
    for field in (
        "position", "pose_action", "topology", "body_state", "physical_condition"
    ):
        if field in record:
            record[field] = _scrub_snapshot_text(record.get(field), field)
    wardrobe = record.get("wardrobe")
    if isinstance(wardrobe, dict):
        for garment in ("upper", "lower", "footwear", "other"):
            if garment in wardrobe:
                wardrobe[garment] = _scrub_snapshot_text(wardrobe.get(garment), f"wardrobe.{garment}")
    for field in SUBJECT_LIST_FIELDS:
        if isinstance(record.get(field), list):
            record[field] = list(dict.fromkeys(
                cleaned
                for item in record[field]
                if (cleaned := _continuity_item_text(item, field))
            ))
    _remove_wardrobe_owned_persistent_effects(record)
    return record


def scrub_continuity_state(state):
    """Remove historical timeline fragments from a stored final-frame state."""
    if not isinstance(state, dict):
        return state
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        if field in state:
            state[field] = _scrub_snapshot_text(state.get(field), field)
    environment = state.get("environment")
    if isinstance(environment, dict):
        for field in ("location", "persistent_state"):
            if field in environment:
                environment[field] = _scrub_snapshot_text(environment.get(field), f"environment.{field}")
    subjects = state.get("subjects")
    if isinstance(subjects, dict):
        for record in subjects.values():
            _scrub_continuity_subject_record(record)
    return state


def normalize_continuity_state(state):
    """Normalize a continuity state to the current schema.
    
    Ensures the state has the proper structure and converts
    any legacy fields to the current format.
    """
    if not isinstance(state, dict):
        return new_continuity_state()
    
    normalized = new_continuity_state()
    environment = state.get("environment")
    
    if isinstance(environment, dict):
        normalized["environment"] = {
            "location": environment.get("location", "N/A") or "N/A",
            "persistent_state": environment.get("persistent_state", "N/A") or "N/A",
        }
    elif isinstance(environment, str) and environment.strip():
        normalized["environment"] = {
            "location": environment.strip(),
            "persistent_state": "N/A",
        }
    
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        value = state.get(field)
        if isinstance(value, str) and value.strip():
            normalized[field] = value.strip()
    
    subjects = state.get("subjects")
    if isinstance(subjects, dict):
        normalized["subjects"] = {}
        for key, record in subjects.items():
            if not isinstance(record, dict):
                continue
            normalized["subjects"][key] = record
    
    return normalized


def migrate_continuity_state(state):
    """Return a valid structured state without discarding legacy prose."""
    if not isinstance(state, dict):
        return new_continuity_state()
    migrated = new_continuity_state()
    environment = state.get("environment")
    if isinstance(environment, dict):
        def migrated_environment_string(value, field_name):
            if isinstance(value, str):
                return value.strip() or "N/A"
            if isinstance(value, (list, tuple)):
                parts = [
                    cleaned
                    for item in value
                    if (cleaned := _continuity_item_text(item, field_name))
                ]
                return "; ".join(parts) if parts else "N/A"
            return "N/A"

        migrated["environment"] = {
            "location": migrated_environment_string(
                environment.get("location", "N/A"),
                "environment.location",
            ),
            "persistent_state": migrated_environment_string(
                environment.get("persistent_state", "N/A"),
                "environment.persistent_state",
            ),
        }
    elif isinstance(environment, str) and environment.strip():
        migrated["environment"] = {
            "location": environment.strip(),
            "persistent_state": "N/A",
        }
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        value = state.get(field)
        if isinstance(value, str) and value.strip():
            migrated[field] = value.strip()
    subjects = state.get("subjects")
    if isinstance(subjects, dict):
        normalized_subjects = {}
        for key, record in subjects.items():
            if not isinstance(record, dict):
                continue
            if isinstance(key, str) and key.isdigit():
                subject_id = int(key)
                if subject_id in parse_subject_registry(
                    state.get("subject_definitions", "")
                ):
                    name = parse_subject_registry(
                        state.get("subject_definitions", "")
                    )[subject_id]["name"]
                    normalized_subjects[name] = record
                    continue
            normalized_subjects[str(key)] = record
        # Backfill newly introduced structured fields without discarding
        # legacy checkpoints.
        for record in normalized_subjects.values():
            if isinstance(record, dict):
                record["gender"] = normalize_subject_gender(record.get("gender"))
                record["persistent_structural_change"] = bool(
                    record.get("persistent_structural_change", False)
                )
                if (
                    not record.get("speaker_id")
                    and str(record.get("subject_id") or "").isdigit()
                ):
                    record["speaker_id"] = f"S{record['subject_id']}"
                record.setdefault("topology", "N/A")
                for field in SUBJECT_LIST_FIELDS:
                    record.setdefault(field, [])
        migrated["subjects"] = normalized_subjects
    return scrub_continuity_state(migrated)


def get_refresh_incompatible_picture_ids(continuity_state):
    """Return Picture IDs incompatible with the Subject's current configuration."""
    incompatible = set()
    state = migrate_continuity_state(continuity_state)
    for record in state.get("subjects", {}).values():
        if not isinstance(record, dict) or not record.get(
            "persistent_structural_change", False
        ):
            continue
        for picture_id in record.get("picture_ids", []):
            if isinstance(picture_id, int) or str(picture_id).isdigit():
                incompatible.add(int(picture_id))
        picture_id = record.get("picture_id")
        if isinstance(picture_id, int) or str(picture_id).isdigit():
            incompatible.add(int(picture_id))
    return incompatible


def get_continuity_picture_ids(continuity_state):
    """Return every stable Picture ID represented by the continuity state."""
    picture_ids = set()
    state = migrate_continuity_state(continuity_state)
    for record in state.get("subjects", {}).values():
        if not isinstance(record, dict):
            continue
        for picture_id in record.get("picture_ids", []):
            if isinstance(picture_id, int) or str(picture_id).isdigit():
                picture_ids.add(int(picture_id))
        picture_id = record.get("picture_id")
        if isinstance(picture_id, int) or str(picture_id).isdigit():
            picture_ids.add(int(picture_id))
    return picture_ids


def get_conditioning_excluded_picture_ids(continuity_state, conditioning_mode):
    """Return Picture IDs omitted from H3 text/reference conditioning.

    Canonical Picture IDs remain stable in continuity and Director context. Both
    clean refresh and latent continuation exclude only Pictures whose Subjects
    have become structurally incompatible; append H3 packing handles any gaps.
    """
    return get_refresh_incompatible_picture_ids(continuity_state)


def _known_continuity_value(value):
    if not isinstance(value, str):
        return None
    value = sanitize_previous_state_value(value).strip()
    return None if not value or value.upper() == "N/A" else value


def _english_join(items):
    items = [str(item).strip() for item in items if str(item).strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _subject_wardrobe(record):
    wardrobe = record.get("wardrobe", {})
    if not isinstance(wardrobe, dict):
        return []
    return [
        value
        for field in ("upper", "lower", "footwear", "other")
        if (value := _known_continuity_value(wardrobe.get(field)))
    ]


_WARDROBE_CONTINUITY_LABELS = {
    "upper": "upper garment",
    "lower": "lower garment",
    "footwear": "footwear",
    "other": "additional garment or accessory",
}


def _h3_terminal_constraint(value, field_name=""):
    """Render a terminal database fact as a result-only H3 constraint."""
    status = _terminal_state_status(value)
    if status is None:
        return None
    if field_name in {"topology", "body_state"}:
        return "Preserve the current structural configuration."
    if field_name.startswith("wardrobe."):
        key = field_name.partition(".")[2]
        label = _WARDROBE_CONTINUITY_LABELS.get(key, "garment")
    else:
        label = _terminal_state_label(value)
    if not label:
        if field_name == "held_props":
            label = "held prop"
        elif field_name == "attached_objects":
            label = "attached object"
        else:
            label = "affected item"
    if status == "absent":
        return f"No {label} is present."
    return f"The {label} remains destroyed."


def _split_h3_terminal_facts(items, field_name):
    """Separate result-only constraints from ordinary current-state wording."""
    current = []
    constraints = []
    for item in items:
        constraint = _h3_terminal_constraint(item, field_name)
        if constraint:
            constraints.append(constraint)
        else:
            current.append(item)
    return current, constraints


def _subject_picture_tags(record, excluded_picture_ids=None):
    excluded = {
        int(value)
        for value in (excluded_picture_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }
    return [
        f"<Picture {picture_id}>"
        for picture_id in record.get("picture_ids", [])
        if picture_id is not None and int(picture_id) not in excluded
    ]


def _subject_opening_sentence(subject_id, name, record, summary=False):
    tag = f"<Subject {subject_id}>"
    position = _known_continuity_value(record.get("position"))
    pose_action = _known_continuity_value(record.get("pose_action"))
    wardrobe = []
    terminal_constraints = []
    wardrobe_state = record.get("wardrobe", {})
    if isinstance(wardrobe_state, dict):
        for field in ("upper", "lower", "footwear", "other"):
            value = _known_continuity_value(wardrobe_state.get(field))
            if not value:
                continue
            constraint = _h3_terminal_constraint(value, f"wardrobe.{field}")
            if constraint:
                terminal_constraints.append(constraint)
            else:
                wardrobe.append(value)
    topology = _known_continuity_value(record.get("topology"))
    body_state = _known_continuity_value(record.get("body_state"))
    physical_condition = _known_continuity_value(
        record.get("physical_condition")
    )
    held_props = [
        cleaned
        for prop in record.get("held_props", [])
        if (cleaned := _continuity_item_text(prop, "held_props"))
    ]
    persistent_lists = {
        field: [
            cleaned
            for item in record.get(field, [])
            if (cleaned := _continuity_item_text(item, field))
        ]
        for field in SUBJECT_LIST_FIELDS
    }
    topology_constraint = _h3_terminal_constraint(topology, "topology")
    body_state_constraint = _h3_terminal_constraint(body_state, "body_state")
    for constraint in (topology_constraint, body_state_constraint):
        if constraint and constraint not in terminal_constraints:
            terminal_constraints.append(constraint)
    held_props, constraints = _split_h3_terminal_facts(
        held_props,
        "held_props",
    )
    terminal_constraints.extend(constraints)
    for field in PERSISTENT_SUBJECT_LIST_FIELDS:
        persistent_lists[field], constraints = _split_h3_terminal_facts(
            persistent_lists[field],
            field,
        )
        terminal_constraints.extend(constraints)

    if summary:
        # subject_definitions already carries identity.  Only repeat a Subject
        # here when the structured state contributes actual opening-state data.
        if not position:
            return ""
        return f"{tag} {name} remains {position}."

    facts = []
    if position:
        facts.append(f"At the opening, {name} remains {position}")
    if wardrobe:
        wardrobe_text = f"wearing {_english_join(wardrobe)}"
        if facts:
            facts[-1] += f", {wardrobe_text}"
        else:
            facts.append(f"At the opening, {name} is {wardrobe_text}")
    if pose_action:
        facts.append(f"Opening pose/action: {pose_action}")
    if topology and not topology_constraint:
        facts.append(f"Topology: {topology}")
    if body_state and not body_state_constraint:
        facts.append(f"Body state: {body_state}")
    if physical_condition:
        facts.append(f"Physical condition: {physical_condition}")
    if held_props:
        facts.append(f"Held props: {_english_join(held_props)}")
    if persistent_lists["attached_objects"]:
        facts.append(
            "Attached objects: "
            + _english_join(persistent_lists["attached_objects"])
        )
    if persistent_lists["injuries"]:
        facts.append("Injuries: " + _english_join(persistent_lists["injuries"]))
    if persistent_lists["substances"]:
        facts.append(
            "Persistent substances: "
            + _english_join(persistent_lists["substances"])
        )
    if persistent_lists["spatial_relationships"]:
        facts.append(
            "Physical relationships: "
            + _english_join(persistent_lists["spatial_relationships"])
        )
    if persistent_lists["persistent_effects"]:
        facts.append(
            "Persistent effects: "
            + _english_join(persistent_lists["persistent_effects"])
        )
    facts.extend(dict.fromkeys(terminal_constraints))
    return ". ".join(fact.rstrip(". ") for fact in facts) + ("." if facts else "")


def _ordered_continuity_subjects(state):
    subjects = []
    for fallback_id, (name, record) in enumerate(
        state.get("subjects", {}).items(),
        start=1,
    ):
        if not isinstance(record, dict):
            continue
        try:
            subject_id = int(record.get("subject_id", fallback_id))
        except (TypeError, ValueError):
            subject_id = fallback_id
        subjects.append((subject_id, name, record))
    return sorted(subjects, key=lambda item: (item[0], item[1].lower()))


def _remove_absent_subject_mentions_from_h3_value(value, absent_names):
    """Drop continuity facts that explicitly name an off-camera Subject."""
    if isinstance(value, str):
        if any(
            re.search(
                rf"(?i)(?<!\w){re.escape(name)}(?!\w)",
                value,
            )
            for name in absent_names
            if str(name).strip()
        ):
            return ""
        return value
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (
                cleaned := _remove_absent_subject_mentions_from_h3_value(
                    item,
                    absent_names,
                )
            )
        ]
    if isinstance(value, dict):
        return {
            key: _remove_absent_subject_mentions_from_h3_value(
                item,
                absent_names,
            )
            for key, item in value.items()
        }
    return value


def _h3_continuity_state_for_visible_subjects(state, visible_subject_ids):
    """Return an H3-only copy without cross-references to absent Subjects."""
    visible = {
        int(value)
        for value in (visible_subject_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }
    rendered = copy.deepcopy(state)
    ordered = _ordered_continuity_subjects(rendered)
    absent_names = [name for subject_id, name, _ in ordered if subject_id not in visible]
    if not absent_names:
        return rendered

    for subject_id, _, record in ordered:
        if subject_id not in visible:
            continue
        for field in (
            *CURRENT_SUBJECT_SCALAR_FIELDS,
            *PERSISTENT_SUBJECT_SCALAR_FIELDS,
            *SUBJECT_LIST_FIELDS,
            "wardrobe",
        ):
            if field in record:
                record[field] = _remove_absent_subject_mentions_from_h3_value(
                    record[field],
                    absent_names,
                )
    for field in ("environment", "camera", "ongoing_action", "ongoing_audio"):
        if field in rendered:
            rendered[field] = _remove_absent_subject_mentions_from_h3_value(
                rendered[field],
                absent_names,
            )
    return rendered


_EXPLICIT_REMOVAL_RE = re.compile(
    r"(?i)\b(?:remove[sd]?|removing|"
    r"pull(?:s|ed|ing)?(?:\s+\S+){0,8}?\s+out|"
    r"unfasten(?:s|ed|ing)?|release[sd]?|releasing|"
    r"drop(?:s|ped|ping)?|wipe[sd]?\s+(?:off|away)|wash(?:es|ed|ing)?\s+(?:off|away)|"
    r"clean(?:s|ed|ing)?\s+(?:off|away)|dissipat(?:es|ed|ing)|fade[sd]?\s+away)\b"
)


_STRUCTURED_CONTINUITY_FRAGMENT_RE = re.compile(
    r"(?is)\{[^{}]{0,1200}(?:['\"](?:type|location|description|subject|relation|"
    r"effect_type|material|item|duration|severity)['\"]\s*:)[^{}]{0,1200}\}"
)


def inject_persistent_state_into_description(detailed_description):
    """Remove structured continuity fragments from H3 scene prose.

    The append workflow now carries a much larger trailing video context window,
    while the director receives the committed continuity snapshot separately.
    Automatically prepending every stored fact made descriptions repetitive and
    could leak structured state into the prompt. Off-camera state therefore stays
    in the continuity store and is reintroduced by the director only when it is
    actually visible/relevant on re-entry.
    """
    description = str(detailed_description or "")
    description = _STRUCTURED_CONTINUITY_FRAGMENT_RE.sub("", description)
    description = re.sub(r"\s+,", ",", description)
    description = re.sub(r",\s*,+", ", ", description)
    description = re.sub(r"\s+", " ", description).strip(" ,")
    return description

def format_director_opening_state(state, subject_definitions=""):
    """Render a compact physical starting state for the Director LLM."""
    state = continuity_state_for_registry(subject_definitions, state)
    lines = ["OPENING STATE"]
    environment = state.get("environment", {})
    location = _known_continuity_value(environment.get("location"))
    persistent_state = _known_continuity_value(environment.get("persistent_state"))
    if location:
        lines.append(f"Location: {location}")
    if persistent_state:
        lines.append(f"Environment: {persistent_state}")
    camera = _known_continuity_value(state.get("camera"))
    ongoing_action = _known_continuity_value(state.get("ongoing_action"))
    ongoing_audio = _known_continuity_value(state.get("ongoing_audio"))
    if camera:
        lines.append(f"Camera: {camera}")
    if ongoing_action:
        lines.append(f"Ongoing action: {ongoing_action}")
    if ongoing_audio:
        lines.append(f"Ongoing audio: {ongoing_audio}")

    for subject_id, name, record in _ordered_continuity_subjects(state):
        facts = []
        for label, field in (
            ("position", "position"),
            ("pose", "pose_action"),
            ("topology", "topology"),
            ("body", "body_state"),
            ("condition", "physical_condition"),
        ):
            value = _known_continuity_value(record.get(field))
            if value:
                facts.append(f"{label}: {value}")
        wardrobe = _subject_wardrobe(record)
        if wardrobe:
            facts.append("wardrobe: " + _english_join(wardrobe))
        for field, label in (
            ("held_props", "held"),
            ("attached_objects", "attached"),
            ("injuries", "injuries"),
            ("substances", "substances"),
            ("spatial_relationships", "relationships"),
            ("persistent_effects", "effects"),
        ):
            values = [
                cleaned
                for item in record.get(field, [])
                if (cleaned := _continuity_item_text(item, field))
            ]
            if values:
                facts.append(f"{label}: {_english_join(values)}")
        if facts:
            lines.append(f"<Subject {subject_id}> {name}: " + "; ".join(facts))
    if len(lines) == 1:
        lines.append("No prior physical state is established.")
    return "\n".join(lines)


def story_arc_phase_for_beat(macro_arc, beat_id):
    """Return the macro phase containing one global beat ID."""
    try:
        beat_id = int(beat_id)
    except (TypeError, ValueError):
        return None
    phases = macro_arc.get("phases", []) if isinstance(macro_arc, dict) else []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        try:
            start = int(phase.get("beat_start"))
            end = int(phase.get("beat_end"))
        except (TypeError, ValueError):
            continue
        if start <= beat_id <= end:
            return phase
    return None


def format_authoritative_opening_state(
    state,
    subject_definitions="",
    include_camera=True,
    excluded_picture_ids=None,
    visible_subject_ids=None,
):
    """Render continuation/reference guidance, optionally including camera state."""
    state = continuity_state_for_registry(subject_definitions, state)
    excluded_picture_ids = {
        int(value)
        for value in (excluded_picture_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }
    visible_ids = (
        None
        if visible_subject_ids is None
        else {
            int(value)
            for value in visible_subject_ids
            if isinstance(value, int) or str(value).isdigit()
        }
    )
    if visible_ids is not None:
        state = _h3_continuity_state_for_visible_subjects(
            state,
            visible_ids,
        )
    subjects = [
        subject
        for subject in _ordered_continuity_subjects(state)
        if visible_ids is None or subject[0] in visible_ids
    ]
    if not subjects:
        if visible_ids is None:
            raise RuntimeError(
                "Cannot render authoritative continuation guidance: no subjects "
                "were available."
            )

    location = _known_continuity_value(state["environment"].get("location"))
    location_text = location or "environment"
    continuation_details = (
        "lighting, spatial layout, subject positions, wardrobe condition, "
        "physical states, props, and environmental continuity"
        if subjects
        else "lighting, spatial layout, and environmental continuity"
    )
    lines = [
        "<Video 1> is the immediately preceding successfully rendered video "
        "and provides the authoritative continuation starting point. Preserve "
        f"its {location_text}, {continuation_details} until an action in this "
        "target video visibly changes them.",
        "",
        "summary:",
        "",
    ]

    summary_sentences = [
        "[video continuation + reference generation] The target video continues "
        "directly from the final observable state of <Video 1>."
    ]
    summary_sentences.extend(
        sentence
        for subject_id, name, record in subjects
        if (sentence := _subject_opening_sentence(
            subject_id, name, record, summary=True
        ))
    )

    picture_numbers = []
    picture_subject_names = []
    for _, name, record in subjects:
        record_pictures = [
            int(value)
            for value in record.get("picture_ids", [])
            if (isinstance(value, int) or str(value).isdigit())
            and int(value) not in excluded_picture_ids
        ]
        if record_pictures:
            picture_numbers.extend(record_pictures)
            picture_subject_names.append(name)
    picture_numbers = list(dict.fromkeys(picture_numbers))
    picture_subject_names = list(dict.fromkeys(picture_subject_names))
    if picture_numbers:
        picture_label = (
            f"Picture {picture_numbers[0]}"
            if len(picture_numbers) == 1
            else f"Pictures {_english_join(picture_numbers)}"
        )
        identity_label = (
            f"{picture_subject_names[0]}'s identity"
            if len(picture_subject_names) == 1
            else _english_join(
                f"{name}'s" for name in picture_subject_names
            ) + " identities"
        )
        picture_verb = "preserves" if len(picture_numbers) == 1 else "preserve"
        summary_sentences.append(
            f"{picture_label} {picture_verb} {identity_label} without overriding "
            "the physical continuation established by <Video 1>."
        )
    lines.append(" ".join(summary_sentences))
    lines.extend(["", "retention_analysis:", ""])

    for subject_id, name, record in subjects:
        picture_tags = _subject_picture_tags(
            record,
            excluded_picture_ids=excluded_picture_ids,
        )
        details = _subject_opening_sentence(subject_id, name, record)
        if picture_tags:
            source = (
                f"Preserve {name}'s identity from {_english_join(picture_tags)}."
            )
            line = f"<Subject {subject_id}>: fully_preserved - {source}"
            if details:
                line += f" {details}"
        elif details:
            line = f"<Subject {subject_id}>: fully_preserved - {details}"
        else:
            # Identity is already in subject_definitions and <Video 1> carries
            # appearance. Avoid repeating an empty dynamic Subject three times.
            continue
        lines.extend([line, ""])

    video_details = []
    persistent_state = _known_continuity_value(
        state["environment"].get("persistent_state")
    )
    camera = _known_continuity_value(state.get("camera"))
    ongoing_action = _known_continuity_value(state.get("ongoing_action"))
    ongoing_audio = _known_continuity_value(state.get("ongoing_audio"))
    if persistent_state:
        terminal_constraint = _h3_terminal_constraint(
            persistent_state,
            "environment.persistent_state",
        )
        video_details.append(terminal_constraint or persistent_state)
    if include_camera and camera:
        video_details.append(f"camera/framing: {camera}")
    if ongoing_action:
        video_details.append(f"ongoing action: {ongoing_action}")
    if ongoing_audio:
        video_details.append(f"ongoing audio: {ongoing_audio}")
    if subjects:
        subject_names = _english_join(name for _, name, _ in subjects)
        video_line = (
            f"<Video 1>: fully_preserved - Preserve the {location_text}, lighting, "
            f"spatial layout, positions of {subject_names}, wardrobe condition, "
            "physical states, props, and immediate physical continuity from the "
            "final frame of the preceding video."
        )
    else:
        video_line = (
            f"<Video 1>: fully_preserved - Preserve the {location_text}, lighting, "
            "spatial layout, and immediate environmental continuity from the final "
            "frame of the preceding video."
        )
    if video_details:
        result_constraints = [
            detail for detail in video_details
            if str(detail).rstrip().endswith(".")
        ]
        descriptive_details = [
            detail for detail in video_details
            if not str(detail).rstrip().endswith(".")
        ]
        if descriptive_details:
            video_line += f" Also preserve {_english_join(descriptive_details)}."
        if result_constraints:
            video_line += " " + " ".join(result_constraints)
    lines.append(video_line)
    return "\n".join(lines)


def format_subject_registry(subject_definitions):
    """Render only canonical identity mappings for the director user prompt."""
    registry = parse_subject_registry(subject_definitions)
    if not registry:
        return "N/A"

    lines = []
    for subject_id, subject in registry.items():
        speaker = subject.get("speaker_id") or "N/A"
        lines.append(
            f"- canonical_name: {subject['name']}\n"
            f"  subject_id: {subject_id}\n"
            f"  gender: {subject['gender']}\n"
            f"  picture_ids: {json.dumps(subject.get('picture_ids', [subject['picture_id']]))}\n"
            f"  continuation_source: "
            f"{'Picture reference(s)' if subject.get('picture_ids') else '<Video 1>'}\n"
            f"  speaker_id: {speaker}"
        )
    return "\n".join(lines)


def derive_additional_subject_definitions(
    base_subject_definitions,
    continuity_state,
):
    """Render video-created Subject definitions from continuity_state.

    continuity_state is the single source of truth for dynamic Subjects.  The
    returned text lines are only a derived prompt representation; they are not a
    second persistent Subject registry.
    """
    base_registry = parse_subject_registry(base_subject_definitions)
    base_ids = set(base_registry)
    base_names = {
        record["name"].casefold() for record in base_registry.values()
    }
    state = continuity_state_for_registry(
        base_subject_definitions,
        copy.deepcopy(continuity_state),
    )
    definitions = []
    for subject_id, name, record in _ordered_continuity_subjects(state):
        if subject_id in base_ids or name.casefold() in base_names:
            continue
        if record.get("picture_ids"):
            continue
        gender = normalize_subject_gender(record.get("gender"))
        speaker_id = str(record.get("speaker_id") or f"S{subject_id}").upper()
        try:
            origin_segment = int(record.get("origin_segment"))
        except (TypeError, ValueError):
            origin_segment = 1
        definitions.append(
            f"<Subject {subject_id}> is {name}, {gender} ({speaker_id}), "
            "continued from <Video 1>."
        )
    return definitions


def subject_definitions_for_state(base_subject_definitions, continuity_state):
    """Combine subjects.txt with dynamic Subjects derived from current state."""
    return combine_subject_definitions(
        base_subject_definitions,
        derive_additional_subject_definitions(
            base_subject_definitions,
            continuity_state,
        ),
    )


def combine_subject_definitions(subject_definitions, additional_definitions):
    """Combine immutable subjects.txt content with run-local subjects."""
    parts = [str(subject_definitions or "").strip()]
    parts.extend(
        str(definition).strip()
        for definition in additional_definitions or []
        if str(definition).strip()
    )
    return "\n".join(part for part in parts if part)


def collect_additional_subject_definitions(
    subject_definitions,
    additional_definitions=None,
    continuity_state=None,
    origin_segment=None,
    **kwargs,
):
    """Return dynamic Subject prompt lines derived from continuity_state.

    ``additional_definitions`` is accepted for backward compatibility and only
    used to report which rendered lines are new.  Dynamic identity itself lives
    exclusively in continuity_state["subjects"].
    """
    # Backward-compatibility: callers historically passed
    # (subject_definitions, continuity_state). Detect that case where the
    # second positional argument is a continuity state dict and adapt.
    if isinstance(additional_definitions, dict) and continuity_state is None:
        continuity_state = additional_definitions
        additional_definitions = None

    # Accept legacy keyword name used by older tests/callers.
    if "previous_definitions" in kwargs and additional_definitions is None:
        additional_definitions = kwargs.get("previous_definitions")

    # origin_segment is not used here but accepted for callers that provide it
    # so keep the parameter for signature compatibility.
    previous = {
        str(definition).strip()
        for definition in (additional_definitions or [])
        if str(definition).strip()
    }
    derived = derive_additional_subject_definitions(
        subject_definitions,
        continuity_state,
    )
    added = [definition for definition in derived if definition not in previous]
    return derived, added


def clear_dynamic_subjects_for_new_phase(
    base_subject_definitions,
    continuity_state,
):
    """Remove video-created Subjects while retaining file-backed identities."""
    base_registry = parse_subject_registry(base_subject_definitions)
    base_names = {record["name"] for record in base_registry.values()}
    normalized = continuity_state_for_registry(
        base_subject_definitions,
        copy.deepcopy(continuity_state),
    )
    removed_names = [
        name for name in normalized.get("subjects", {}) if name not in base_names
    ]
    normalized["subjects"] = {
        name: record
        for name, record in normalized.get("subjects", {}).items()
        if name in base_names
    }
    return normalized, removed_names


def reset_generation_state_subjects_for_new_phase(
    generation_state,
    base_subject_definitions,
    continuity_state,
):
    """Clear dynamic Subjects from current state and its checkpoint fields."""
    cleared_state, removed_names = clear_dynamic_subjects_for_new_phase(
        base_subject_definitions,
        continuity_state,
    )
    generation_state["subject_registry_state"] = migrate_continuity_state(
        cleared_state
    )
    generation_state.pop("additional_subject_definitions", None)
    return cleared_state, removed_names


def format_beat_generation_subjects(subject_definitions):
    """Render parsed subject names and descriptive prose for beat planning."""
    meaningful_lines = [
        (line_number, line.strip())
        for line_number, line in enumerate(
            str(subject_definitions or "").splitlines(),
            start=1,
        )
        if line.strip() and not line.strip().startswith("#")
    ]
    if not meaningful_lines:
        return ""

    try:
        registry = parse_subject_registry(subject_definitions)
    except ValueError as error:
        raise ValueError(f"Invalid subjects.txt: {error}") from error

    for line_number, line in meaningful_lines:
        try:
            parsed_line = parse_subject_registry(line)
        except ValueError as error:
            raise ValueError(
                f"Invalid subjects.txt definition on line {line_number}: "
                f"{error}"
            ) from error
        if not parsed_line:
            raise ValueError(
                f"Could not parse subjects.txt line {line_number}: {line!r}. "
                "Expected '<Subject N> is Name, optional description "
                "referenced in <Picture N>.' or a generated video subject "
                "entry written by this program."
            )

    if len(registry) != len(meaningful_lines):
        raise ValueError(
            "Invalid subjects.txt: every non-comment line must define exactly "
            "one unique subject."
        )

    definition_lines = {
        int(match.group("subject")): line.strip()
        for line in str(subject_definitions or "").splitlines()
        if (
            match := re.match(
                r"(?i)^\s*<Subject\s+(?P<subject>\d+)>\s+is\s+",
                line,
            )
        )
    }
    characters = []
    for subject_id, subject in registry.items():
        name = subject["name"]
        details = ""
        line = definition_lines.get(subject_id, "")
        if line:
            match = re.match(
                rf"(?i)^\s*<Subject\s+{subject_id}>\s+is\s+"
                rf"{re.escape(name)}\s*(?:,\s*(?P<details>.*))?$",
                line,
            )
            if match:
                details = str(match.group("details") or "")
                details = re.sub(r"(?i)\s*\(S\d+\)\s*", " ", details)
                details = re.sub(
                    r"(?i)\s*(?:,?\s*(?:and\s+)?)?referenced\s+in"
                    r"(?:\s*<Picture\s+\d+>\s*(?:,|and)?)+\.?(?:\s*)$",
                    "",
                    details,
                )
                details = " ".join(details.split()).strip(" ,;.")
        if details:
            characters.append(f"- {name} is {details}.")
        else:
            characters.append(f"- {name} is a main character.")
    subject_information = "\n".join(characters)
    if len(characters) != len(registry):
        raise RuntimeError(
            "subjects.txt parsed, but not every subject could be prepared for "
            "beat generation."
        )
    return subject_information


_DIALOGUE_BLOCK_PATTERN = re.compile(
    r"<d>(?P<dialogue>.*?)</d>",
    flags=re.IGNORECASE | re.DOTALL,
)
_DIALOGUE_LANGUAGE_TAG_PATTERN = re.compile(r"^\s*\[[^\]\r\n]{1,40}\]\s*")


def extract_spoken_dialogues(llm_result):
    """Return exact spoken text from a formatted segment result."""
    if not isinstance(llm_result, dict):
        return []
    description = llm_result.get("detailed_description")
    if description is None:
        description = llm_result.get("detailed_description", "")
    dialogues = []
    for match in _DIALOGUE_BLOCK_PATTERN.finditer(str(description or "")):
        dialogue = _DIALOGUE_LANGUAGE_TAG_PATTERN.sub(
            "",
            match.group("dialogue"),
            count=1,
        )
        dialogue = " ".join(dialogue.split()).strip()
        if dialogue:
            dialogues.append(dialogue)
    return dialogues


def normalize_dialogue_for_comparison(value):
    """Normalize inconsequential differences when checking dialogue reuse."""
    normalized = " ".join(str(value or "").split()).strip().casefold()
    return normalized.rstrip(" .!?\u2026")


def find_repeated_dialogues(llm_result, dialogue_exclusions):
    excluded = {
        normalize_dialogue_for_comparison(value)
        for value in (dialogue_exclusions or [])
        if normalize_dialogue_for_comparison(value)
    }
    return [
        dialogue
        for dialogue in extract_spoken_dialogues(llm_result)
        if normalize_dialogue_for_comparison(dialogue) in excluded
    ]


def collect_recent_dialogues(
    segment_records,
    max_segments=DIALOGUE_HISTORY_SEGMENTS_MAX,
):
    """Flatten dialogue from the latest completed segment window.

    The window is based on segments rather than the number of spoken lines, so
    silent segments still age older dialogue out of the exclusion list.
    """
    records = list(segment_records or [])[-max_segments:]
    dialogues = []
    for record in records:
        if not isinstance(record, dict):
            continue
        record_dialogues = record.get("dialogues")
        if not isinstance(record_dialogues, list):
            record_dialogues = extract_spoken_dialogues(record.get("llm_result"))
            record["dialogues"] = record_dialogues
        dialogues.extend(
            " ".join(value.split()).strip()
            for value in record_dialogues
            if isinstance(value, str) and value.strip()
        )
    return dialogues


def new_generation_state(run_config):
    return {
        "version": 1,
        "config": dict(run_config),
        "segments": [],
        "recent_dialogues": [],
        # Continuity sources are preserved separately for debugging.
        # continuity_prompt_state is the combined call's prompt-derived
        # prediction. continuity_state is the authoritative merged state after
        # visible rendered facts have overlaid that prediction.
        "continuity_prompt_state": {},
        "continuity_state": {
            "version": CONTINUITY_STATE_VERSION,
        },
        "continuity_opening_state": "",
        "continuity_summary": "",
        # Visual observer output records what the rendered pixels actually show.
        "visual_raw_end_state": {},
        "visual_end_state": {},
        "visual_end_frame_paths": [],
        "subject_registry_state": new_continuity_state(),
        "continuity_summary_pending": False,
        "beat_progress": {
            "completed_beat_ids": [],
            "last_segment_number": None,
            "newly_completed_beat_ids": [],
        },
    }


def load_generation_state(path=GENERATION_STATE_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Cannot resume because the generation checkpoint is missing: {path}"
        ) from None
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Generation checkpoint is invalid JSON: {path} "
            f"(line {e.lineno}, column {e.colno})"
        ) from e

    if not isinstance(state, dict):
        raise RuntimeError("Generation checkpoint must contain a JSON object.")
    return state


def wait_for_resume_checkpoint(
    state,
    resume_segment,
    path=GENERATION_STATE_FILE,
    timeout=RESUME_CHECKPOINT_WAIT_SECONDS,
    poll_interval=RESUME_CHECKPOINT_POLL_SECONDS,
):
    """Reload a checkpoint while the immediately preceding segment commits.

    ComfyUI writes the video before the main thread can validate its path and
    atomically append the completed-segment record.  A resume process started
    in that small window used to reject a valid ``--resume N`` request after a
    single stale read.  Only wait when exactly that final required record is
    missing; older or more severely incomplete checkpoints still fail fast.
    """

    required_count = resume_segment - 1
    records = state.get("segments")
    if (
        not isinstance(records, list)
        or len(records) != required_count - 1
        or timeout <= 0
    ):
        return state

    print(
        f"Checkpoint currently has {len(records)}/{required_count} required "
        f"segment records; waiting up to {timeout:g} seconds for segment "
        f"{required_count} to finish committing.",
        flush=True,
    )
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return state
        time.sleep(min(poll_interval, remaining))
        reloaded = load_generation_state(path)
        reloaded_records = reloaded.get("segments")
        if (
            isinstance(reloaded_records, list)
            and len(reloaded_records) >= required_count
        ):
            print(
                f"Segment {required_count} checkpoint commit detected; "
                "continuing resume.",
                flush=True,
            )
            return reloaded
        state = reloaded


def save_generation_state(state, path=GENERATION_STATE_FILE):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".generation_state_",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def find_repair_segment_video(records, segment_number):
    """Return the newest generated clip for a segment missing from checkpoint."""

    directories = []
    for record in records:
        if not isinstance(record, dict):
            continue
        video_path = record.get("video_path")
        if isinstance(video_path, str) and video_path:
            directory = os.path.dirname(os.path.abspath(video_path))
            if directory not in directories:
                directories.append(directory)
    if VIDEO_OUTPUT not in directories:
        directories.append(VIDEO_OUTPUT)

    prefix = f"segment_{segment_number:04d}"
    candidates = []
    for directory in directories:
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            for entry in entries:
                if (
                    entry.is_file()
                    and entry.name.lower().endswith(".mp4")
                    and entry.name.startswith(prefix)
                    and entry.name[len(prefix):].startswith(("_", "."))
                ):
                    try:
                        stat = entry.stat()
                    except OSError:
                        continue
                    if stat.st_size > 0:
                        candidates.append((stat.st_mtime_ns, entry.path))
    if not candidates:
        return None
    return os.path.abspath(max(candidates)[1])


def validate_repair_checkpoint(state, segment_number):
    """Validate and return the checkpoint records needed for an isolated repair."""

    if not isinstance(segment_number, int) or isinstance(segment_number, bool):
        raise ValueError("--repair must identify an integer segment number.")
    if not isinstance(state, dict):
        raise RuntimeError("Generation checkpoint must contain a JSON object.")
    if state.get("version") != 1:
        raise RuntimeError("Generation checkpoint version is unsupported for repair.")
    records = state.get("segments")
    if not isinstance(records, list):
        raise RuntimeError("Generation checkpoint has no valid segment records.")
    config = state.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("Generation checkpoint has no saved run configuration.")
    try:
        raw_total_segments = config["total_segments"]
        if isinstance(raw_total_segments, bool):
            raise ValueError
        total_segments = int(raw_total_segments)
        if float(raw_total_segments) != total_segments or total_segments <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise RuntimeError(
            "Generation checkpoint has no valid total_segments setting."
        ) from error
    if segment_number < 2:
        raise ValueError("Repair requires a middle segment; Segment 1 has no prior neighbor.")
    if segment_number >= total_segments:
        raise ValueError(
            f"Repair requires both neighbors; segment {segment_number} must be less "
            f"than the final segment {total_segments}."
        )

    required = {}
    checkpointed_segments = set()
    for required_segment in (
        segment_number - 1,
        segment_number,
        segment_number + 1,
    ):
        record_index = required_segment - 1
        if record_index >= len(records):
            print(
                f"WARNING: checkpoint record for segment {required_segment} is "
                "missing; continuing repair using the generated video artifact.",
                flush=True,
            )
            record = {
                "segment_number": required_segment,
                "video_path": find_repair_segment_video(
                    records,
                    required_segment,
                ),
            }
        else:
            record = records[record_index]
            if (
                not isinstance(record, dict)
                or record.get("segment_number") != required_segment
            ):
                raise RuntimeError(
                    f"Cannot repair segment {segment_number}: checkpoint record for "
                    f"segment {required_segment} is missing or out of order."
                )
            checkpointed_segments.add(required_segment)
        video_path = record.get("video_path")
        if (
            not isinstance(video_path, str)
            or not os.path.isfile(video_path)
            or os.path.getsize(video_path) == 0
        ):
            raise RuntimeError(
                f"Cannot repair segment {segment_number}: video for segment "
                f"{required_segment} is missing or empty: {video_path!r}"
            )
        required[required_segment] = record

    previous_record = required[segment_number - 1]
    target_record = required[segment_number]
    if (
        segment_number in checkpointed_segments
        and not isinstance(target_record.get("llm_result"), dict)
    ):
        raise RuntimeError(
            f"Cannot repair segment {segment_number}: its saved Director result "
            "is missing."
        )
    if segment_number - 1 not in checkpointed_segments:
        context_record = next(
            (
                record
                for record in reversed(records)
                if (
                    isinstance(record, dict)
                    and isinstance(record.get("llm_result"), dict)
                    and isinstance(record.get("segment_number"), int)
                    and record["segment_number"] < segment_number
                )
            ),
            None,
        )
        if context_record is not None:
            previous_record["llm_result"] = copy.deepcopy(
                context_record["llm_result"]
            )
            if isinstance(context_record.get("continuity_state"), dict):
                previous_record["continuity_state"] = copy.deepcopy(
                    context_record["continuity_state"]
                )
            if isinstance(context_record.get("subject_registry_state"), dict):
                previous_record["subject_registry_state"] = copy.deepcopy(
                    context_record["subject_registry_state"]
                )
            if context_record.get("continuity_opening_state"):
                previous_record["continuity_opening_state"] = str(
                    context_record["continuity_opening_state"]
                )
        if not isinstance(previous_record.get("llm_result"), dict):
            previous_record["llm_result"] = {}
        if not isinstance(previous_record.get("subject_registry_state"), dict):
            fallback_registry = state.get("subject_registry_state")
            legacy = previous_record.get("continuity_state")
            previous_record["subject_registry_state"] = copy.deepcopy(
                fallback_registry
                if isinstance(fallback_registry, dict)
                else (
                    legacy
                    if isinstance(legacy, dict) and "subjects" in legacy
                    else new_continuity_state()
                )
            )
    if not isinstance(previous_record.get("subject_registry_state"), dict):
        legacy = previous_record.get("continuity_state")
        if isinstance(legacy, dict) and "subjects" in legacy:
            previous_record["subject_registry_state"] = copy.deepcopy(legacy)
        else:
            raise RuntimeError(
                f"Cannot repair segment {segment_number}: segment "
                f"{segment_number - 1} has no committed Subject registry state."
            )
    return {
        "records": records,
        "config": config,
        "total_segments": total_segments,
        "previous_record": previous_record,
        "target_record": target_record,
        "next_record": required[segment_number + 1],
        "target_record_checkpointed": segment_number in checkpointed_segments,
    }


def get_repair_render_settings(checkpoint_config, segment_number):
    """Derive repair duration and resolution from the original run settings."""

    try:
        segment_length = float(checkpoint_config["segment_length"])
        total_length = float(checkpoint_config["total_length"])
        megapixels = float(checkpoint_config["megapixels"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Generation checkpoint has invalid repair render settings."
        ) from error
    if (
        not all(math.isfinite(value) for value in (
            segment_length,
            total_length,
            megapixels,
        ))
        or segment_length <= 0
        or total_length <= 0
        or megapixels <= 0
    ):
        raise RuntimeError(
            "Generation checkpoint repair render settings must be positive."
        )
    duration = min(
        segment_length,
        total_length - (segment_number - 1) * segment_length,
    )
    if duration <= 0:
        raise RuntimeError(
            f"Generation checkpoint has no positive duration for segment "
            f"{segment_number}."
        )
    return duration, megapixels


def restore_generation_state(
    resume_segment,
    beats,
    path=GENERATION_STATE_FILE,
    base_subject_definitions="",
    checkpoint_wait_timeout=None,
    checkpoint_poll_interval=RESUME_CHECKPOINT_POLL_SECONDS,
):
    state = load_generation_state(path)
    if state.get("version") != 1:
        raise RuntimeError(
            "Generation checkpoint version is unsupported; start at segment 1."
        )
    records = state.get("segments")
    if not isinstance(records, list):
        raise RuntimeError("Generation checkpoint has no valid segment records.")

    required_count = resume_segment - 1
    if checkpoint_wait_timeout is None:
        checkpoint_wait_timeout = (
            RESUME_CHECKPOINT_WAIT_SECONDS
            if os.path.abspath(path) == os.path.abspath(GENERATION_STATE_FILE)
            else 0
        )
    state = wait_for_resume_checkpoint(
        state,
        resume_segment,
        path,
        timeout=checkpoint_wait_timeout,
        poll_interval=checkpoint_poll_interval,
    )
    if state.get("version") != 1:
        raise RuntimeError(
            "Generation checkpoint version is unsupported; start at segment 1."
        )
    records = state.get("segments")
    if not isinstance(records, list):
        raise RuntimeError("Generation checkpoint has no valid segment records.")
    if len(records) < required_count:
        raise RuntimeError(
            f"Cannot resume at segment {resume_segment}: checkpoint contains "
            f"only {len(records)} completed segment(s)."
        )

    restored_records = []
    video_paths = []
    recent_results = []
    completed_beat_ids = set()
    latent_path = None
    for expected_segment, record in enumerate(
        records[:required_count],
        start=1,
    ):
        if (
            not isinstance(record, dict)
            or record.get("segment_number") != expected_segment
        ):
            raise RuntimeError(
                "Generation checkpoint segment records are missing or out of order."
            )
        latent_path = get_h3_latent_path(expected_segment)

        if not os.path.isfile(latent_path):
            raise RuntimeError(
                f"Cannot resume: H3 AV latent for segment "
                f"{expected_segment} is missing: {latent_path}"
            )
        video_path = record.get("video_path")
        if not isinstance(video_path, str) or not os.path.isfile(video_path):
            raise RuntimeError(
                f"Cannot resume: video for segment {expected_segment} is "
                f"missing: {video_path!r}"
            )
        llm_result = record.get("llm_result")
        if not isinstance(llm_result, dict):
            raise RuntimeError(
                f"Cannot resume: segment {expected_segment} has no saved "
                "formatted director result."
            )
        record = copy.deepcopy(record)
        record.pop("additional_subject_definitions", None)
        restored_records.append(record)
        video_paths.append(video_path)
        recent_results.append((expected_segment, llm_result))
        completed_beat_ids = normalize_completed_beat_ids(
            beats,
            record.get("completed_beat_ids", []),
        )

    state["segments"] = restored_records
    state["recent_dialogues"] = collect_recent_dialogues(restored_records)
    if restored_records:
        state["beat_progress"] = {
            "completed_beat_ids": sorted(completed_beat_ids),
            "last_segment_number": restored_records[-1].get("segment_number"),
            "newly_completed_beat_ids": [],
        }
    else:
        state["beat_progress"] = {
            "completed_beat_ids": [],
            "last_segment_number": None,
            "newly_completed_beat_ids": [],
        }
    if restored_records:
        last_record = restored_records[-1]
        reduced_state = copy.deepcopy(last_record.get("continuity_state", {}))
        prompt_state = copy.deepcopy(
            last_record.get("continuity_prompt_state", reduced_state)
        )
        opening_state_text = str(
            last_record.get(
                "continuity_opening_state",
                last_record.get("continuity_summary", ""),
            )
            or ""
        ).strip()
        registry_state = last_record.get("subject_registry_state")
        if not isinstance(registry_state, dict):
            # Backward compatibility for checkpoints created before the
            # two-phase continuity pipeline separated semantic continuity
            # from the internal Subject registry.
            legacy = last_record.get("continuity_state")
            registry_state = (
                legacy
                if isinstance(legacy, dict) and "subjects" in legacy
                else state.get("subject_registry_state", new_continuity_state())
            )
        registry_state = migrate_continuity_state(registry_state)
        if not opening_state_text and registry_state.get("subjects"):
            opening_state_text = format_director_opening_state(
                registry_state,
                base_subject_definitions,
            )
        state["continuity_prompt_state"] = prompt_state
        state["continuity_state"] = reduced_state
        state["continuity_opening_state"] = opening_state_text
        state["continuity_summary"] = opening_state_text
        state["subject_registry_state"] = registry_state
        state["continuity_summary_pending"] = bool(
            last_record.get("continuity_summary_pending", False)
        )
    else:
        state["continuity_prompt_state"] = {}
        state["continuity_state"] = {}
        state["continuity_opening_state"] = ""
        state["continuity_summary"] = ""
        state["subject_registry_state"] = new_continuity_state()
        state["continuity_summary_pending"] = False
    state.pop("additional_subject_definitions", None)
    restored_dynamic_subject_definitions = derive_additional_subject_definitions(
        base_subject_definitions,
        state.get("subject_registry_state"),
    )
    return {
        "state": state,
        "video_paths": video_paths,
        "latent_path": latent_path,
        "previous_video_path": video_paths[-1] if video_paths else None,
        "recent_results": recent_results[-RECENT_SEGMENTS_MAX:],
        "completed_beat_ids": completed_beat_ids,
        "continuity_summary": state.get("continuity_summary", ""),
        "continuity_opening_state": state.get("continuity_opening_state", ""),
        "continuity_prompt_state": copy.deepcopy(
            state.get("continuity_prompt_state", state.get("continuity_state", {}))
        ),
        "continuity_state": copy.deepcopy(state.get("continuity_state", {})),
        "subject_registry_state": migrate_continuity_state(
            state.get("subject_registry_state")
        ),
        "continuity_summary_pending": state.get(
            "continuity_summary_pending", False
        ),
        "additional_subject_definitions": restored_dynamic_subject_definitions,
        "recent_dialogues": list(state.get("recent_dialogues", [])),
    }


def record_completed_segment(
    state,
    segment_number,
    video_path,
    llm_result,
    completed_beat_ids,
    continuity_summary="",
    continuity_state=None,
    continuity_summary_pending=False,
    additional_subject_definitions=None,
    continuity_opening_state="",
    subject_registry_state=None,
):
    records = state.setdefault("segments", [])
    if continuity_state is None:
        continuity_state = state.get("continuity_state", {})
    if not continuity_opening_state:
        continuity_opening_state = continuity_summary or state.get(
            "continuity_opening_state", ""
        )
    if subject_registry_state is None:
        subject_registry_state = state.get(
            "subject_registry_state",
            new_continuity_state(),
        )
    del additional_subject_definitions
    expected_segment = len(records) + 1
    if segment_number != expected_segment:
        raise RuntimeError(
            f"Cannot checkpoint segment {segment_number}; expected segment "
            f"{expected_segment}."
        )
    record = {
        "segment_number": segment_number,
        "video_path": os.path.abspath(video_path),
        "llm_result": llm_result,
        "dialogues": extract_spoken_dialogues(llm_result),
        "completed_beat_ids": sorted(completed_beat_ids),
        "continuity_summary": continuity_opening_state,
        "continuity_state": copy.deepcopy(continuity_state),
        "continuity_opening_state": continuity_opening_state,
        "subject_registry_state": migrate_continuity_state(subject_registry_state),
        "continuity_summary_pending": bool(continuity_summary_pending),
    }
    records.append(record)
    state["recent_dialogues"] = collect_recent_dialogues(records)
    state["beat_progress"] = {
        "completed_beat_ids": sorted(completed_beat_ids),
        "last_segment_number": segment_number,
        "newly_completed_beat_ids": [],
    }
    state["continuity_summary"] = continuity_opening_state
    state["continuity_state"] = copy.deepcopy(continuity_state)
    state["continuity_opening_state"] = continuity_opening_state
    state["subject_registry_state"] = migrate_continuity_state(
        subject_registry_state
    )
    state["continuity_summary_pending"] = bool(
        continuity_summary_pending
    )
    return record


def find_workflow_node(workflow, node_name, workflow_label, expected_class_type=None):
    matches = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        meta = node.get("_meta", {})
        if isinstance(meta, dict) and meta.get("title") == node_name:
            matches.append((node_id, node))

    if not matches:
        raise RuntimeError(
            f"{workflow_label} is missing the ComfyUI node named '{node_name}'."
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"{workflow_label} contains multiple nodes named '{node_name}'."
        )

    node_id, node = matches[0]
    if expected_class_type and node.get("class_type") != expected_class_type:
        raise RuntimeError(
            f"Node '{node_name}' has type '{node.get('class_type')}', "
            f"expected '{expected_class_type}'."
        )
    if not isinstance(node.get("inputs"), dict):
        raise RuntimeError(f"Node '{node_name}' has no valid inputs object.")

    return node_id, node


def set_node_input(
    workflow,
    node_name,
    input_name,
    value,
    workflow_label,
    expected_class_type=None
):
    _, node = find_workflow_node(
        workflow,
        node_name,
        workflow_label,
        expected_class_type
    )
    if input_name not in node["inputs"]:
        raise RuntimeError(
            f"Node '{node_name}' in {workflow_label} is missing input '{input_name}'."
        )
    node["inputs"][input_name] = value


def validate_named_connection(
    workflow,
    destination_name,
    input_name,
    source_name,
    output_index,
    workflow_label
):
    source_id, _ = find_workflow_node(
        workflow,
        source_name,
        workflow_label
    )
    _, destination = find_workflow_node(
        workflow,
        destination_name,
        workflow_label
    )
    connection = destination["inputs"].get(input_name)

    if (
        not isinstance(connection, list)
        or len(connection) != 2
        or str(connection[0]) != str(source_id)
        or connection[1] != output_index
    ):
        raise RuntimeError(
            f"'{input_name}' on '{destination_name}' must connect to "
            f"output {output_index} of '{source_name}' in {workflow_label}."
        )


def validate_workflow(workflow, workflow_label, is_append=False):
    required = (
        (DURATION_NODE_NAME, "PrimitiveFloat"),
        (PROMPT_NODE_NAME, "DPRandomGenerator"),
        (NOISE_NODE_NAME, "RandomNoise"),
        (SAVE_VIDEO_NODE_NAME, "SaveVideo")
    )
    for name, class_type in required:
        find_workflow_node(workflow, name, workflow_label, class_type)
    _, lora_node = find_workflow_node(
        workflow,
        LORA_NODE_NAME,
        workflow_label,
        "LoraLoaderModelOnly",
    )
    for input_name in ("lora_name", "strength_model"):
        if input_name not in lora_node["inputs"]:
            raise RuntimeError(
                f"Node '{LORA_NODE_NAME}' in {workflow_label} is missing "
                f"input '{input_name}'."
            )

    if not is_append:
        find_workflow_node(
            workflow,
            RESOLUTION_NODE_NAME,
            workflow_label,
            "ResolutionSelector"
        )
        return

    find_workflow_node(
        workflow,
        IMAGE_BATCH_NODE_NAME,
        workflow_label,
        "ImageBatchMulti"
    )
    find_workflow_node(
        workflow,
        LOAD_VIDEO_NODE_NAME,
        workflow_label,
        "VHS_LoadVideoPath"
    )

    required_connections = (
        (
            MATH_NODE_NAME,
            "values.a",
            DURATION_NODE_NAME,
            0,
        ),
        (
            VIDEO_EXTEND_NODE_NAME,
            "length",
            MATH_NODE_NAME,
            1,
        ),
        (
            VIDEO_EXTEND_NODE_NAME,
            "prompt",
            PROMPT_NODE_NAME,
            0,
        ),

        # NEW: direct previous sampler AV latent
        (
            VIDEO_EXTEND_NODE_NAME,
            "context_latent",
            H3_LATENT_LOAD_NODE_NAME,
            0,
        ),

        (
            VIDEO_EXTEND_NODE_NAME,
            "ref_images",
            IMAGE_BATCH_NODE_NAME,
            0,
        ),

        (
            "Basic Guider",
            "conditioning",
            VIDEO_EXTEND_NODE_NAME,
            0,
        ),
        (
            "SamplerCustomAdvanced",
            "latent_image",
            VIDEO_EXTEND_NODE_NAME,
            1,
        ),

        # NEW: persist this segment's pristine AV latent
        (
            H3_LATENT_SAVE_NODE_NAME,
            "latent",
            "SamplerCustomAdvanced",
            0,
        ),

        (
            "Create Video",
            "images",
            "VAE Decode",
            0,
        ),
        (
            "Create Video",
            "audio",
            "VAE Decode Audio",
            0,
        ),
        (
            SAVE_VIDEO_NODE_NAME,
            "video",
            "Create Video",
            0,
        ),
    )

    for args in required_connections:
        validate_named_connection(
            workflow,
            *args,
            workflow_label=workflow_label
        )


def validate_refresh_workflow(workflow, workflow_label):
    """Validate the refresh graph, including its frame and reference inputs."""

    validate_workflow(workflow, workflow_label, is_append=False)
    find_workflow_node(
        workflow,
        REFRESH_FIRST_FRAME_NODE_NAME,
        workflow_label,
        "LoadImage",
    )
    find_workflow_node(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        workflow_label,
        "MiniMaxH3HybridRefAndKeyframe",
    )
    validate_named_connection(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        "first_frame",
        REFRESH_FIRST_FRAME_NODE_NAME,
        0,
        workflow_label,
    )
    validate_named_connection(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "latent",
        "SamplerCustomAdvanced",
        0,
        workflow_label,
    )


def normalize_lora_list(loras):
    normalized = []
    for lora in loras or ():
        if not isinstance(lora, (list, tuple)) or len(lora) != 2:
            raise ValueError(
                f"Invalid LoRA {lora!r}; expected (lora_name, strength)."
            )
        name = str(lora[0]).strip()
        if not name or re.search(r"[\s:]", name):
            raise ValueError(f"Invalid LoRA name: {lora[0]!r}.")
        try:
            strength = float(lora[1])
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid LoRA strength: {lora[1]!r}.") from error
        if not math.isfinite(strength):
            raise ValueError(f"LoRA strength must be finite: {lora[1]!r}.")
        normalized.append((name, strength))
    return normalized


def configure_lora_chain(workflow, loras, workflow_label):
    """Replace the workflow's placeholder with an exact ordered LoRA chain."""
    loras = normalize_lora_list(loras)
    placeholder_id, placeholder = find_workflow_node(
        workflow,
        LORA_NODE_NAME,
        workflow_label,
        "LoraLoaderModelOnly",
    )
    source_connection = placeholder.get("inputs", {}).get("model")
    if (
        not isinstance(source_connection, list)
        or len(source_connection) != 2
        or source_connection[1] != 0
        or str(source_connection[0]) not in {str(node_id) for node_id in workflow}
    ):
        raise RuntimeError(
            f"Node '{LORA_NODE_NAME}' in {workflow_label} must have a model "
            "input connected to output 0 of its upstream model node."
        )

    consumers = []
    for node_id, node in workflow.items():
        if str(node_id) == str(placeholder_id):
            continue
        for input_name, value in node.get("inputs", {}).items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and str(value[0]) == str(placeholder_id)
                and value[1] == 0
            ):
                consumers.append((node, input_name))
    if not consumers:
        raise RuntimeError(
            f"Node '{LORA_NODE_NAME}' in {workflow_label} has no model consumers."
        )

    if not loras:
        for consumer, input_name in consumers:
            consumer["inputs"][input_name] = copy.deepcopy(source_connection)
        del workflow[placeholder_id]
        return workflow

    placeholder_template = copy.deepcopy(placeholder)
    placeholder["inputs"]["lora_name"] = loras[0][0]
    placeholder["inputs"]["strength_model"] = loras[0][1]
    last_lora_id = str(placeholder_id)
    numeric_ids = []
    for node_id in workflow:
        try:
            numeric_ids.append(int(node_id))
        except (TypeError, ValueError):
            continue
    if not numeric_ids:
        raise RuntimeError(f"{workflow_label} contains no numeric ComfyUI node IDs.")
    next_node_id = max(numeric_ids) + 1

    for lora_number, (lora_name, strength) in enumerate(loras[1:], start=2):
        while str(next_node_id) in workflow:
            next_node_id += 1
        node_id = str(next_node_id)
        next_node_id += 1
        node = copy.deepcopy(placeholder_template)
        node["inputs"]["model"] = [last_lora_id, 0]
        node["inputs"]["lora_name"] = lora_name
        node["inputs"]["strength_model"] = strength
        node.setdefault("_meta", {})["title"] = f"{LORA_NODE_NAME} {lora_number}"
        workflow[node_id] = node
        last_lora_id = node_id

    for consumer, input_name in consumers:
        consumer["inputs"][input_name] = [last_lora_id, 0]
    return workflow


# ============================================================
# BEATS
# ============================================================

LORA_SPEC_PATTERN = re.compile(
    r"(?P<name>[^\s:]+):(?P<strength>[^\s:]+)",
    re.IGNORECASE,
)
LORA_SUFFIX_PATTERN = re.compile(
    r"\s+--lora\s+(?P<spec>[^\s]+)",
    re.IGNORECASE,
)
LORA_DIRECTIVE_PATTERN = re.compile(
    r"^--lora\s+(?P<spec>[^\s]+)$",
    re.IGNORECASE,
)
PHASE_DIRECTIVE_PATTERN = re.compile(
    r"^#\s*phase\s+(?P<number>\d+)\s*$",
    re.IGNORECASE,
)
BEAT_NUMBER_PATTERN = re.compile(
    r"^(?P<number>\d+)\.\s+(?P<text>.+)$",
)


class BeatDefinition(str):
    def __new__(
        cls,
        text,
        loras=None,
        phase_number=None,
        phase_start=False,
    ):
        beat = super().__new__(cls, text)
        beat.loras = tuple(loras or ())
        beat.phase_number = (
            int(phase_number) if str(phase_number or "").isdigit() else None
        )
        beat.phase_start = bool(phase_start)
        # Retain the old scalar attributes for callers that inspect beats made
        # with exactly one LoRA. New code should use ``beat.loras``.
        beat.lora_name = beat.loras[0][0] if len(beat.loras) == 1 else None
        beat.strength_model = beat.loras[0][1] if len(beat.loras) == 1 else None
        return beat

    @property
    def lora_override(self):
        if len(self.loras) != 1:
            return None
        return self.loras[0]


def parse_lora_spec(raw_spec):
    spec = str(raw_spec or "").strip()
    match = LORA_SPEC_PATTERN.fullmatch(spec)
    if match is None:
        raise argparse.ArgumentTypeError(
            f"Invalid LoRA {raw_spec!r}; expected [lora_name]:[strength]."
        )
    try:
        strength = float(match.group("strength"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid LoRA strength in {raw_spec!r}."
        ) from error
    if not math.isfinite(strength):
        raise argparse.ArgumentTypeError(
            f"LoRA strength must be finite in {raw_spec!r}."
        )
    return match.group("name"), strength


def parse_beat_definition(line):
    first_match = LORA_SUFFIX_PATTERN.search(line)
    if first_match is None:
        if "--lora" in line.lower():
            raise ValueError(
                f"Invalid LoRA option in beat: {line!r}. Expected "
                "one or more --lora [lora_name]:[strength] options at the end."
            )
        return BeatDefinition(line)

    text = line[:first_match.start()].rstrip()
    if not text:
        raise ValueError(f"Beat text cannot be empty: {line!r}.")
    loras = []
    position = first_match.start()
    while position < len(line):
        if not line[position:].strip():
            break
        match = LORA_SUFFIX_PATTERN.match(line, position)
        if match is None:
            raise ValueError(
                f"Invalid LoRA option in beat: {line!r}. Expected "
                "one or more --lora [lora_name]:[strength] options at the end."
            )
        try:
            loras.append(parse_lora_spec(match.group("spec")))
        except argparse.ArgumentTypeError as error:
            raise ValueError(f"Invalid LoRA option in beat: {line!r}. {error}") from error
        position = match.end()
    return BeatDefinition(text, loras)


def parse_beats_content(raw):
    beats = []
    global_lora = None
    global_lora_directive = ""
    current_phase = None
    pending_phase_start = False
    for line in raw.splitlines():
        beat = line.strip()
        if not beat:
            continue
        phase_match = PHASE_DIRECTIVE_PATTERN.fullmatch(beat)
        if phase_match is not None:
            phase_number = int(phase_match.group("number"))
            if phase_number <= 0:
                raise ValueError("Beat phases must use positive one-based numbers.")
            if current_phase is not None and phase_number != current_phase + 1:
                raise ValueError("Beat phase markers must be consecutive and ordered.")
            current_phase = phase_number
            pending_phase_start = True
            continue
        if beat.startswith("#"):
            continue

        directive_match = LORA_DIRECTIVE_PATTERN.fullmatch(beat)
        if directive_match is not None:
            if global_lora is not None:
                raise ValueError(
                    "beats.txt may contain only one file-level --lora directive."
                )
            try:
                global_lora = parse_lora_spec(directive_match.group("spec"))
            except argparse.ArgumentTypeError as error:
                raise ValueError(
                    f"Invalid file-level LoRA directive: {beat!r}. {error}"
                ) from error
            global_lora_directive = beat
            continue
        number_match = BEAT_NUMBER_PATTERN.fullmatch(beat)
        if number_match is not None:
            beat_number = int(number_match.group("number"))
            expected_number = len(beats) + 1
            if beat_number != expected_number:
                raise ValueError(
                    "Numbered beats must be consecutive and ordered; "
                    f"expected beat {expected_number}, found {beat_number}."
                )
            beat = number_match.group("text").strip()
        parsed = parse_beat_definition(beat)
        beats.append(BeatDefinition(
            str(parsed),
            parsed.loras,
            phase_number=current_phase,
            phase_start=pending_phase_start,
        ))
        pending_phase_start = False

    if global_lora is not None:
        beats = [
            BeatDefinition(
                str(beat),
                (global_lora, *beat.loras),
                phase_number=beat.phase_number,
                phase_start=beat.phase_start,
            )
            for beat in beats
        ]
    return beats, global_lora_directive


def load_beats(path):
    raw = load_text_file(path, required=True)
    beats, _ = parse_beats_content(raw)
    return beats


def beat_loras(beats, beat_id, global_loras=()):
    merged = list(global_loras or ())
    try:
        beat_id = int(beat_id)
    except (TypeError, ValueError):
        return merged
    if beat_id <= 0 or beat_id > len(beats):
        return merged
    merged.extend(getattr(beats[beat_id - 1], "loras", ()))
    return merged


def serialize_beats(beats):
    return [
        {
            "text": str(beat),
            "loras": [list(lora) for lora in getattr(beat, "loras", ())],
            "phase_number": getattr(beat, "phase_number", None),
            "phase_start": bool(getattr(beat, "phase_start", False)),
        }
        for beat in beats or []
    ]


def is_new_phase_start(beats, beat_id):
    """Return whether this beat begins a phase after the opening phase."""
    try:
        beat_id = int(beat_id)
    except (TypeError, ValueError):
        return False
    if beat_id <= 0 or beat_id > len(beats or ()):
        return False
    beat = beats[beat_id - 1]
    phase_number = getattr(beat, "phase_number", None)
    return bool(
        getattr(beat, "phase_start", False)
        and isinstance(phase_number, int)
        and phase_number > 1
    )


def normalize_completed_beat_ids(beats, completed_beat_ids):
    valid = set()
    for raw_id in completed_beat_ids or []:
        if isinstance(raw_id, bool):
            continue
        try:
            beat_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if 1 <= beat_id <= len(beats):
            valid.add(beat_id)

    contiguous = set()
    beat_id = 1
    while beat_id in valid:
        contiguous.add(beat_id)
        beat_id += 1
    return contiguous


def get_next_beat_id(beats, completed_beat_ids):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    next_id = len(completed) + 1
    return None if next_id > len(beats) else next_id


def build_bounded_beat_state(
    beats,
    completed_beat_ids,
    segment_number=None,
    lookahead=DEFAULT_BEAT_LOOKAHEAD,
):
    """Return the one-beat-per-segment window needed by the director."""
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    state = {
        "completed_through": len(completed) or None,
        "active_beat": None,
        "ordered_lookahead": [],
        "beats_completed": len(completed),
        "beats_remaining": max(0, len(beats) - len(completed)),
        "active_deadline_segment": None,
    }
    if not beats:
        return state
    if segment_number is None:
        active_id = get_next_beat_id(beats, completed)
    else:
        active_id = int(segment_number)
    if active_id is None or active_id < 1 or active_id > len(beats):
        return state

    state["active_beat"] = {
        "id": active_id,
        "text": beats[active_id - 1],
    }
    state["ordered_lookahead"] = [
        {"id": beat_id, "text": beats[beat_id - 1]}
        for beat_id in range(
            active_id + 1,
            min(len(beats), active_id + lookahead) + 1,
        )
    ]
    state["active_deadline_segment"] = active_id
    return state


def get_accepted_reported_beat_ids(
    beats,
    completed_beat_ids,
    reported_beat_ids
):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    next_id = get_next_beat_id(beats, completed)
    if next_id is None:
        return []
    reported = set()
    for raw_id in reported_beat_ids or []:
        if isinstance(raw_id, bool):
            continue
        try:
            beat_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if 1 <= beat_id <= len(beats):
            reported.add(beat_id)
    return [next_id] if next_id in reported else []


def get_last_checkpoint_beat_update(state, beats):
    records = state.get("segments", []) if isinstance(state, dict) else []
    if not records:
        return None, []

    last_record = records[-1]
    if not isinstance(last_record, dict):
        return None, []
    last_completed = normalize_completed_beat_ids(
        beats,
        last_record.get("completed_beat_ids", [])
    )
    previous_completed = set()
    if len(records) > 1 and isinstance(records[-2], dict):
        previous_completed = normalize_completed_beat_ids(
            beats,
            records[-2].get("completed_beat_ids", [])
        )
    return last_record.get("segment_number"), sorted(
        last_completed - previous_completed
    )


def print_minimax_beat_plan(beats, completed_beat_ids, reported_beat_ids):
    if not beats:
        return [], None

    accepted = get_accepted_reported_beat_ids(
        beats,
        completed_beat_ids,
        reported_beat_ids
    )
    projected_completed = set(
        normalize_completed_beat_ids(beats, completed_beat_ids)
    )
    projected_completed.update(accepted)
    next_id = get_next_beat_id(beats, projected_completed)

    print()
    print("=" * 64)
    print("MINIMAX H3 BEAT PLAN")
    print("=" * 64)
    print("Beat assigned to this prompt:")
    if accepted:
        for beat_id in accepted:
            print(f"  Beat {beat_id}: {beats[beat_id - 1]}")
    else:
        current_id = get_next_beat_id(beats, completed_beat_ids)
        print("  None reported complete by the formatted prompt.")
        if current_id is not None:
            print(f"  Still targeting Beat {current_id}: {beats[current_id - 1]}")
    print("Next required after this prompt:")
    if next_id is None:
        print("  All required beats would be complete.")
    else:
        print(f"  Beat {next_id}: {beats[next_id - 1]}")
    print("=" * 64)
    return accepted, next_id


def apply_reported_beat_completions(
    beats,
    completed_beat_ids,
    reported_beat_ids,
    segment_number
):
    """Apply the active beat only when the returned director result reports it."""
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    if not beats:
        return completed
    expected_id = int(segment_number)
    if not 1 <= expected_id <= len(beats):
        raise RuntimeError(
            f"Segment {segment_number} has no corresponding beat; "
            f"the run has {len(beats)} beats."
        )

    reported = set()
    for raw_id in reported_beat_ids or []:
        if isinstance(raw_id, bool):
            continue
        try:
            reported.add(int(raw_id))
        except (TypeError, ValueError):
            continue
    unexpected = sorted(
        beat_id for beat_id in reported
        if 1 <= beat_id <= len(beats) and beat_id != expected_id
    )
    if unexpected:
        print(
            "WARNING: Ignoring beat completion claim(s) not belonging to this "
            f"segment: {', '.join(str(x) for x in unexpected)}"
        )
    if expected_id not in reported:
        print(
            f"WARNING: Director did not confirm Beat {expected_id} complete for "
            f"Segment {segment_number}; treating the assigned beat as complete "
            "so generation can continue."
        )

    required_prior = set(range(1, expected_id))
    if completed != required_prior:
        raise RuntimeError(
            f"Beat progress is incompatible with Segment {segment_number}: "
            f"expected completed beats {sorted(required_prior)}, got "
            f"{sorted(completed)}. Start a fresh run or resume from a checkpoint "
            "created under the one-beat-per-segment contract."
        )
    completed.add(expected_id)
    print(f"Segment {segment_number} completed Beat {expected_id}.")
    return normalize_completed_beat_ids(beats, completed)


def get_beat_deadline_segment(beat_id):
    return max(1, int(beat_id))


# ============================================================
# LLM
# ============================================================

def parse_llm_json_content(content):
    if not isinstance(content, str):
        raise TypeError("LM Studio returned non-text message content.")

    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline != -1:
            candidate = candidate[first_newline + 1:-3].strip()

    def strip_trailing_commas(text):
        cleaned = []
        index = 0
        in_string = False
        escaped = False
        while index < len(text):
            char = text[index]
            if in_string:
                cleaned.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char in ('"', "'"):
                    in_string = False
                index += 1
                continue
            if char in ('"', "'"):
                in_string = True
                cleaned.append(char)
                index += 1
                continue
            if char == ",":
                next_index = index + 1
                while next_index < len(text) and text[next_index].isspace():
                    next_index += 1
                if next_index < len(text) and text[next_index] in "}]":
                    index += 1
                    continue
            cleaned.append(char)
            index += 1
        return "".join(cleaned)

    def find_json_segment(text):
        for start_index, start_char in enumerate(text):
            if start_char not in "[{":
                continue
            stack = []
            in_string = False
            escaped = False
            for index in range(start_index, len(text)):
                ch = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch in ('"', "'"):
                        in_string = False
                    continue
                if ch in ('"', "'"):
                    in_string = True
                    continue
                if ch in "[{":
                    stack.append(ch)
                elif ch in "]}":
                    if not stack:
                        return text[start_index:index + 1]
                    expect = "]" if stack[-1] == "[" else "}"
                    if ch == expect:
                        stack.pop()
                        if not stack:
                            return text[start_index:index + 1]
                    else:
                        return text[start_index:index + 1]
        return None

    candidates = [candidate, strip_trailing_commas(candidate)]
    for candidate_text in candidates:
        try:
            return json.loads(candidate_text)
        except json.JSONDecodeError:
            pass

    json_segment = find_json_segment(candidate)
    if json_segment is not None:
        normalized = strip_trailing_commas(json_segment)
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            pass

    last_error = None
    for candidate_text in candidates:
        json_segment = find_json_segment(candidate_text)
        if json_segment is not None:
            try:
                return json.loads(strip_trailing_commas(json_segment))
            except json.JSONDecodeError as error:
                last_error = error

    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("Invalid JSON", candidate, 0)


def raise_for_lm_studio_status(response):
    """Raise an HTTP error that preserves LM Studio's useful response body."""
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        body = str(getattr(response, "text", "") or "").strip()
        if len(body) > 2000:
            body = body[:2000] + "... [truncated]"
        detail = f"{error}"
        if body:
            detail += f"; LM Studio response: {body}"
        raise requests.HTTPError(
            detail,
            request=getattr(error, "request", None),
            response=response
        ) from error


def normalize_lm_studio_messages(messages):
    """Merge adjacent same-role turns before Ministral's strict Jinja template."""
    normalized = []
    for message in messages or []:
        if not isinstance(message, dict):
            raise TypeError("Each LM Studio message must be a dictionary.")
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", ""))
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Unsupported LM Studio message role: {role!r}")
        if role == "system" and normalized:
            raise ValueError("The LM Studio system message must be first.")
        if normalized and normalized[-1]["role"] == role:
            normalized[-1]["content"] += "\n\n" + content
        else:
            normalized.append({"role": role, "content": content})

    conversation = [
        message["role"]
        for message in normalized
        if message["role"] != "system"
    ]
    if any(
        role != ("user" if index % 2 == 0 else "assistant")
        for index, role in enumerate(conversation)
    ):
        raise ValueError(
            "LM Studio conversation roles must alternate user and assistant."
        )
    return normalized


def append_prompt_history(messages, path=PROMPT_HISTORY_FILE, metadata=None):
    """Append one outgoing LM Studio prompt to the debugging history file."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with PROMPT_HISTORY_LOCK:
        with open(path, "a", encoding="utf-8") as history_file:
            history_file.write("=" * 72 + "\n")
            history_file.write(
                json.dumps(
                    {
                        "metadata": {
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            **(metadata or {}),
                        },
                        "messages": messages,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            history_file.write("\n\n")


def reset_prompt_history(path=PROMPT_HISTORY_FILE):
    """Clear prompt history once before starting a brand-new generation run."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with PROMPT_HISTORY_LOCK:
        with open(path, "w", encoding="utf-8"):
            pass


def ask_llm(
    messages,
    max_retries=5,
    retry_delay=5,
    response_format=RESPONSE_FORMAT,
    history_metadata=None,
    temperature=0.35,
    top_p=None,
    presence_penalty=None,
    frequency_penalty=None,
    repeat_penalty=None,
    max_tokens=4000,
):
    last_error = None
    messages = normalize_lm_studio_messages(messages)
    beat_history_purposes = {
        "beat_arc_plan",
        "beat_arc_fidelity",
        "beat_generation",
        "beat_instruction_review",
        "beat_plan_audit",
        "beat_plan_repair",
        "beat_plan_verify",
    }
    response_history_purposes = beat_history_purposes | {
        "director_raw_scene",
        "director_h3_formatter",
        "continuity_combined_reduced_state",
        "continuity_phase_2_h3_opening",
    }
    history_purpose = str((history_metadata or {}).get("purpose", ""))
    log_beat_response = history_purpose in response_history_purposes
    retry_until_success = history_purpose in beat_history_purposes
    attempt = 0
    while retry_until_success or attempt < max_retries:
        attempt += 1
        try:
            llm_seed = generate_random_llm_seed()
            request_payload = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": int(max_tokens),
                "seed": llm_seed,
            }
            optional_sampling_parameters = {
                "top_p": top_p,
                "presence_penalty": presence_penalty,
                "frequency_penalty": frequency_penalty,
                "repeat_penalty": repeat_penalty,
            }
            request_payload.update(
                {
                    name: value
                    for name, value in optional_sampling_parameters.items()
                    if value is not None
                }
            )
            sampling_metadata = {
                name: request_payload[name]
                for name in (
                    "temperature",
                    "top_p",
                    "presence_penalty",
                    "frequency_penalty",
                    "repeat_penalty",
                )
                if name in request_payload
            }
            if response_format is not None:
                request_payload["response_format"] = response_format

            response_format_used = response_format is not None
            response_request_variant = None

            append_prompt_history(
                messages,
                metadata={
                    "response_format": response_format is not None,
                    **(history_metadata or {}),
                    "seed": llm_seed,
                    "sampling_parameters": sampling_metadata,
                    **({"entry_type": "request"} if log_beat_response else {}),
                },
            )
            response = requests.post(
                f"{LM_STUDIO_URL}/v1/chat/completions",
                json=request_payload,
                timeout=600
            )
            try:
                raise_for_lm_studio_status(response)
            except requests.HTTPError:
                # Some LM Studio/model combinations intermittently reject
                # OpenAI-compatible JSON Schema output. The deterministic
                # formatter can recover JSON or labeled plain text, so retry
                # this request once without only that optional constraint.
                if (
                    getattr(response, "status_code", None) == 400
                    and "response_format" in request_payload
                ):
                    print(
                        "LM Studio rejected structured response_format; "
                        "retrying once with Python-enforced formatting."
                    )
                    fallback_payload = dict(request_payload)
                    fallback_payload.pop("response_format")
                    response_format_used = False
                    response_request_variant = "without_response_format"
                    append_prompt_history(
                        fallback_payload["messages"],
                        metadata={
                            "response_format": False,
                            **(history_metadata or {}),
                            "request_variant": "without_response_format",
                            "seed": llm_seed,
                            "sampling_parameters": sampling_metadata,
                            **(
                                {"entry_type": "request"}
                                if log_beat_response else {}
                            ),
                        },
                    )
                    response = requests.post(
                        f"{LM_STUDIO_URL}/v1/chat/completions",
                        json=fallback_payload,
                        timeout=600
                    )
                    raise_for_lm_studio_status(response)
                else:
                    raise
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = str(choice.get("finish_reason") or "").strip().lower()
            if log_beat_response:
                response_metadata = {
                    "response_format": response_format_used,
                    **(history_metadata or {}),
                    "seed": llm_seed,
                    "sampling_parameters": sampling_metadata,
                    "finish_reason": finish_reason or None,
                    "entry_type": "response",
                }
                if response_request_variant:
                    response_metadata["request_variant"] = response_request_variant
                append_prompt_history(
                    [{"role": "assistant", "content": content}],
                    metadata=response_metadata,
                )
            if finish_reason in {"length", "max_tokens"}:
                raise ValueError(
                    "LM Studio truncated the response at the configured "
                    f"max_tokens={int(max_tokens)} before completion."
                )
            try:
                result = parse_llm_json_content(content)
            except json.JSONDecodeError:
                # The pure formatter can also recover plain labeled fields.
                # Preserve the response instead of spending a transport retry.
                result = content
            if (
                isinstance(result, dict)
                and set(result) == {"segment"}
                and isinstance(result["segment"], dict)
            ):
                # Without response_format, Ministral sometimes adds this
                # harmless wrapper despite being asked for the fields at the
                # top level. Unwrap it without changing any authored content.
                result = result["segment"]
            if not isinstance(result, (dict, str)):
                raise ValueError("LM Studio returned unsupported message content.")
            return result
        except (
            requests.RequestException,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError
        ) as e:
            last_error = e
            if retry_until_success:
                print(
                    f"LLM beat-creation request failed (attempt {attempt}); "
                    f"retrying until successful or Ctrl+Q: {e}"
                )
                time.sleep(retry_delay)
            else:
                print(
                    f"LLM request failed (attempt {attempt}/{max_retries}): {e}"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay)

    if retry_until_success:
        raise AssertionError("Unlimited beat-creation request loop exited.")

    raise RuntimeError(
        f"LM Studio failed after {max_retries} attempts. "
        f"Last error: {last_error}"
    ) from last_error


def estimate_text_tokens(text):
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)


def estimate_message_tokens(messages):
    def content_text(content):
        if isinstance(content, list):
            return "\n".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return str(content or "")

    return sum(
        estimate_text_tokens(content_text(message.get("content", ""))) + 12
        for message in messages
    )


# ============================================================
# STORY BEAT GENERATION
# ============================================================

def build_beats_response_format(total_segments, beat_start=1):
    if total_segments <= 0:
        raise ValueError("Beat generation requires at least one segment.")
    if (
        isinstance(beat_start, bool)
        or not isinstance(beat_start, int)
        or beat_start <= 0
    ):
        raise ValueError("Beat generation requires a positive beat_start.")
    beat_end = beat_start + total_segments - 1
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beats",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "beats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "beat_number": {
                                    "type": "integer",
                                    "minimum": beat_start,
                                    "maximum": beat_end,
                                },
                                "beat_text": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": (
                                        "One concise, complete sentence."
                                    ),
                                },
                            },
                            "required": ["beat_number", "beat_text"],
                            "additionalProperties": False,
                        },
                        "minItems": total_segments,
                        "maxItems": total_segments,
                        "uniqueItems": True,
                    },
                },
                "required": ["beats"],
                "additionalProperties": False,
            },
        },
    }


def build_beat_arc_response_format(total_segments):
    if total_segments <= 0:
        raise ValueError("Beat arc planning requires at least one segment.")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beat_arc",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "phases": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": total_segments,
                        "items": {
                            "type": "object",
                            "properties": {
                                "phase_number": {"type": "integer", "minimum": 1},
                                "beat_start": {"type": "integer", "minimum": 1},
                                "beat_end": {"type": "integer", "minimum": 1},
                                "narrative_purpose": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "broad_progression": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "required_end_state": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "characters_introduced": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1},
                                    "uniqueItems": True,
                                },
                                "location": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                            },
                            "required": [
                                "phase_number",
                                "beat_start",
                                "beat_end",
                                "narrative_purpose",
                                "broad_progression",
                                "characters_introduced",
                                "location",
                                "required_end_state",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["phases"],
                "additionalProperties": False,
            },
        },
    }


def build_beat_arc_fidelity_response_format():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beat_arc_fidelity",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "valid": {"type": "boolean"},
                    "issues": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["valid", "issues"],
                "additionalProperties": False,
            },
        },
    }


PERSISTENT_STATE_CONFLICT_ISSUE_TYPE = "persistent_state_conflict"

BEAT_PHASE_VALIDATION_ISSUE_TYPES = (
    "missing_end_state",
    "next_phase_scope_creep",
    "future_character",
    "future_location",
    "bad_opening_continuity",
    PERSISTENT_STATE_CONFLICT_ISSUE_TYPE,
)


def build_beat_phase_validation_response_format(beat_start=None, beat_end=None):
    beat_id_schema = {"type": "integer", "minimum": 1}
    if beat_start is not None:
        beat_start = int(beat_start)
        if beat_start <= 0:
            raise ValueError("Phase validation requires a positive beat_start.")
        beat_id_schema["minimum"] = beat_start
    if beat_end is not None:
        beat_end = int(beat_end)
        if beat_end < beat_id_schema["minimum"]:
            raise ValueError("Phase validation requires beat_end >= beat_start.")
        beat_id_schema["maximum"] = beat_end
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beat_phase_validation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "valid": {"type": "boolean"},
                    "issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "beat_id": beat_id_schema,
                                "type": {
                                    "type": "string",
                                    "enum": list(BEAT_PHASE_VALIDATION_ISSUE_TYPES),
                                },
                                "problem": {"type": "string", "minLength": 1},
                            },
                            "required": ["beat_id", "type", "problem"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["valid", "issues"],
                "additionalProperties": False,
            },
        },
    }


def build_beat_plan_audit_response_format(total_segments=None):
    beat_id_schema = {"type": "integer", "minimum": 1}
    if total_segments is not None:
        total_segments = int(total_segments)
        if total_segments <= 0:
            raise ValueError("Beat-plan auditing requires at least one segment.")
        beat_id_schema["maximum"] = total_segments
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beat_plan_audit",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "valid": {"type": "boolean"},
                    "macro_arc_consistent_with_source": {"type": "boolean"},
                    "blocking_issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "beat_start": {
                                    **beat_id_schema,
                                },
                                "beat_end": {
                                    **beat_id_schema,
                                },
                                "type": {"type": "string", "minLength": 1},
                                "source_requirement": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "problem": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                            },
                            "required": [
                                "beat_start",
                                "beat_end",
                                "type",
                                "source_requirement",
                                "problem",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": [
                    "valid",
                    "macro_arc_consistent_with_source",
                    "blocking_issues",
                    "warnings",
                ],
                "additionalProperties": False,
            },
        },
    }


def beat_ids_for_repair_ranges(repair_ranges, beat_end=None):
    if beat_end is not None:
        repair_ranges = [{
            "beat_start": repair_ranges,
            "beat_end": beat_end,
        }]
    if not isinstance(repair_ranges, list) or not repair_ranges:
        raise ValueError("Beat-plan repair requires at least one repair range.")
    requested_ids = set()
    for range_number, repair_range in enumerate(repair_ranges, start=1):
        if not isinstance(repair_range, dict):
            raise ValueError(f"Repair range {range_number} must be an object.")
        beat_start = repair_range.get("beat_start")
        range_end = repair_range.get("beat_end")
        if (
            isinstance(beat_start, bool)
            or not isinstance(beat_start, int)
            or isinstance(range_end, bool)
            or not isinstance(range_end, int)
            or beat_start <= 0
            or range_end < beat_start
        ):
            raise ValueError(f"Repair range {range_number} is invalid.")
        requested_ids.update(range(beat_start, range_end + 1))
    return sorted(requested_ids)


def format_beat_plan_repair_ranges(repair_ranges):
    beat_ids_for_repair_ranges(repair_ranges)
    return "Beats " + ", ".join(
        f"{repair_range['beat_start']}-{repair_range['beat_end']}"
        for repair_range in repair_ranges
    )


def build_beat_plan_repair_response_format(repair_ranges, beat_end=None):
    expected_ids = beat_ids_for_repair_ranges(repair_ranges, beat_end)
    replacement_count = len(expected_ids)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beat_plan_repair",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "beats": {
                        "type": "array",
                        "minItems": replacement_count,
                        "maxItems": replacement_count,
                        "items": {
                            "type": "object",
                            "properties": {
                                "beat_id": {
                                    "type": "integer",
                                    "enum": expected_ids,
                                },
                                "text": {"type": "string", "minLength": 1},
                            },
                            "required": ["beat_id", "text"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["beats"],
                "additionalProperties": False,
            },
        },
    }


def _format_beat_arc_subject_names(subject_information):
    subject_names = []
    for subject_line in str(subject_information or "").splitlines():
        subject_name, separator, _ = subject_line.strip().lstrip("- ").partition(
            " is "
        )
        if separator and subject_name:
            subject_names.append(subject_name)
    return ", ".join(subject_names)


def build_beat_arc_plan_messages(
    story,
    total_segments,
    subject_information="",
    correction="",
):
    subject_text = _format_beat_arc_subject_names(subject_information) or "N/A"
    correction_text = ""
    if correction:
        correction_text = f"""

CORRECTION REQUIRED
{correction}
Return the complete corrected arc.
"""
    return [
        {
            "role": "system",
            "content": (
                "You organize a supplied story into a chronological video arc. "
                "Preserve the story; do not invent a replacement story. Return "
                "only the requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Create a macro story arc for a {total_segments}-beat video.

A phase exists when the STORY'S NARRATIVE PURPOSE changes, not merely when the
location or characters change. Use the fewest meaningful phases that still keep
distinct story stages separate.

PHASE BOUNDARY RULES
- Separate a setup/introduction stage from a long main process/conflict when the
  source clearly contains both.
- Separate completion/aftermath/resolution from the main process when the source
  clearly gives the ending a different purpose.
- A long repeated process may occupy one large phase.
- Do NOT collapse setup + long process + completion into one phase merely because
  they occur in the same place with the same characters.
- One phase is appropriate only when the story genuinely has one narrative
  purpose from beginning through ending. For a long multi-stage story, a
  one-phase arc should be unusual.
- Phase sizes do not need to be similar. Give most beats to the stage containing
  most of the required visible events.

The phases must cover Beats 1-{total_segments} exactly once with no gaps or
overlaps. For each phase return only:
- phase_number
- beat_start
- beat_end
- narrative_purpose
- broad_progression
- characters_introduced
- location
- required_end_state

`broad_progression` is an abstract description of what happens DURING that phase.
`required_end_state` is the concrete handoff state that must be true at the END
of that phase before the next phase starts. Do not put next-phase progression in
the current phase merely to make the arc feel complete.

Preserve required events, order, premise, and ending. Connective detail is
allowed, but do not introduce unsupported major characters, transformations,
procedures, mythology, timelines, loops, resurrection, or other plot mechanics.

MAIN CHARACTER(S)
{subject_text}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---
{correction_text}

Return only a JSON object with a `phases` array using exactly the fields above.
""".strip(),
        },
    ]

def parse_beat_arc_plan(raw_result, total_segments, formatter=None):
    if total_segments <= 0:
        raise ValueError("Beat arc planning requires at least one segment.")
    formatter = formatter or ACTIVE_FORMATTER
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("The LLM arc response must be valid JSON.") from error
    if (
        isinstance(candidate, dict)
        and set(candidate) == {"arc_plan"}
        and isinstance(candidate["arc_plan"], dict)
    ):
        candidate = candidate["arc_plan"]
    if not isinstance(candidate, dict) or not isinstance(
        candidate.get("phases"), list
    ):
        raise ValueError("The LLM arc response must contain a JSON 'phases' array.")
    if set(candidate) != {"phases"}:
        raise ValueError(
            "The LLM arc response must contain only the JSON 'phases' array."
        )
    phases = candidate["phases"]
    if not phases:
        raise ValueError("The macro story arc must contain at least one phase.")
    if len(phases) > total_segments:
        raise ValueError(
            "The macro story arc cannot contain more phases than story beats."
        )

    normalized_phases = []
    expected_start = 1
    required_fields = (
        "phase_number",
        "beat_start",
        "beat_end",
        "narrative_purpose",
        "broad_progression",
        "characters_introduced",
        "location",
        "required_end_state",
    )
    for phase_number, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            raise ValueError(f"Macro arc phase {phase_number} must be an object.")
        missing = [field for field in required_fields if field not in phase]
        if missing:
            raise ValueError(
                f"Macro arc phase {phase_number} is missing: {', '.join(missing)}."
            )
        extras = [field for field in phase if field not in required_fields]
        if extras:
            raise ValueError(
                f"Macro arc phase {phase_number} has unsupported fields: "
                f"{', '.join(extras)}."
            )
        returned_phase_number = phase["phase_number"]
        if (
            isinstance(returned_phase_number, bool)
            or not isinstance(returned_phase_number, int)
            or returned_phase_number != phase_number
        ):
            raise ValueError(
                f"Macro arc phase {phase_number} must have phase_number "
                f"{phase_number}."
            )
        start = phase["beat_start"]
        end = phase["beat_end"]
        if isinstance(start, bool) or not isinstance(start, int):
            raise ValueError(
                f"Macro arc phase {phase_number} beat_start must be an integer."
            )
        if isinstance(end, bool) or not isinstance(end, int):
            raise ValueError(
                f"Macro arc phase {phase_number} beat_end must be an integer."
            )
        if start != expected_start:
            relationship = "overlap" if start < expected_start else "gap"
            raise ValueError(
                f"Macro arc phase {phase_number} creates a {relationship}: expected "
                f"beat_start {expected_start}, received {start}."
            )
        if end < start or end > total_segments:
            raise ValueError(
                f"Macro arc phase {phase_number} has invalid inclusive range "
                f"{start}-{end} for {total_segments} beats."
            )
        purpose = str(phase["narrative_purpose"] or "").strip()
        progression = str(phase["broad_progression"] or "").strip()
        end_state = str(phase["required_end_state"] or "").strip()
        location = str(phase["location"] or "").strip()
        characters = phase["characters_introduced"]
        if not isinstance(characters, list) or any(
            not isinstance(character, str) or not character.strip()
            for character in characters
        ):
            raise ValueError(
                f"Macro arc phase {phase_number} characters_introduced must be "
                "an array of non-empty strings."
            )
        normalized_characters = [
            " ".join(character.split()) for character in characters
        ]
        if len({character.casefold() for character in normalized_characters}) != len(
            normalized_characters
        ):
            raise ValueError(
                f"Macro arc phase {phase_number} characters_introduced contains "
                "duplicates."
            )
        if not purpose or not progression or not end_state or not location:
            raise ValueError(
                f"Macro arc phase {phase_number} must include purpose, broad "
                "progression, location, and end state."
            )
        normalized_phases.append(
            {
                "phase_number": phase_number,
                "beat_start": start,
                "beat_end": end,
                "narrative_purpose": purpose,
                "broad_progression": " ".join(progression.split()),
                "characters_introduced": normalized_characters,
                "location": " ".join(location.split()),
                "required_end_state": end_state,
            }
        )
        expected_start = end + 1
    if expected_start != total_segments + 1:
        raise ValueError(
            f"Macro story arc ends at Beat {expected_start - 1}; it must cover "
            f"through Beat {total_segments}."
        )
    return {"phases": normalized_phases}


def build_phase_generation_batches(
    macro_arc,
    max_batch_size=None,
):
    """Return one generation batch per phase unless a limit is explicitly set."""
    if max_batch_size is not None:
        if isinstance(max_batch_size, bool) or not isinstance(max_batch_size, int):
            raise ValueError("Beat generation batch size must be an integer.")
        if max_batch_size <= 0:
            raise ValueError("Beat generation batch size must be positive.")
    phases = macro_arc.get("phases") if isinstance(macro_arc, dict) else None
    if not isinstance(phases, list) or not phases:
        raise ValueError("Phase-based beat generation requires a macro arc.")

    batches = []
    expected_start = 1
    for phase_index, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            raise ValueError(f"Macro arc phase {phase_index} must be an object.")
        phase_number = phase.get("phase_number")
        beat_start = phase.get("beat_start")
        beat_end = phase.get("beat_end")
        if phase_number != phase_index:
            raise ValueError(
                f"Macro arc phase {phase_index} must have phase_number "
                f"{phase_index}."
            )
        if (
            isinstance(beat_start, bool)
            or not isinstance(beat_start, int)
            or isinstance(beat_end, bool)
            or not isinstance(beat_end, int)
            or beat_start != expected_start
            or beat_end < beat_start
        ):
            raise ValueError(
                f"Macro arc phase {phase_index} has an invalid beat range."
            )
        phase_batch_size = max_batch_size or (beat_end - beat_start + 1)
        for batch_start in range(beat_start, beat_end + 1, phase_batch_size):
            batches.append(
                {
                    "phase": phase,
                    "batch_start": batch_start,
                    "batch_end": min(
                        batch_start + phase_batch_size - 1,
                        beat_end,
                    ),
                }
            )
        expected_start = beat_end + 1
    return batches


def build_beat_arc_fidelity_messages(
    story,
    macro_arc,
    subject_information="",
):
    subject_text = str(subject_information or "").strip() or "N/A"
    return [
        {
            "role": "system",
            "content": (
                "You are a conservative story-arc fidelity checker. Report only "
                "major blocking errors. Return only the requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Check whether the PROPOSED MACRO STORY ARC preserves and USEFULLY ORGANIZES the
SOURCE STORY for phase-by-phase beat generation.

Set valid=false only if the arc:
- changes the central premise or core conflict;
- omits or reverses a required major event;
- changes the required ending;
- invents a major unsupported character, transformation, procedure, mythology,
  timeline, or plot mechanic;
- materially contradicts an explicit source fact;
- collapses clearly distinct source stages into one phase in a way that removes
  a meaningful handoff boundary. In particular, if the source clearly contains
  setup/introduction, a long main process/conflict, and completion/aftermath,
  those stages should not all be merged into one catch-all phase; or
- fails to establish concrete clothing when a defined human Subject is first
  shown. A human Subject introduced later may establish clothing in that later
  introduction phase.

Do NOT reject merely because phase sizes are unequal or because one long process
uses most of the beats. A one-phase arc is valid when the source truly has one
continuous narrative purpose with no meaningful stage change.

Do not critique wording, pacing, minor visual details, or screenplay quality.
When uncertain, return valid=true.

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---

DEFINED SUBJECTS
{subject_text}

PROPOSED MACRO STORY ARC
{json.dumps(macro_arc, ensure_ascii=False, indent=2)}

Return only {{"valid": true, "issues": []}} or the same object with valid=false
and concise blocking issue strings.
""".strip(),
        },
    ]

def parse_beat_arc_fidelity(raw_result, formatter=None):
    formatter = formatter or ACTIVE_FORMATTER
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(
                "The macro-arc fidelity response must be valid JSON."
            ) from error
    if (
        isinstance(candidate, dict)
        and set(candidate) == {"fidelity"}
        and isinstance(candidate["fidelity"], dict)
    ):
        candidate = candidate["fidelity"]
    if not isinstance(candidate, dict):
        raise ValueError("The macro-arc fidelity response must be a JSON object.")
    valid = candidate.get("valid")
    issues = candidate.get("issues")
    if not isinstance(valid, bool):
        raise ValueError("The macro-arc fidelity 'valid' field must be boolean.")
    if not isinstance(issues, list) or not all(
        isinstance(issue, str) and issue.strip() for issue in issues
    ):
        raise ValueError(
            "The macro-arc fidelity 'issues' field must be a string array."
        )
    normalized_issues = [" ".join(issue.split()) for issue in issues]
    if valid != (not normalized_issues):
        raise ValueError(
            "Macro-arc fidelity 'valid' must be true exactly when issues is empty."
        )
    return {"valid": valid, "issues": normalized_issues}


def build_beat_phase_validation_messages(
    beats,
    current_phase,
    next_phase=None,
    previous_phase=None,
    previous_beat=None,
    previous_beats=None,
):
    """Build the mandatory validation request for one generated macro phase."""
    phase_number = int(current_phase["phase_number"])
    beat_start = int(current_phase["beat_start"])
    beat_end = int(current_phase["beat_end"])

    numbered_beats = "\n".join(
        f"Beat {number}: {beat}"
        for number, beat in enumerate(beats, start=beat_start)
    )

    next_phase_text = (
        json.dumps(next_phase, ensure_ascii=False, indent=2)
        if next_phase is not None
        else "N/A (this is the final phase)"
    )

    previous_phase_text = (
        json.dumps(previous_phase, ensure_ascii=False, indent=2)
        if previous_phase is not None
        else "N/A (this is the first phase)"
    )

    previous_beat_text = (
        f"Beat {beat_start - 1}: {previous_beat}"
        if previous_beat is not None
        else "N/A (this is the first phase)"
    )

    earlier_beats = list(previous_beats or [])
    if not earlier_beats and previous_beat is not None:
        earlier_beats = [previous_beat]
    earlier_start = max(1, beat_start - len(earlier_beats))
    earlier_beats_text = (
        "\n".join(
            f"Beat {number}: {beat}"
            for number, beat in enumerate(earlier_beats, start=earlier_start)
        )
        if earlier_beats
        else "N/A (this is the first phase)"
    )

    issue_types_text = "\n".join(
        f"- {issue_type}"
        for issue_type in BEAT_PHASE_VALIDATION_ISSUE_TYPES
    )

    response_example = json.dumps(
        {
            "valid": False,
            "issues": [
                {
                    "beat_id": beat_end,
                    "type": "missing_end_state",
                    "problem": (
                        "The final beat does not clearly establish the "
                        "current phase required_end_state."
                    ),
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )

    following_phase_rules = ""
    if next_phase is not None:
        following_phase_rules = f"""
FOLLOWING-PHASE BOUNDARY RULES

- CURRENT PHASE.required_end_state owns the boundary and takes precedence over
  conflicting FOLLOWING PHASE fields.

- Anything explicitly necessary to establish CURRENT PHASE.required_end_state
  is allowed in the current phase, even if the same character, entity, location,
  condition, or event also appears in the FOLLOWING PHASE.

- Treat the FOLLOWING PHASE as beginning immediately AFTER the current
  required_end_state becomes true.

- next_phase_scope_creep means a beat performs meaningful progression that
  occurs AFTER the current required_end_state, not progression needed to reach it.

- A character from FOLLOWING PHASE.characters_introduced is NOT early if that
  character or entity must appear for CURRENT PHASE.required_end_state to become
  true.

- A FOLLOWING PHASE location or environmental state is NOT early if reaching or
  beginning that state is explicitly required by CURRENT PHASE.required_end_state.

- Do not treat a changed condition of the same physical place as a new location
  merely because the FOLLOWING PHASE describes it differently.

- Setup, reaction, or foreshadowing is allowed when it helps establish the
  current required_end_state. Reject only events that materially continue
  beyond that handoff into phase {phase_number + 1}'s distinctive progression.

Example boundary logic:
If the current required_end_state is "alien craft land in the theme park,
starting the crisis" and the following phase is "visitors flee while aliens
abduct people," then the landing belongs to the CURRENT phase. Abductions and
the family's flight belong to the FOLLOWING phase.
""".strip()

    return [
        {
            "role": "system",
            "content": (
                "You are a narrow chronological story-state and phase-boundary "
                "validator. Check persistent state, opening continuity, whether "
                "the current phase reaches its required end state, and whether "
                "it materially progresses past that boundary. Do not rewrite "
                "the beats. Do not critique quality, pacing, drama, or wording. "
                "Return only the requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Validate the newly generated beats for macro phase {phase_number}, whose exact
range is Beats {beat_start}-{beat_end}.

CORE RULES

1. Beat {beat_start} must plausibly continue from the previous accepted phase
   end state when a previous phase exists.

2. The beats must execute the CURRENT PHASE's broad_progression.

3. Beat {beat_end} MUST clearly make CURRENT PHASE.required_end_state true.

4. Semantic equivalence counts. Do not require exact wording or a preferred
   dramatic presentation.

5. CURRENT PHASE.required_end_state defines the handoff boundary. Events needed
   to make that state true belong to the CURRENT PHASE.

6. Do not reject a beat merely because its event, character, location, or
   environmental condition is also mentioned in the FOLLOWING PHASE.

7. Reject scope creep only when a beat materially performs story progression
   that occurs AFTER CURRENT PHASE.required_end_state has already been reached.

8. Do not invent finer distinctions than the phase text states. For example,
   if required_end_state says an entity "emerges," do not reinterpret that as
   "partially emerges" or "only hints at emerging."

9. Do not invent requirements from SOURCE STORY, canon, genre expectations, or
   your own preferences. Judge only the supplied phase information and beats.

10. Do not report pacing, tone, imagery, detail level, dramatic strength, or
    minor connective actions as failures.

11. Track the semantic result of every explicit irreversible transition in ALL
    EARLIER ACCEPTED BEATS and in earlier beats of the current phase. Once an
    item, clothing, or structural feature is definitively destroyed, removed, consumed,
    detached, replaced, or otherwise permanently changed, every later beat must
    begin from that resulting state. Reject a later beat that repeats the same
    transition on the same entity or treats its prior state as still true.

12. Use semantic reasoning, not keyword matching. Report a conflict only when
    the earlier transition is definitive and the later beat clearly requires an
    incompatible earlier state or performs that completed transition again.
    Do not report a conflict when the text clearly establishes restoration, a
    new instance, or a distinct entity between the two events.

{following_phase_rules}

ISSUE REPORTING

Set valid=true only when there is a clear pass.

Otherwise return one issue object per concrete boundary failure.

Each issue must contain exactly:
- beat_id: the global beat number responsible;
- type: one allowed type;
- problem: a concise factual explanation.

ALLOWED ISSUE TYPES
{issue_types_text}

Use them narrowly:

- missing_end_state:
  Beat {beat_end} fails to make CURRENT PHASE.required_end_state true.

- next_phase_scope_creep:
  A beat materially performs progression that belongs AFTER the current
  required_end_state.

- future_character:
  A genuinely next-phase-only character appears before the boundary and is NOT
  required to establish the current required_end_state.

- future_location:
  A genuinely different next-phase location is entered before the boundary and
  is NOT required by the current required_end_state. Do not use this merely for
  a changed condition of the same physical location.

- bad_opening_continuity:
  Beat {beat_start} contradicts or skips the previous accepted phase end state.
  Never use this type for the first phase.

- persistent_state_conflict:
  A later beat contradicts the lasting result of an earlier irreversible event
  or attempts the same completed irreversible transition again. Set beat_id to
  the later conflicting beat, not the earlier state-establishing beat.

PREVIOUS PHASE
{previous_phase_text}

PREVIOUS ACCEPTED BEAT
{previous_beat_text}

ALL EARLIER ACCEPTED BEATS
{earlier_beats_text}

CURRENT PHASE
{json.dumps(current_phase, ensure_ascii=False, indent=2)}

FOLLOWING PHASE
{next_phase_text}

NEWLY GENERATED CURRENT-PHASE BEATS
{numbered_beats}

Return only JSON using this structure:
{response_example}

When the phase passes, return:
{{"valid": true, "issues": []}}
""".strip(),
        },
    ]


def parse_beat_phase_validation(
    raw_result,
    formatter=None,
    beat_start=None,
    beat_end=None,
):
    """Parse a phase validation response and enforce valid/issues agreement."""
    formatter = formatter or ACTIVE_FORMATTER
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(
                "The beat-phase validation response must be valid JSON."
            ) from error
    if not isinstance(candidate, dict) or set(candidate) != {"valid", "issues"}:
        raise ValueError(
            "The beat-phase validation response must contain only 'valid' and "
            "'issues'."
        )
    valid = candidate["valid"]
    issues = candidate["issues"]
    if not isinstance(valid, bool):
        raise ValueError("The beat-phase validation 'valid' field must be boolean.")
    if not isinstance(issues, list):
        raise ValueError(
            "The beat-phase validation 'issues' field must be an array."
        )
    normalized_issues = []
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {
            "beat_id",
            "type",
            "problem",
        }:
            raise ValueError(
                "Every beat-phase validation issue must contain exactly "
                "'beat_id', 'type', and 'problem'."
            )
        beat_id = issue["beat_id"]
        issue_type = issue["type"]
        problem = issue["problem"]
        if isinstance(beat_id, bool) or not isinstance(beat_id, int) or beat_id <= 0:
            raise ValueError(
                "Every beat-phase validation issue beat_id must be a positive "
                "integer."
            )
        if beat_start is not None and beat_id < int(beat_start):
            raise ValueError("Beat-phase validation issue beat_id precedes the phase.")
        if beat_end is not None and beat_id > int(beat_end):
            raise ValueError("Beat-phase validation issue beat_id exceeds the phase.")
        if issue_type not in BEAT_PHASE_VALIDATION_ISSUE_TYPES:
            raise ValueError(
                "Beat-phase validation issue type must be one of: "
                + ", ".join(BEAT_PHASE_VALIDATION_ISSUE_TYPES)
                + "."
            )
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError(
                "Every beat-phase validation issue problem must be a non-empty "
                "string."
            )
        normalized_issues.append(
            {
                "beat_id": beat_id,
                "type": issue_type,
                "problem": " ".join(problem.split()),
            }
        )
    if valid != (not normalized_issues):
        raise ValueError(
            "Beat-phase validation 'valid' must be true exactly when issues is "
            "empty."
        )
    return {"valid": valid, "issues": normalized_issues}


def reconcile_beat_phase_validation(
    validation,
    beat_start,
    beat_end,
    passed_beat_ids,
):
    """Ignore new claims against unchanged beats that passed an earlier check."""
    phase_beat_ids = set(range(int(beat_start), int(beat_end) + 1))
    previously_passed = set(passed_beat_ids) & phase_beat_ids
    reported_issue_ids = {
        issue["beat_id"] for issue in validation["issues"]
    }

    # Every beat omitted from this validation response has passed this check.
    # Previously passed beats remain trusted because targeted repair never edits
    # them, even if a later seeded validation response changes its opinion.
    passed_beat_ids.update(phase_beat_ids - reported_issue_ids)
    effective_issues = [
        issue
        for issue in validation["issues"]
        if issue["beat_id"] not in previously_passed
    ]
    ignored_issues = [
        issue
        for issue in validation["issues"]
        if issue["beat_id"] in previously_passed
    ]
    return (
        {"valid": not effective_issues, "issues": effective_issues},
        ignored_issues,
    )


def format_beat_phase_validation_correction(validation):
    """Format structured phase issues for targeted beat repair."""
    issues = sorted(
        validation["issues"],
        key=lambda issue: (issue["beat_id"], issue["type"]),
    )
    beat_ids = sorted({issue["beat_id"] for issue in issues})
    bullets = "\n".join(
        f"- Beat {issue['beat_id']}: {issue['problem']}" for issue in issues
    )
    return (
        "PHASE VALIDATION CORRECTION\n\n"
        "The previous phase failed chronological state or macro-boundary "
        "validation:\n\n"
        f"{bullets}\n\n"
        "Repair only the violating beat IDs "
        + ", ".join(str(beat_id) for beat_id in beat_ids)
        + ". Every other beat is immutable. Preserve the CURRENT PHASE "
        "progression, honor every lasting state established by earlier beats, "
        "reach its required_end_state in the final beat, and do not enact NEXT "
        "PHASE progression."
    )


def beat_phase_validation_repair_ranges(validation):
    """Return one exact singleton repair range per violating phase beat."""
    beat_ids = sorted({issue["beat_id"] for issue in validation["issues"]})
    if not beat_ids:
        raise ValueError("Targeted phase repair requires at least one violation.")
    return [
        {"beat_start": beat_id, "beat_end": beat_id}
        for beat_id in beat_ids
    ]


def format_phrase_exclusions_section(phrase_exclusions):
    """Format the optional hard exclusion list for a beat-writing prompt."""
    exclusions = [
        " ".join(str(value).split()).strip()
        for value in (phrase_exclusions or [])
        if str(value).strip()
    ]
    if not exclusions:
        return ""
    return (
        "\n\nWORDS AND PHRASES NOT ALLOWED IN BEATS\n"
        "Do not use any of the following words or phrases in any beat. "
        "Matching is case-insensitive and applies to complete words or phrases:\n"
        + "\n".join(
            f"- {json.dumps(value, ensure_ascii=False)}"
            for value in exclusions
        )
    )


def build_beat_phase_repair_messages(
    phase_beats,
    current_phase,
    validation,
    next_phase=None,
    previous_phase=None,
    previous_beats=None,
    correction="",
    phrase_exclusions=(),
):
    """Build a repair request containing only the validator-cited beat IDs."""
    beat_start = int(current_phase["beat_start"])
    beat_end = int(current_phase["beat_end"])
    expected_count = beat_end - beat_start + 1
    if len(phase_beats) != expected_count:
        raise ValueError("Phase repair requires the complete current phase context.")

    repair_ranges = beat_phase_validation_repair_ranges(validation)
    requested_ids = beat_ids_for_repair_ranges(repair_ranges)
    if requested_ids[0] < beat_start or requested_ids[-1] > beat_end:
        raise ValueError("Phase repair violation is outside the current phase.")

    previous_beats = list(previous_beats or [])
    earlier_text = (
        "\n".join(
            f"Beat {number}: {beat}"
            for number, beat in enumerate(previous_beats, start=1)
        )
        if previous_beats
        else "N/A (this is the first phase)"
    )
    phase_text = "\n".join(
        f"Beat {number}: {beat}"
        for number, beat in enumerate(phase_beats, start=beat_start)
    )
    previous_phase_text = (
        json.dumps(previous_phase, ensure_ascii=False, indent=2)
        if previous_phase is not None
        else "N/A (this is the first phase)"
    )
    next_phase_text = (
        json.dumps(next_phase, ensure_ascii=False, indent=2)
        if next_phase is not None
        else "N/A (this is the final phase)"
    )
    correction_text = ""
    if correction:
        correction_text = f"""

YOUR PREVIOUS REPAIR RESPONSE WAS INVALID
{correction}
Return all and only the same requested beat IDs again.
"""
    phrase_exclusions_text = format_phrase_exclusions_section(phrase_exclusions)

    return [
        {
            "role": "system",
            "content": (
                "You are a conservative story-beat repair editor. Rewrite only "
                "the beat IDs explicitly cited by the validator. Treat every "
                "other beat as immutable and return only the requested JSON."
            ),
        },
        {
            "role": "user",
            "content": f"""
Repair only violating Beat IDs {', '.join(str(beat_id) for beat_id in requested_ids)}
in macro phase {current_phase['phase_number']} (Beats {beat_start}-{beat_end}).

TARGETED REPAIR CONTRACT
- Return exactly one replacement for each requested Beat ID and no other beats.
- Do not rewrite, paraphrase, or return any non-violating beat.
- Fix every listed validation issue associated with each requested beat.
- All earlier accepted beats and all non-violating current-phase beats are
  immutable story-state and continuity anchors.
- Preserve chronological cause and effect with the immutable beats immediately
  before and after each replacement.
- Keep the current phase inside its broad_progression, make its
  required_end_state true by its final beat, and do not perform progression that
  belongs after that boundary.
- Each replacement must contain one to three concise complete sentences and
  must not end with a colon.

PHASE VALIDATION ISSUES
{json.dumps(validation['issues'], ensure_ascii=False, indent=2)}

PREVIOUS PHASE
{previous_phase_text}

ALL EARLIER ACCEPTED BEATS (IMMUTABLE)
{earlier_text}

CURRENT PHASE
{json.dumps(current_phase, ensure_ascii=False, indent=2)}

FOLLOWING PHASE
{next_phase_text}

CURRENT-PHASE BEATS
{phase_text}
{phrase_exclusions_text}
{correction_text}

Return only a JSON object with a beats array. Each item must contain exactly
beat_id and text. Include Beat IDs {', '.join(str(beat_id) for beat_id in requested_ids)}
and no others.
""".strip(),
        },
    ]


def format_macro_phase_boundaries(macro_arc):
    """Render exact Python-known phase ranges for audit/verification prompts."""
    phases = macro_arc.get("phases") if isinstance(macro_arc, dict) else None
    if not isinstance(phases, list) or not phases:
        return "N/A"
    lines = []
    for index, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            continue
        phase_number = phase.get("phase_number", index)
        beat_start = phase.get("beat_start")
        beat_end = phase.get("beat_end")
        if not isinstance(beat_start, int) or not isinstance(beat_end, int):
            continue
        if index < len(phases):
            transition = f"next phase begins at Beat {beat_end + 1}"
        else:
            transition = "final phase; there is no next phase"
        lines.append(
            f"Phase {phase_number}: Beats {beat_start}-{beat_end}; "
            f"exact phase-ending beat = Beat {beat_end}; {transition}."
        )
    return "\n".join(lines) or "N/A"


def build_beat_plan_verification_response_format(issue_ids):
    """Return a compact schema for verifying only already-frozen blockers."""
    issue_ids = sorted(set(int(issue_id) for issue_id in issue_ids))
    if not issue_ids:
        raise ValueError("Beat-plan verification requires at least one issue ID.")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_beat_plan_verification",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "unresolved_issue_ids": {
                        "type": "array",
                        "items": {
                            "type": "integer",
                            "enum": issue_ids,
                        },
                        "uniqueItems": True,
                    },
                },
                "required": ["unresolved_issue_ids"],
                "additionalProperties": False,
            },
        },
    }


def parse_beat_plan_verification(raw_result, issue_ids, formatter=None):
    """Parse a verifier response without permitting new blocker identities."""
    formatter = formatter or ACTIVE_FORMATTER
    allowed_ids = sorted(set(int(issue_id) for issue_id in issue_ids))
    allowed = set(allowed_ids)
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(
                "The beat-plan verification response must be valid JSON."
            ) from error
    if not isinstance(candidate, dict) or set(candidate) != {"unresolved_issue_ids"}:
        raise ValueError(
            "The beat-plan verification response must contain only "
            "'unresolved_issue_ids'."
        )
    unresolved = candidate["unresolved_issue_ids"]
    if not isinstance(unresolved, list):
        raise ValueError("'unresolved_issue_ids' must be an array.")
    normalized = []
    seen = set()
    for raw_issue_id in unresolved:
        if isinstance(raw_issue_id, bool) or not isinstance(raw_issue_id, int):
            raise ValueError("Every unresolved issue ID must be an integer.")
        if raw_issue_id not in allowed:
            raise ValueError(
                f"Verifier returned unknown frozen issue ID {raw_issue_id}."
            )
        if raw_issue_id in seen:
            raise ValueError(
                f"Verifier returned duplicate frozen issue ID {raw_issue_id}."
            )
        seen.add(raw_issue_id)
        normalized.append(raw_issue_id)
    return sorted(normalized)


def build_beat_plan_verification_messages(
    story,
    total_segments,
    beats,
    macro_arc,
    frozen_issues,
    pending_issue_ids,
    subject_information="",
):
    """Verify only frozen blockers; never discover or redefine new blockers."""
    subject_text = str(subject_information or "").strip() or "N/A"
    numbered_beats = "\n".join(
        f"Beat {number}: {beat}" for number, beat in enumerate(beats, start=1)
    )
    phase_boundaries = format_macro_phase_boundaries(macro_arc)
    pending_issue_ids = sorted(set(int(issue_id) for issue_id in pending_issue_ids))
    issue_sections = []
    for issue_id in pending_issue_ids:
        if issue_id <= 0 or issue_id > len(frozen_issues):
            raise ValueError(f"Unknown frozen beat-plan issue ID {issue_id}.")
        issue_sections.append(
            f"ISSUE {issue_id}\n"
            + json.dumps(frozen_issues[issue_id - 1], ensure_ascii=False, indent=2)
        )
    frozen_text = "\n\n".join(issue_sections)
    return [
        {
            "role": "system",
            "content": (
                "You are a narrow beat-plan repair verifier. Verify only the "
                "listed frozen issues. You are forbidden from discovering, "
                "inventing, broadening, renaming, or relocating blockers. "
                "Return only the requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Verify the current COMPLETE {total_segments}-beat plan ONLY against the frozen
issues listed below.

The initial global audit already established the complete blocker set. This is
NOT a new global audit. Do not search for new problems and do not reinterpret the
story to create additional requirements.

VERIFICATION RULES
- For each frozen issue, answer only whether its HARD source requirement is still
  clearly unsatisfied in the CURRENT beat plan.
- For an issue whose type is `{PERSISTENT_STATE_CONFLICT_ISSUE_TYPE}`, instead
  verify semantically whether the targeted later beat still contradicts the
  definitive lasting state established earlier or repeats the same completed
  irreversible transition. This built-in chronological rule does not need to
  appear in SOURCE STORY.
- Return its numeric issue ID in unresolved_issue_ids only if it still clearly
  fails. Omit the ID when the requirement is now reasonably satisfied.
- Never return an issue ID that was not supplied below.
- Never change a frozen issue's type, source requirement, or repair target.
- If a frozen issue's old problem explanation contains a factual, numeric, or
  semantic mistake, judge the CURRENT beats against the quoted source_requirement
  instead of preserving the old mistake.
- Semantic equivalence counts. Do not fail synonyms or paraphrases such as
  "warped" versus "distorted" unless SOURCE STORY explicitly requires exact
  wording.
- If a required event or character appears anywhere in the exact phase-ending
  beat, that satisfies "at the end of the phase" unless SOURCE STORY explicitly
  requires a finer within-beat sequence. Do not call an event in Beat 20
  "mid-phase" when Python says Beat 20 is the phase-ending beat.
- A transition requirement such as "at the end of each phase ... into the next
  area" applies only to phases that actually have a next phase unless SOURCE
  STORY explicitly requires the same transition after the final phase.
- "Periodically" or "occasionally" means recurring at reasonable intervals; it
  does NOT mean every phase, every beat, or every phase-ending beat unless SOURCE
  STORY explicitly says so.
- Do not require characters or events merely because they exist in a famous or
  established version of the story. Only SOURCE STORY is hard authority.
- When the source requirement is already visibly satisfied, mark the issue
  resolved even if you would prefer different wording, placement, pacing, or
  dramatic emphasis.

PYTHON-DERIVED PHASE BOUNDARIES
{phase_boundaries}

FROZEN ISSUES TO VERIFY
{frozen_text}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---

MAIN CHARACTER(S)
{subject_text}

CURRENT COMPLETE BEAT PLAN
{numbered_beats}

Return only:
{{"unresolved_issue_ids": [/* zero or more supplied issue IDs */]}}
""".strip(),
        },
    ]


def build_beat_plan_audit_messages(
    story,
    total_segments,
    beats,
    macro_arc,
    subject_information="",
    beat_instructions="",
    repaired_beat_ids=None,
):
    subject_text = str(subject_information or "").strip() or "N/A"
    instruction_text = str(beat_instructions or "").strip() or "N/A"
    numbered_beats = "\n".join(
        f"Beat {number}: {beat}" for number, beat in enumerate(beats, start=1)
    )
    repaired_beat_ids = sorted(set(repaired_beat_ids or []))
    repaired_context = (
        ", ".join(str(beat_id) for beat_id in repaired_beat_ids)
        if repaired_beat_ids else "N/A"
    )
    phase_boundaries = format_macro_phase_boundaries(macro_arc)
    return [
        {
            "role": "system",
            "content": (
                "You are a conservative whole-story beat-plan auditor. Catch "
                "only clear story, authorization, or chronological-state failures. "
                "Do not optimize the screenplay. Return only the requested JSON "
                "object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Audit the complete {total_segments}-beat plan.

SOURCE STORY and explicit beat instructions are hard requirements. MACRO STORY
ARC is a planning scaffold and boundary guide.

AUTHORIZED-EVENT RULE
Every beat's primary WHAT must be traceable to SOURCE STORY, explicit beat
instructions, the current macro phase, or a physically necessary consequence of
one of those requirements. Specificity may explain HOW an authorized event is
shown, but specificity is NOT permission to invent an additional event.

When the source authorizes a broad category or repeated process, concrete members
of that category may be selected as needed to expand it into beats. Do not add
operations, transformations, targets, or setup changes outside the authorized
category merely to fill the beat budget or make the story more graphic.

Create a blocking issue only for:
- major unsupported premise drift;
- an unsupported concrete event, operation, transformation, removal, replacement,
  or setup change that is not authorized by the source/phase;
- a required major source event, named required character, ordering requirement,
  or ending that is missing or contradicted;
- a source-established condition that a beat changes or removes without source
  authorization;
- a later beat that contradicts a definitive lasting result of an earlier beat
  or repeats the same irreversible transition on the same item/body feature
  without an explicit restoration/replacement making it possible;
- a source-required repeated remove/replace or cause/result cycle where the plan
  performs only one side for an item, or defers so much unrelated progression
  that the required pair is effectively skipped; or
- several consecutive beats that substantially repeat the same event without
  progression.

For unsupported-event problems, report the SMALLEST offending beat range,
preferably one beat. Never report the entire plan merely because one or two beats
invent unsupported material.

Do not block for style, pacing preference, phase size, reactions, atmosphere,
dialogue style, camera choices, or minor omitted details.

For each blocking_issues object return:
- beat_start and beat_end: smallest range that actually needs rewriting;
- type: concise category;
- source_requirement: the violated hard source/instruction requirement, or for
  persistent-state conflicts the rule that definitive state remains true;
- problem: concise concrete failure.

Set `macro_arc_consistent_with_source` false only if the macro arc itself
contradicts a hard source requirement enough that beat repair is unsafe.
Warnings never make the plan invalid. Set valid=true exactly when
blocking_issues is empty.

PREVIOUSLY REPAIRED BEAT IDS
{repaired_context}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---

EXPLICIT BEAT INSTRUCTIONS
{instruction_text}

MAIN CHARACTER(S)
{subject_text}

PYTHON-DERIVED PHASE BOUNDARIES
{phase_boundaries}

MACRO STORY ARC
{json.dumps(macro_arc, ensure_ascii=False, indent=2)}

COMPLETE BEAT PLAN
{numbered_beats}
""".strip(),
        },
    ]

def build_beat_plan_repair_messages(
    story,
    total_segments,
    beats,
    macro_arc,
    blocking_issues,
    repair_ranges,
    subject_information="",
    beat_instructions="",
    correction="",
    phrase_exclusions=(),
):
    requested_ids = beat_ids_for_repair_ranges(repair_ranges)
    if requested_ids[-1] > len(beats):
        raise ValueError("Beat-plan repair range is outside the complete plan.")
    range_label = format_beat_plan_repair_ranges(repair_ranges)
    subject_text = str(subject_information or "").strip() or "N/A"
    instruction_text = str(beat_instructions or "").strip() or "N/A"
    phrase_exclusions_text = format_phrase_exclusions_section(phrase_exclusions)
    numbered_beats = "\n".join(
        f"Beat {number}: {beat}" for number, beat in enumerate(beats, start=1)
    )
    boundary_sections = []
    for repair_range in repair_ranges:
        beat_start = repair_range["beat_start"]
        beat_end = repair_range["beat_end"]
        preceding = (
            f"Beat {beat_start - 1}: {beats[beat_start - 2]}"
            if beat_start > 1
            else "N/A (this range begins at Beat 1)"
        )
        following = (
            f"Beat {beat_end + 1}: {beats[beat_end]}"
            if beat_end < len(beats)
            else "N/A (this range includes the final beat)"
        )
        boundary_sections.append(
            f"RANGE Beats {beat_start}-{beat_end}\n"
            f"Immutable beat before: {preceding}\n"
            f"Immutable beat after: {following}"
        )
    boundaries = "\n\n".join(boundary_sections)
    correction_text = ""
    if correction:
        correction_text = f"""

YOUR PREVIOUS REPAIR RESPONSE WAS INVALID
{correction}
Return the complete requested replacement range again.
"""
    return [
        {
            "role": "system",
            "content": (
                "You are a conservative beat-plan repair editor. Repair only "
                "the explicitly authorized beat range and return only the "
                "requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Repair {range_label} in this {total_segments}-beat plan in one repair round.

HARD AUTHORITY
- SOURCE STORY and explicit ADDITIONAL BEAT INSTRUCTIONS FROM STORY.TXT are hard
  requirements.
- MACRO STORY ARC is authoritative for the earliest beat at which each phase's
  location and characters_introduced entries may first appear; its remaining
  details are soft guidance.

REPAIR CONTRACT
- Modify ONLY beats inside these listed ranges: {range_label}.
- Every beat outside those ranges is immutable and must remain exactly unchanged.
- Return exactly one replacement object for every requested beat ID, preserving
  the same IDs and total replacement count.
- Fix only the stated blocking problem and preserve usable existing material
  where possible.
- Every replacement beat's primary event must be authorized by SOURCE STORY,
  explicit beat instructions, or the current macro phase. Do not replace one
  unsupported invention with a different unsupported invention.
- Specificity may clarify HOW an authorized event happens; it may not add a new
  WHAT merely for detail, shock, atmosphere, or beat-count filler.
- Maintain chronological cause-and-effect continuity with the immutable beats
  immediately before and after the range.
- Keep every replacement as a simple H3 EXECUTION TARGET: one primary physical
  operation or one tightly coupled cause -> action -> visible result. Use 1-2
  concise sentences and stop once that visible result is established.
- Do not solve an audit issue by packing several unrelated operations into one
  beat. Distribute required material only across the explicitly authorized beat
  IDs.
- Specificity belongs in the visible physical action/result. Do not add new
  tools, implants, mechanisms, powers, reactions, dialogue, camera directions,
  measurements, or decorative technology unless the hard source requires them.
- When repairing a `{PERSISTENT_STATE_CONFLICT_ISSUE_TYPE}` blocker, preserve the
  definitive lasting result established by the earlier immutable beat and
  rewrite the later conflict so it starts from that resulting state without
  repeating the completed irreversible transition.
- Do not introduce a new premise, mythology, characters, loops, copies,
  resurrection, or other major concepts unless the hard source supports them.
- Never mention a macro location or character before the beat_start of the phase
  where that location or characters_introduced entry first appears.
- Each replacement beat must not end with a colon and must satisfy the existing
  structural rules.

FROZEN BLOCKING ISSUES TO REPAIR
These issues came from the initial global audit. Fix these requirements only; do
not reinterpret them into new requirements or broaden their scope.
{json.dumps(blocking_issues, ensure_ascii=False, indent=2)}

NORMALIZED REPAIR RANGES
{json.dumps(repair_ranges, ensure_ascii=False, indent=2)}

IMMUTABLE RANGE BOUNDARIES
{boundaries}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---

ADDITIONAL BEAT INSTRUCTIONS FROM STORY.TXT
{instruction_text}
{phrase_exclusions_text}

MAIN CHARACTERS FROM SUBJECTS.TXT
{subject_text}

MACRO STORY ARC (SOFT CONTEXT ONLY)
{json.dumps(macro_arc, ensure_ascii=False, indent=2)}

COMPLETE CURRENT BEAT PLAN
{numbered_beats}
{correction_text}

Return only a JSON object with a beats array. Each item must contain exactly
beat_id and text, with one item for every requested beat ID and no others.
""".strip(),
        },
    ]


def parse_beat_plan_audit(raw_result, formatter=None, total_segments=None):
    formatter = formatter or ACTIVE_FORMATTER
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("The beat-plan audit response must be valid JSON.") from error
    if (
        isinstance(candidate, dict)
        and set(candidate) == {"audit"}
        and isinstance(candidate["audit"], dict)
    ):
        candidate = candidate["audit"]
    if not isinstance(candidate, dict):
        raise ValueError("The beat-plan audit response must be a JSON object.")
    valid = candidate.get("valid")
    arc_consistent = candidate.get("macro_arc_consistent_with_source")
    blocking_issues = candidate.get("blocking_issues")
    warnings = candidate.get("warnings")
    if not isinstance(valid, bool):
        raise ValueError("The beat-plan audit 'valid' field must be boolean.")
    if not isinstance(arc_consistent, bool):
        raise ValueError(
            "The beat-plan audit 'macro_arc_consistent_with_source' field must "
            "be boolean."
        )
    if not isinstance(blocking_issues, list):
        raise ValueError(
            "The beat-plan audit 'blocking_issues' field must be an array."
        )
    if not isinstance(warnings, list) or not all(
        isinstance(warning, str) and warning.strip() for warning in warnings
    ):
        raise ValueError(
            "The beat-plan audit 'warnings' field must be a string array."
        )
    if valid != (not blocking_issues):
        raise ValueError(
            "The beat-plan audit 'valid' field must be true exactly when the "
            "reported 'blocking_issues' array is empty."
        )
    required_issue_fields = {
        "beat_start",
        "beat_end",
        "type",
        "source_requirement",
        "problem",
    }
    normalized_blockers = []
    for issue_number, issue in enumerate(blocking_issues, start=1):
        if not isinstance(issue, dict) or set(issue) != required_issue_fields:
            continue
        beat_start = issue["beat_start"]
        beat_end = issue["beat_end"]
        if (
            isinstance(beat_start, bool)
            or not isinstance(beat_start, int)
            or isinstance(beat_end, bool)
            or not isinstance(beat_end, int)
        ):
            continue
        if beat_start <= 0 or beat_end < beat_start:
            continue
        if total_segments is not None and beat_end > total_segments:
            continue
        normalized_issue = {
            "beat_start": beat_start,
            "beat_end": beat_end,
        }
        for field in ("type", "source_requirement", "problem"):
            value = issue[field]
            if not isinstance(value, str) or not value.strip():
                normalized_issue = None
                break
            normalized_issue[field] = " ".join(value.split())
        if normalized_issue is not None:
            normalized_blockers.append(normalized_issue)
    normalized_warnings = [" ".join(warning.split()) for warning in warnings]
    return {
        "valid": not normalized_blockers,
        "macro_arc_consistent_with_source": arc_consistent,
        "blocking_issues": normalized_blockers,
        "discarded_blocking_issues": len(blocking_issues) - len(
            normalized_blockers
        ),
        "warnings": normalized_warnings,
    }


def hard_source_requirement_is_grounded(
    source_requirement,
    story,
    beat_instructions="",
):
    requirement = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(source_requirement or "").casefold(),
    ).strip()
    hard_source = re.sub(
        r"[^a-z0-9]+",
        " ",
        f"{story or ''} {beat_instructions or ''}".casefold(),
    ).strip()
    if not requirement or requirement in {"n a", "unknown", "unspecified"}:
        return False
    if requirement in hard_source:
        return True
    ignored = {
        "a", "an", "and", "are", "as", "at", "be", "before", "by", "for",
        "from", "in", "is", "it", "must", "of", "on", "or", "should", "the",
        "then", "to", "with",
    }
    requirement_tokens = {
        token for token in requirement.split()
        if token not in ignored and len(token) > 2
    }
    source_tokens = set(hard_source.split())
    if len(requirement_tokens) < 2:
        return False
    overlap = requirement_tokens & source_tokens
    return len(overlap) >= 2 and (
        len(overlap) / len(requirement_tokens) >= 0.6
    )


def normalize_beat_plan_repair_ranges(
    blocking_issues,
    total_segments,
    repaired_beat_ids=None,
    story="",
    beat_instructions="",
    max_gap=0,
):
    if total_segments <= 0:
        raise ValueError("Beat-plan repair requires at least one beat.")
    repaired_beat_ids = set(repaired_beat_ids or [])
    credible = []
    discarded = []
    downgraded = []
    required_fields = {
        "beat_start",
        "beat_end",
        "type",
        "source_requirement",
        "problem",
    }
    for issue in blocking_issues:
        if not isinstance(issue, dict):
            discarded.append(issue)
            continue
        beat_start = issue.get("beat_start")
        beat_end = issue.get("beat_end")
        if (
            set(issue) != required_fields
            or isinstance(beat_start, bool)
            or not isinstance(beat_start, int)
            or isinstance(beat_end, bool)
            or not isinstance(beat_end, int)
            or beat_start <= 0
            or beat_end < beat_start
            or beat_end > total_segments
        ):
            discarded.append(issue)
            continue
        normalized_issue = {
            "beat_start": beat_start,
            "beat_end": beat_end,
        }
        invalid_text = False
        for field in ("type", "source_requirement", "problem"):
            value = issue.get(field)
            if not isinstance(value, str) or not value.strip():
                invalid_text = True
                break
            normalized_issue[field] = " ".join(value.split())
        if invalid_text:
            discarded.append(issue)
            continue
        issue_ids = set(range(beat_start, beat_end + 1))
        repair_span = beat_end - beat_start + 1
        if repair_span > MAX_TARGETED_BEAT_REPAIR_SPAN:
            # A global audit is useful for spotting problems, but a complaint
            # that spans a large part of the plan is not precise enough to
            # authorize destructive rewriting. Preserve the generated plan and
            # surface the complaint as a warning instead.
            downgraded.append(normalized_issue)
            continue
        if (
            issue_ids & repaired_beat_ids
            and normalized_issue["type"]
            != PERSISTENT_STATE_CONFLICT_ISSUE_TYPE
            and not hard_source_requirement_is_grounded(
                normalized_issue["source_requirement"],
                story,
                beat_instructions,
            )
        ):
            downgraded.append(normalized_issue)
            continue
        credible.append(normalized_issue)

    credible.sort(key=lambda issue: (issue["beat_start"], issue["beat_end"]))
    merged = []
    for issue in credible:
        if (
            not merged
            or issue["beat_start"] > merged[-1]["beat_end"] + max_gap
        ):
            merged.append({
                "beat_start": issue["beat_start"],
                "beat_end": issue["beat_end"],
                "issues": [issue],
            })
            continue
        merged[-1]["beat_end"] = max(merged[-1]["beat_end"], issue["beat_end"])
        merged[-1]["issues"].append(issue)
    return {
        "issues": credible,
        "ranges": merged,
        "discarded": discarded,
        "downgraded": downgraded,
    }


def merge_overlapping_beat_blockers(blocking_issues, total_segments):
    return normalize_beat_plan_repair_ranges(
        blocking_issues,
        total_segments,
    )["ranges"]


def format_beat_plan_blocking_issues(blocking_issues):
    return " ".join(
        (
            f"Beats {issue['beat_start']}-{issue['beat_end']} "
            f"({issue['type']}): {issue['problem']} "
            f"[source requirement: {issue['source_requirement']}]"
        )
        for issue in blocking_issues
    )


def parse_beat_plan_repair(
    raw_result,
    repair_ranges,
    beat_end=None,
    formatter=None,
):
    formatter = formatter or ACTIVE_FORMATTER
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("The beat-plan repair response must be valid JSON.") from error
    if (
        isinstance(candidate, dict)
        and set(candidate) == {"repair"}
        and isinstance(candidate["repair"], dict)
    ):
        candidate = candidate["repair"]
    if not isinstance(candidate, dict) or set(candidate) != {"beats"}:
        raise ValueError(
            "The beat-plan repair response must contain only a JSON 'beats' array."
        )
    replacements = candidate["beats"]
    if not isinstance(replacements, list):
        raise ValueError("The beat-plan repair 'beats' field must be an array.")
    expected_ids = beat_ids_for_repair_ranges(repair_ranges, beat_end)
    if len(replacements) != len(expected_ids):
        raise ValueError(
            f"Expected exactly {len(expected_ids)} repaired beats for "
            f"the requested ranges, received {len(replacements)}."
        )
    by_id = {}
    for item_number, item in enumerate(replacements, start=1):
        if not isinstance(item, dict) or set(item) != {"beat_id", "text"}:
            raise ValueError(
                f"Repaired beat item {item_number} must contain exactly beat_id "
                "and text."
            )
        beat_id = item["beat_id"]
        if isinstance(beat_id, bool) or not isinstance(beat_id, int):
            raise ValueError(f"Repaired beat item {item_number} has a non-integer ID.")
        if beat_id not in expected_ids:
            raise ValueError(f"Unexpected repaired beat ID {beat_id}.")
        if beat_id in by_id:
            raise ValueError(f"Duplicate repaired beat ID {beat_id}.")
        by_id[beat_id] = item["text"]
    missing_ids = [beat_id for beat_id in expected_ids if beat_id not in by_id]
    if missing_ids:
        raise ValueError(
            "Missing repaired beat ID(s): "
            + ", ".join(str(beat_id) for beat_id in missing_ids)
            + "."
        )
    normalized_texts = parse_generated_beats(
        {"beats": [by_id[beat_id] for beat_id in expected_ids]},
        len(expected_ids),
        formatter=formatter,
    )
    return dict(zip(expected_ids, normalized_texts))


def splice_beat_plan_repair(
    beats,
    repair_ranges,
    replacement_beats,
    beat_end=None,
):
    original = list(beats)
    expected_ids = beat_ids_for_repair_ranges(repair_ranges, beat_end)
    if expected_ids[-1] > len(original):
        raise ValueError("Cannot splice an invalid beat-plan repair range.")
    if not isinstance(replacement_beats, dict) or set(replacement_beats) != set(
        expected_ids
    ):
        raise ValueError(
            "Repair replacements must exactly match the requested beat IDs."
        )
    repaired = list(original)
    for beat_id in expected_ids:
        repaired[beat_id - 1] = replacement_beats[beat_id]
    validated = parse_generated_beats({"beats": repaired}, len(original))
    requested = set(expected_ids)
    for beat_id, original_text in enumerate(original, start=1):
        if beat_id not in requested and validated[beat_id - 1] != original_text:
            raise RuntimeError(
                f"Beat-plan repair changed immutable Beat {beat_id}."
            )
    return repaired


_BEAT_INSTRUCTIONS = re.compile(
    r"(?ims)^[ \t]*beat_instructions[ \t]*:[ \t]*\["
    r"(?P<instructions>.*?)\][ \t]*(?:\n|$)"
)

_GEN_RULES = re.compile(
    r"(?ims)^[ \t]*gen_rules[ \t]*:[ \t]*"
    r"(?:\[(?P<bracketed_rules>.*?)\]|(?P<inline_rules>[^\r\n]*))"
    r"[ \t]*(?:\r?\n|$)"
)


def parse_story_beat_instructions(story):
    story = str(story or "")
    matches = list(_BEAT_INSTRUCTIONS.finditer(story))
    if len(matches) > 1:
        raise ValueError("story.txt contains more than one beat_instructions directive.")
    if not matches:
        return story.strip(), ""
    match = matches[0]
    narrative = (story[:match.start()] + story[match.end():]).strip()
    return narrative, match.group("instructions")


def parse_story_gen_rules(story):
    """Extract optional H3-generation rules from story.txt metadata."""
    story = str(story or "")
    matches = list(_GEN_RULES.finditer(story))
    if len(matches) > 1:
        raise ValueError("story.txt contains more than one gen_rules directive.")
    if not matches:
        return story.strip(), ""
    match = matches[0]
    narrative = (story[:match.start()] + story[match.end():]).strip()
    rules = match.group("bracketed_rules")
    if rules is None:
        rules = match.group("inline_rules").strip()
    return narrative, rules


def build_beat_generation_messages(
    story,
    total_segments,
    correction="",
    beat_instructions="",
    subject_information="",
    batch_start=None,
    batch_end=None,
    previous_beats=None,
    macro_arc=None,
    current_phase=None,
    audit_correction="",
    phrase_exclusions=(),
    gen_rules="",
):
    batch_start = 1 if batch_start is None else int(batch_start)
    batch_end = total_segments if batch_end is None else int(batch_end)
    batch_size = batch_end - batch_start + 1
    previous_beats = list(previous_beats or [])
    macro_arc = macro_arc or {"phases": []}
    current_phase = current_phase or {}
    phase_number = int(current_phase.get("phase_number", 1))
    subject_names = _format_beat_arc_subject_names(subject_information) or "N/A"

    phases = macro_arc.get("phases", [])
    previous_phase = next(
        (phase for phase in phases if phase.get("phase_number") == phase_number - 1),
        None,
    )
    next_phase = next(
        (phase for phase in phases if phase.get("phase_number") == phase_number + 1),
        None,
    )
    previous_phase_end_state = (
        previous_phase.get("required_end_state", "N/A") if previous_phase else "N/A"
    )

    # Only a small amount of already-accepted action history is useful here.
    recent_previous = previous_beats[-3:]
    previous_context = "N/A"
    if recent_previous:
        previous_start = batch_start - len(recent_previous)
        previous_context = "\n".join(
            f"Beat {number}: {beat}"
            for number, beat in enumerate(recent_previous, start=previous_start)
        )

    next_phase_boundary = "N/A"
    if next_phase:
        next_phase_boundary = json.dumps(
            {
                "phase_number": next_phase.get("phase_number"),
                "broad_progression": next_phase.get("broad_progression"),
                "required_end_state": next_phase.get("required_end_state"),
                "location": next_phase.get("location"),
            },
            ensure_ascii=False,
            indent=2,
        )

    supplemental_sections = []
    if correction:
        supplemental_sections.append(
            "CORRECTION REQUIRED\n"
            + str(correction).strip()
            + "\nRegenerate the complete current phase."
        )
    if beat_instructions:
        supplemental_sections.append(
            "STORY BEAT INSTRUCTIONS (MANDATORY)\n" + str(beat_instructions).strip()
        )
    if str(gen_rules or "").strip():
        supplemental_sections.append(
            "PROJECT GENERATION RULES (MANDATORY)\n" + str(gen_rules).strip()
        )
    phrase_exclusions_section = format_phrase_exclusions_section(phrase_exclusions)
    if phrase_exclusions_section:
        supplemental_sections.append(phrase_exclusions_section.strip())
    if audit_correction:
        supplemental_sections.append(
            "WHOLE-PLAN CORRECTION\n" + str(audit_correction).strip()
        )
    supplemental_text = (
        "\n\n" + "\n\n".join(supplemental_sections)
        if supplemental_sections else ""
    )

    response_shape = json.dumps(
        {"beats": [{"beat_number": batch_start, "beat_text": "..."}]},
        ensure_ascii=False,
    )
    return [
        {
            "role": "system",
            "content": (
                "You expand one macro story phase into concrete chronological "
                "simple video beats. Expand the supplied story; do not reinterpret or "
                "embellish it into a different story. Return only the requested "
                "JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Write exactly {batch_size} beats for Phase {phase_number}, global Beats
{batch_start}-{batch_end}.

Each beat is an EXECUTION TARGET for one H3 video clip, not prose and not a
miniature screenplay. Use 1 concise sentence. Give the Director only the
concrete visible action that must happen in this clip and the visible physical
result that must be true when the clip ends.

AUTHORIZED-EVENT TEST — APPLY THIS TO EVERY BEAT
Before writing a beat, ask: "What SOURCE STORY or CURRENT PHASE requirement
actually authorizes this event?" If there is no answer, do not write the event.

Specificity is not invention:
- Specificity may describe HOW an already-authorized action happens.
- Specificity may NOT create an additional WHAT: no extra operation,
  transformation, target, removal, replacement, setup change, character action,
  or technology merely to make the beat more vivid, graphic, or detailed.
- If the source authorizes a broad category or says "all" members of a category,
  selecting concrete members of that category is allowed because it is necessary
  to expand the source into visible beats. Do not add targets outside that
  authorized category.
- Preserve source-established setup details unless the source explicitly requires
  them to change. Do not spend beats dismantling setup merely to create action.

Beat-writing rules:
- Follow SOURCE STORY first and CURRENT PHASE second.
- Continue naturally from PREVIOUS PHASE END STATE and recent accepted beats.
- Progress chronologically; do not repeat or restage an earlier beat.
- Center each beat on ONE primary physical operation or one tightly coupled
  cause -> action -> visible result. If several distinct operations are needed,
  split them across separate beats.
- When the source requires a repeated remove/replace, destroy/rebuild, or other
  paired process for each item, keep the pair local: establish the removal/change
  and its corresponding replacement/result before moving to an unrelated item,
  unless SOURCE STORY explicitly requires bulk removal followed by later rebuild.
- Do not begin the next operation after this beat's visible result is reached.
- Preserve lasting results of earlier removals, destruction, replacements, or
  other irreversible changes unless the story explicitly restores them.
- If SOURCE STORY does not specify a tool or mechanism, use the minimum generic
  mechanism needed to make the authorized action visually executable. Do not
  invent elaborate tool systems, implants, powers, internal mechanisms, or new
  transformations.
- Do not invent dialogue or reactions unless SOURCE STORY or explicit beat
  instructions require them.
- Do not include camera directions unless SOURCE STORY explicitly requires a
  particular camera event. The Director owns normal camera staging.
- Do not include atmosphere, sound effects, measurements, lens choices, or
  decorative details unless they are necessary to understand the required
  physical action.
- Use the beat budget to EXPAND required source events into clear visible steps,
  never to manufacture additional events.
- Only create one sentence per beat.
- Reach CURRENT PHASE.required_end_state by the final beat of this phase.
- NEXT PHASE is boundary context only; do not perform its progression early.
- Return exactly {batch_size} ordered beats with the requested global numbers.
- Beat strings contain no numbering, labels, Markdown, comments, or --lora data.
- Return only JSON shaped exactly as {response_shape}.
{supplemental_text}

MAIN CHARACTER(S)
{subject_names}

CURRENT PHASE
{json.dumps(current_phase, ensure_ascii=False, indent=2)}

PREVIOUS PHASE END STATE
{previous_phase_end_state}

RECENT ACCEPTED BEATS
{previous_context}

NEXT PHASE - BOUNDARY ONLY
{next_phase_boundary}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---
""".strip(),
        },
    ]

def build_beat_instruction_review_messages(
    story,
    total_segments,
    beats,
    correction="",
    subject_information="",
    batch_start=None,
    batch_end=None,
    complete_beats=None,
    macro_arc=None,
    current_phase=None,
    phrase_exclusions=(),
):
    batch_start = 1 if batch_start is None else int(batch_start)
    batch_end = total_segments if batch_end is None else int(batch_end)
    batch_size = batch_end - batch_start + 1
    complete_beats = list(complete_beats or beats)
    macro_arc = macro_arc or {"phases": []}
    current_phase = current_phase or {}
    phrase_exclusions_text = format_phrase_exclusions_section(phrase_exclusions)
    correction_text = ""
    if correction:
        correction_text = (
            "\nThe previous compliance edit was structurally invalid: "
            f"{correction}\nReturn the complete corrected list again."
        )
    subject_text = ""
    if subject_information:
        subject_text = f"""

MAIN CHARACTERS FROM SUBJECTS.TXT
Preserve these main characters, their exact names, and their established
information in the corrected beats:
{subject_information}
"""
    complete_context = ""
    if len(complete_beats) > len(beats):
        outside_beats = "\n".join(
            f"Beat {number}: {beat}"
            for number, beat in enumerate(complete_beats, start=1)
            if number < batch_start or number > batch_end
        )
        complete_context = (
            "COMPLETE PLAN CONTEXT OUTSIDE THIS BATCH\n" + outside_beats
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a conservative story-beat compliance editor. Preserve "
                "the source rather than adding creative material. Return only "
                "the required JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Audit and, where necessary, minimally correct global beats {batch_start} through {batch_end}
so they follow every additional instruction exactly while retaining
exactly {batch_size} unique, chronological, forward-moving beats.

SOURCE AUTHORIZATION RULE
Every beat's primary WHAT must be authorized by SOURCE STORY, the CURRENT MACRO
PHASE, or explicit instructions. Specificity may clarify HOW an authorized event
is rendered; it may not add a new event, operation, transformation, target,
setup change, technology, dialogue, or reaction merely for detail.

If the source authorizes a broad category or all members of a category, concrete
members may be selected to expand that requirement. Anything outside that
category remains unauthorized unless the source separately requires it.

Also enforce the base story requirements:
- no beat may repeat or restage an earlier beat;
- each beat must center on one primary story event/progression step;
- source-established setup details remain unchanged unless the source requires a
  change;
- when the source requires a repeated paired process for each item, keep each
  pair locally complete before moving to unrelated progression unless the source
  explicitly requires a different order;
- the final beat must conclusively satisfy the source story's required ending
  without an unresolved essential action or cliffhanger.

Preserve chronological persistent state across the complete plan: after an
earlier beat definitively and permanently changes an item or structural feature,
later beats must begin from the resulting state and must not perform that same
irreversible transition again. Determine this semantically rather than by
matching individual words.

IMPORTANT: Use the beat budget to expand REQUIRED source events, not to invent
new events to fill space.

{subject_text}

MACRO STORY ARC
Preserve this plan while making any compliance edits:
{json.dumps(macro_arc, ensure_ascii=False, indent=2)}

CURRENT MACRO PHASE
{json.dumps(current_phase, ensure_ascii=False, indent=2)}
Keep the reviewed beats inside this phase's progression and preserve its
required_end_state. Its broad_progression is abstract guidance, not permission
to invent events that SOURCE STORY does not authorize.
Do not mention any MACRO STORY ARC location or character before the beat_start
of the phase where that location or characters_introduced entry first appears.
{phrase_exclusions_text}

CANDIDATE BEATS
{json.dumps({"beats": beats}, ensure_ascii=False, indent=2)}
{complete_context}
{correction_text}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---

Return only a JSON object shaped exactly as
{{"beats": [{{"beat_number": {batch_start}, "beat_text": "..."}}]}}.
""".strip(),
        },
    ]

def verify_subjects_in_beat_messages(messages, subject_information):
    """Refuse an LLM request that dropped parsed subjects.txt information."""
    subject_information = str(subject_information or "").strip()
    if not subject_information:
        return
    user_prompt = "\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "user"
    )
    if subject_information not in user_prompt:
        raise RuntimeError(
            "Parsed subjects.txt information was not included in the beat "
            "generation prompt; refusing to contact LM Studio."
        )


def _normalize_instruction_check_text(text):
    return re.sub(r"[*_`]", "", " ".join(str(text or "").split())).casefold()


def _normalize_macro_introduction_text(text):
    """Normalize prose for whole-token macro character/location matching."""

    return " ".join(
        re.findall(r"[^\W_]+", str(text or "").casefold(), flags=re.UNICODE)
    )


def _macro_introduction_aliases(value):
    normalized = _normalize_macro_introduction_text(value)
    if not normalized or normalized in {"n a", "none", "unknown"}:
        return set()
    aliases = {normalized}
    words = normalized.split()
    if len(words) > 1 and words[0] in {"a", "an", "the"}:
        aliases.add(" ".join(words[1:]))
    # Also add aliases for slash-separated alternatives, e.g. "X / Y".
    try:
        raw = str(value or "")
        parts = [p.strip() for p in re.split(r"\s*/\s*", raw) if p.strip()]
        for part in parts:
            part_norm = _normalize_macro_introduction_text(part)
            if part_norm:
                aliases.add(part_norm)
    except Exception:
        pass
    return aliases


def _macro_entity_is_mentioned(beat_text, aliases):
    normalized_beat = _normalize_macro_introduction_text(beat_text)
    padded_beat = f" {normalized_beat} "
    return any(f" {alias} " in padded_beat for alias in aliases)


def validate_generated_beat_macro_introductions(
    beats,
    macro_arc,
    beat_start=1,
):
    """Report characters or locations used before their macro phase begins."""

    if isinstance(beat_start, bool) or not isinstance(beat_start, int) or beat_start <= 0:
        raise ValueError("Macro introduction validation requires a positive beat_start.")
    phases = macro_arc.get("phases") if isinstance(macro_arc, dict) else None
    if not isinstance(phases, list) or not phases:
        raise ValueError("Macro introduction validation requires a macro arc.")

    introductions = {"character": {}, "location": {}}

    def register(kind, display_name, introduction_beat):
        aliases = _macro_introduction_aliases(display_name)
        if not aliases:
            return
        key = min(aliases, key=lambda alias: (len(alias), alias))
        existing = introductions[kind].get(key)
        if existing is None or introduction_beat < existing["beat_start"]:
            introductions[kind][key] = {
                "name": " ".join(str(display_name).split()),
                "aliases": aliases,
                "beat_start": introduction_beat,
            }

    for phase_number, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            raise ValueError(f"Macro arc phase {phase_number} must be an object.")
        introduction_beat = phase.get("beat_start")
        if (
            isinstance(introduction_beat, bool)
            or not isinstance(introduction_beat, int)
            or introduction_beat <= 0
        ):
            raise ValueError(
                f"Macro arc phase {phase_number} must have a positive beat_start."
            )
        characters = phase.get("characters_introduced")
        if not isinstance(characters, list):
            raise ValueError(
                f"Macro arc phase {phase_number} must have characters_introduced."
            )
        for character in characters:
            if not isinstance(character, str):
                raise ValueError(
                    f"Macro arc phase {phase_number} has an invalid character."
                )
            register("character", character, introduction_beat)
        location = phase.get("location")
        if not isinstance(location, str):
            raise ValueError(f"Macro arc phase {phase_number} must have a location.")
        register("location", location, introduction_beat)

    issues = []
    for offset, beat in enumerate(beats):
        beat_number = beat_start + offset
        for kind in ("location", "character"):
            for introduction in introductions[kind].values():
                allowed_from = introduction["beat_start"]
                if beat_number >= allowed_from:
                    continue
                if _macro_entity_is_mentioned(beat, introduction["aliases"]):
                    issues.append(
                        f"Beat {beat_number} introduces future {kind} "
                        f"{introduction['name']!r} before its macro phase begins "
                        f"at beat {allowed_from}."
                    )
    return list(dict.fromkeys(issues))


def validate_generated_beat_instructions(beats, beat_instructions):
    """Validate common explicit, mechanically checkable beat constraints."""
    instructions = str(beat_instructions or "")
    if not instructions.strip():
        return []

    normalized_beats = [
        _normalize_instruction_check_text(beat)
        for beat in beats
    ]
    combined = "\n".join(normalized_beats)
    issues = []
    quote = r'["\u201c](?P<phrase>.*?)["\u201d]'
    placement_patterns = (
        re.compile(
            rf"(?is)in\s+beat\s+(?P<beat>\d+)[^.\n]{{0,240}}?"
            rf"exact\s+phrase\s+{quote}"
        ),
        re.compile(
            rf"(?is)exact\s+phrase\s+{quote}[^.\n]{{0,240}}?"
            rf"in\s+beat\s+(?P<beat>\d+)"
        ),
    )
    placed_phrases = set()
    for pattern in placement_patterns:
        for match in pattern.finditer(instructions):
            phrase = match.group("phrase")
            target = int(match.group("beat"))
            key = _normalize_instruction_check_text(phrase)
            if (key, target) in placed_phrases:
                continue
            placed_phrases.add((key, target))
            if not 1 <= target <= len(normalized_beats):
                issues.append(
                    f"Instruction targets beat {target}, but only "
                    f"{len(normalized_beats)} beats exist."
                )
                continue
            counts = [beat.count(key) for beat in normalized_beats]
            if counts[target - 1] != 1 or sum(counts) != 1:
                issues.append(
                    f"Exact phrase {phrase!r} must appear once in beat "
                    f"{target} and nowhere else."
                )

    all_exact_phrases = re.findall(
        r'(?is)exact\s+phrase\s+["\u201c](.*?)["\u201d]',
        instructions,
    )
    placed_keys = {key for key, _ in placed_phrases}
    for phrase in all_exact_phrases:
        key = _normalize_instruction_check_text(phrase)
        if key not in placed_keys and key not in combined:
            issues.append(f"Required exact phrase {phrase!r} is missing.")

    for banned in re.findall(
        r'(?is)do\s+not\s+use\s+the\s+word\s+["\u201c](.*?)["\u201d]',
        instructions,
    ):
        key = _normalize_instruction_check_text(banned)
        if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", combined):
            issues.append(f"Prohibited word {banned!r} appears in the beats.")

    ending_match = re.search(
        r'(?is)(?:entire\s+story|final\s+beat)\s+must\s+end\s+with\s+'
        r'(?:the\s+)?exact\s+sentence\s+["\u201c](.*?)["\u201d]',
        instructions,
    )
    if ending_match:
        ending = ending_match.group(1)
        if not normalized_beats[-1].endswith(
            _normalize_instruction_check_text(ending)
        ):
            issues.append(
                f"Final beat must end with exact sentence {ending!r}."
            )
    return list(dict.fromkeys(issues))


def validate_generated_beat_exclusions(beats, phrase_exclusions, beat_start=1):
    """Report excluded whole words or phrases found in beat text."""
    if (
        isinstance(beat_start, bool)
        or not isinstance(beat_start, int)
        or beat_start <= 0
    ):
        raise ValueError("Beat exclusion validation requires a positive beat_start.")

    exclusions = []
    seen = set()
    for raw_exclusion in phrase_exclusions or []:
        exclusion = " ".join(str(raw_exclusion).split()).strip()
        key = exclusion.casefold()
        if not exclusion or key in seen:
            continue
        exclusions.append((exclusion, key))
        seen.add(key)

    issues = []
    for offset, raw_beat in enumerate(beats or []):
        beat = " ".join(str(raw_beat).split()).casefold()
        for exclusion, key in exclusions:
            parts = key.split(" ")
            expression = r"\s+".join(re.escape(part) for part in parts)
            if key[0].isalnum() or key[0] == "_":
                expression = r"(?<!\w)" + expression
            if key[-1].isalnum() or key[-1] == "_":
                expression += r"(?!\w)"
            if re.search(expression, beat):
                issues.append(
                    f"Beat {beat_start + offset} contains prohibited word or "
                    f"phrase {exclusion!r}."
                )
    return issues


def parse_generated_beats(
    raw_result,
    total_segments,
    formatter=None,
    expected_start=1,
    enforce_content_validation=True,
    phrase_exclusions=(),
):
    if total_segments <= 0:
        raise ValueError("Beat generation requires at least one segment.")
    if (
        isinstance(expected_start, bool)
        or not isinstance(expected_start, int)
        or expected_start <= 0
    ):
        raise ValueError("Beat generation requires a positive expected_start.")

    formatter = formatter or ACTIVE_FORMATTER

    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError:
            lines = []
            for raw_line in candidate.splitlines():
                line = raw_line.strip()
                if not line or re.fullmatch(r"(?i)beats?\s*:", line):
                    continue
                line = re.sub(
                    r"^(?:[-*\u2022]\s+|(?:B\s*0*)?\d+\s*[.):\-]\s*)",
                    "",
                    line,
                    flags=re.IGNORECASE,
                ).strip()
                if line:
                    lines.append(line)
            candidate = {"beats": lines}

    if not isinstance(candidate, dict) or not isinstance(
        candidate.get("beats"), list
    ):
        raise ValueError("The LLM response must contain a JSON 'beats' array.")
    if len(candidate["beats"]) != total_segments:
        raise ValueError(
            f"Expected exactly {total_segments} generated beats, received "
            f"{len(candidate['beats'])}."
        )

    beats = []
    for index, raw_beat in enumerate(candidate["beats"], start=1):
        expected_beat_number = expected_start + index - 1
        if isinstance(raw_beat, dict):
            if set(raw_beat) != {"beat_number", "beat_text"}:
                raise ValueError(
                    f"Generated beat {expected_beat_number} must contain exactly "
                    "beat_number and beat_text."
                )
            returned_beat_number = raw_beat["beat_number"]
            if (
                isinstance(returned_beat_number, bool)
                or not isinstance(returned_beat_number, int)
                or returned_beat_number != expected_beat_number
            ):
                raise ValueError(
                    f"Generated beat {index} must have beat_number "
                    f"{expected_beat_number}."
                )
            raw_beat = raw_beat["beat_text"]
        if not isinstance(raw_beat, str):
            raise ValueError(
                f"Generated beat {expected_beat_number} must have text in "
                "beat_text."
            )
        beat = formatter.sanitize_generated_text(raw_beat)
        beat = " ".join(beat.split()).strip()
        beat = re.sub(
            r"^(?:[-*\u2022]\s+|(?:B\s*0*)?\d+\s*[.):\-]\s*)",
            "",
            beat,
            flags=re.IGNORECASE,
        ).strip()
        if not beat:
            raise ValueError(f"Generated beat {expected_beat_number} is empty.")
        if "--lora" in beat.lower():
            raise ValueError(
                f"Generated beat {expected_beat_number} contains unsupported "
                "--lora metadata."
            )
        if enforce_content_validation and beat.endswith(":"):
            raise ValueError(
                f"Generated beat {expected_beat_number} is incomplete because it "
                "ends with a colon."
            )
        #if not beat_is_single_complete_sentence(beat):
        #    raise ValueError(
        #        f"Generated beat {expected_beat_number} must contain exactly one "
        #        "complete sentence."
        #    )
        beats.append(beat)

    normalized = [beat.casefold() for beat in beats]
    if enforce_content_validation and len(set(normalized)) != len(normalized):
        raise ValueError("Generated beats must not contain duplicates.")
    exclusion_issues = validate_generated_beat_exclusions(
        beats,
        phrase_exclusions,
        beat_start=expected_start,
    )
    if exclusion_issues:
        raise ValueError(" ".join(exclusion_issues))
    return beats


_BEAT_SENTENCE_BREAK = re.compile(
    r"(?P<ending>[.!?]+)[\"'\u2019\u201d)]*\s+(?P<next>[A-Za-z0-9])"
)
_BEAT_ABBREVIATIONS = {
    "dr",
    "etc",
    "jr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "sr",
    "st",
    "vs",
}


def _iter_beat_sentence_breaks(beat):
    """Yield top-level sentence breaks without splitting common titles."""

    beat = str(beat or "").strip()
    for match in _BEAT_SENTENCE_BREAK.finditer(beat):
        if match.group("next").islower():
            # This covers punctuation inside dialogue followed by narration,
            # such as: She shouts "Run!" before opening the door.
            continue
        if match.group("ending") == ".":
            prefix = beat[:match.end("ending")]
            token_match = re.search(r"([A-Za-z]+)\.$", prefix)
            if token_match and token_match.group(1).casefold() in _BEAT_ABBREVIATIONS:
                continue
            if re.search(r"(?:\b[A-Z]\.){1,}$", prefix):
                continue
        yield match


def beat_contains_multiple_sentences(beat):
    """Detect a second top-level sentence without splitting common titles."""

    return next(_iter_beat_sentence_breaks(beat), None) is not None


def beat_is_one_to_three_complete_sentences(beat):
    """Accept a complete beat containing no more than three sentences."""

    beat = str(beat or "").strip()
    has_terminal_punctuation = bool(
        re.search(r"[.!?]+[\"'\u2019\u201d)]*$", beat)
    )
    internal_breaks = sum(1 for _ in _iter_beat_sentence_breaks(beat))
    return has_terminal_punctuation and internal_breaks < 3


def beat_is_single_complete_sentence(beat):
    """Return whether a beat is exactly one complete sentence."""

    beat = str(beat or "").strip()
    has_terminal_punctuation = bool(
        re.search(r"[.!?]+[\"'\u2019\u201d)]*$", beat)
    )
    return has_terminal_punctuation and not beat_contains_multiple_sentences(beat)


def print_generated_beats(beats):
    print()
    print("Generated story beats:")
    number_width = len(str(len(beats)))
    for index, beat in enumerate(beats, start=1):
        print(f"  {index:>{number_width}}. {beat}")
    print()


def get_story_arc_path(beats_path=BEATS_FILE, story_arc_path=None):
    """Return the explicit arc path or the story_arc.json beside beats.txt."""
    if story_arc_path is not None:
        return os.path.abspath(os.fspath(story_arc_path))
    return os.path.join(
        os.path.dirname(os.path.abspath(os.fspath(beats_path))),
        "story_arc.json",
    )


def get_story_arc_hash_path(story_arc_path=STORY_ARC_FILE):
    """Return the SHA-256 sidecar path for a persisted story arc."""
    return os.fspath(story_arc_path) + ".sha256"


def hash_story_arc_source(source_text):
    """Return the SHA-256 digest for the story source used to plan an arc."""
    return hashlib.sha256(str(source_text or "").encode("utf-8")).hexdigest()


def save_story_arc(macro_arc, source_text, path=STORY_ARC_FILE):
    """Atomically overwrite an arc and its story-source SHA-256 sidecar."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".story_arc_",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as arc_file:
            json.dump(macro_arc, arc_file, ensure_ascii=False, indent=2)
            arc_file.write("\n")
            arc_file.flush()
            os.fsync(arc_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

    hash_path = get_story_arc_hash_path(path)
    descriptor, temporary_hash_path = tempfile.mkstemp(
        prefix=".story_arc_hash_",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as hash_file:
            hash_file.write(hash_story_arc_source(source_text) + "\n")
            hash_file.flush()
            os.fsync(hash_file.fileno())
        os.replace(temporary_hash_path, hash_path)
    finally:
        if os.path.exists(temporary_hash_path):
            os.remove(temporary_hash_path)


def load_story_arc(path, total_segments, source_text):
    """Load an arc only when its sidecar matches the current story source."""
    raw_arc = load_text_file(path, required=False)
    if not raw_arc:
        return None
    hash_path = get_story_arc_hash_path(path)
    stored_hash = load_text_file(hash_path, required=False).casefold()
    expected_hash = hash_story_arc_source(source_text)
    if (
        re.fullmatch(r"[0-9a-f]{64}", stored_hash) is None
        or not secrets.compare_digest(stored_hash, expected_hash)
    ):
        print(
            f"Ignoring {path} because {hash_path} is missing or does not match "
            "the current story.txt source; a new story arc will be generated.",
            flush=True,
        )
        return None
    try:
        return parse_beat_arc_plan(raw_arc, total_segments)
    except ValueError as error:
        raise ValueError(f"Invalid story arc in {path}: {error}") from error


def phase_characters_introduced_for_beat(macro_arc, beat_number):
    """Return the characters introduced by the phase containing a beat."""
    if isinstance(beat_number, bool):
        return []
    try:
        beat_number = int(beat_number)
    except (TypeError, ValueError):
        return []
    phases = macro_arc.get("phases", []) if isinstance(macro_arc, dict) else []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        beat_start = phase.get("beat_start")
        beat_end = phase.get("beat_end")
        if (
            isinstance(beat_start, int)
            and not isinstance(beat_start, bool)
            and isinstance(beat_end, int)
            and not isinstance(beat_end, bool)
            and beat_start <= beat_number <= beat_end
        ):
            characters = phase.get("characters_introduced", [])
            return list(characters) if isinstance(characters, list) else []
    return []


def save_generated_beats(
    beats,
    path=BEATS_FILE,
    lora_directive="",
    macro_arc=None,
):
    lora_directive = str(lora_directive or "").strip()
    if lora_directive:
        directive_match = LORA_DIRECTIVE_PATTERN.fullmatch(lora_directive)
        if directive_match is None:
            raise ValueError(
                f"Invalid file-level LoRA directive: {lora_directive!r}."
            )
        try:
            parse_lora_spec(directive_match.group("spec"))
        except argparse.ArgumentTypeError as error:
            raise ValueError(
                f"Invalid file-level LoRA directive: {lora_directive!r}."
            ) from error
    phase_starts = {}
    if macro_arc is not None:
        for phase_batch in build_phase_generation_batches(macro_arc):
            phase = phase_batch["phase"]
            phase_starts.setdefault(
                int(phase["beat_start"]),
                int(phase["phase_number"]),
            )
    saved_beats = []
    for beat_number, beat in enumerate(beats, start=1):
        if beat_number in phase_starts:
            saved_beats.append(f"# Phase {phase_starts[beat_number]}")
        saved_beats.append(
            f"{beat_number}. {beat} {lora_directive}"
            if lora_directive
            else f"{beat_number}. {beat}"
        )
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".generated_beats_",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as beat_file:
            beat_file.write("\n".join(saved_beats) + "\n")
            beat_file.flush()
            os.fsync(beat_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def generate_beats_from_story(
    story,
    total_segments,
    path=BEATS_FILE,
    llm_request=None,
    content_attempts=None,
    history_metadata=None,
    beat_instructions="",
    instruction_review_attempts=None,
    subject_information="",
    lora_directive="",
    audit_attempts=None,
    repair_response_attempts=None,
    repair_rounds=None,
    story_arc_path=None,
    story_arc_source=None,
    phrase_exclusions=(),
    reuse_story_arc=True,
    gen_rules="",
):
    if llm_request is None:
        llm_request = ask_llm
    if not str(story or "").strip():
        raise ValueError("Cannot generate story beats from an empty story.")
    # These former configurable attempt-limit arguments remain accepted so
    # existing callers do not break. Starting with the tenth phase-generation
    # response, the first structurally usable beat list is accepted even when
    # content validation still fails. Post-generation phase LLM validation and
    # repair are disabled; local structural/content checks and the later audit
    # behavior remain unchanged.
    del (
        content_attempts,
        instruction_review_attempts,
        audit_attempts,
        repair_response_attempts,
        repair_rounds,
    )
    story_arc_path = get_story_arc_path(path, story_arc_path)
    if story_arc_source is None:
        story_arc_source = story
    saved_macro_arc = None
    if reuse_story_arc:
        saved_macro_arc = load_story_arc(
            story_arc_path,
            total_segments,
            story_arc_source,
        )

    def request_macro_arc(correction="", combined_attempt=1, max_attempts=10):
        """Request a macro arc from LLM; returns (macro_arc, success).
        
        Args:
            correction: Initial correction message or empty string
            combined_attempt: Current attempt in the combined macro_arc + fidelity loop
            max_attempts: Maximum attempts for this macro arc generation
            
        Returns:
            (macro_arc, success) tuple. Success is False if max_attempts reached.
        """
        last_error = None
        attempt = 0
        last_macro_arc = None
        
        while attempt < max_attempts:
            attempt += 1
            print(
                f"Requesting global beat macro arc (combined attempt {combined_attempt}, "
                f"response attempt {attempt}/{max_attempts}).",
                flush=True,
            )
            messages = build_beat_arc_plan_messages(
                story,
                total_segments,
                subject_information=subject_information,
                correction=correction if attempt == 1 else str(last_error),
            )
            verify_subjects_in_beat_messages(
                messages,
                _format_beat_arc_subject_names(subject_information),
            )
            raw_arc = llm_request(
                messages,
                response_format=build_beat_arc_response_format(total_segments),
                history_metadata={
                    **(history_metadata or {}),
                    "purpose": "beat_arc_plan",
                    "attempt": attempt,
                    "total_segments": total_segments,
                },
                **BEAT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                print(raw_arc, flush=True)
                macro_arc = parse_beat_arc_plan(raw_arc, total_segments)
                save_story_arc(macro_arc, story_arc_source, story_arc_path)
                print(f"Saved story arc to {story_arc_path}.", flush=True)
                return (macro_arc, True)
            except ValueError as error:
                last_error = error
                last_macro_arc = None  # Only save if we get a parseable result
                print(
                    "LM Studio returned an invalid macro arc; requesting a "
                    f"corrected arc: {last_error}"
                )
        
        # Max attempts reached; return None as best effort
        print(
            f"Global beat macro arc generation reached maximum attempts ({max_attempts}); "
            "accepting best effort result.",
            flush=True,
        )
        return (None, False)

    def request_macro_arc_fidelity(macro_arc, combined_attempt, max_attempts=10):
        """Request fidelity check for a macro arc; returns (fidelity, success).
        
        Args:
            macro_arc: The macro arc to validate
            combined_attempt: Current attempt in the combined macro_arc + fidelity loop
            max_attempts: Maximum attempts for parsing fidelity response
            
        Returns:
            (fidelity_dict, success) tuple. Success is False if max_attempts reached.
        """
        last_error = None
        response_attempt = 0
        last_fidelity = None
        
        while response_attempt < max_attempts:
            response_attempt += 1
            print(
                f"Requesting macro-arc fidelity check (combined attempt {combined_attempt}, "
                f"response attempt {response_attempt}/{max_attempts}).",
                flush=True,
            )
            messages = build_beat_arc_fidelity_messages(
                story,
                macro_arc,
                subject_information=subject_information,
            )
            verify_subjects_in_beat_messages(
                messages,
                subject_information,
            )
            if last_error:
                messages[-1]["content"] += (
                    "\n\nYOUR PREVIOUS FIDELITY RESPONSE WAS STRUCTURALLY INVALID\n"
                    f"{last_error}\nReturn the complete fidelity JSON again."
                )
            raw_fidelity = llm_request(
                messages,
                response_format=build_beat_arc_fidelity_response_format(),
                history_metadata={
                    **(history_metadata or {}),
                    "purpose": "beat_arc_fidelity",
                    "attempt": combined_attempt,
                    "response_attempt": response_attempt,
                    "total_segments": total_segments,
                },
                **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                fidelity = parse_beat_arc_fidelity(raw_fidelity)
                return (fidelity, True)
            except ValueError as error:
                last_error = error
                last_fidelity = None  # Only track if we get valid fidelity
                print(
                    "LM Studio returned an invalid macro-arc fidelity response; "
                    f"requesting another response: {last_error}"
                )
        
        # Max attempts reached; return empty fidelity as best effort
        print(
            f"Macro-arc fidelity check parsing reached maximum attempts ({max_attempts}); "
            "accepting best effort result.",
            flush=True,
        )
        return ({"valid": False, "issues": ["Fidelity parsing failed after max attempts"]}, False)

    def request_valid_macro_arc(correction="", max_attempts=10):
        """Request a valid macro arc with fidelity checks; returns (macro_arc, success).
        
        Combines macro arc generation and fidelity validation with a shared attempt limit.
        Both macro arc failures and fidelity check failures count toward the same limit.
        
        Args:
            correction: Initial correction message or empty string
            max_attempts: Maximum combined attempts for macro_arc + fidelity validation
            
        Returns:
            (macro_arc, success) tuple. Success is True only if fidelity passes.
            If max_attempts reached, returns (last_macro_arc, False) as best effort.
        """
        fidelity_correction = correction
        combined_attempt = 0
        last_macro_arc = None
        
        while combined_attempt < max_attempts:
            combined_attempt += 1
            print(
                f"\n--- Combined macro arc generation attempt {combined_attempt}/{max_attempts} ---",
                flush=True,
            )
            
            # Request macro arc
            macro_arc, arc_success = request_macro_arc(
                fidelity_correction, 
                combined_attempt=combined_attempt,
                max_attempts=3  # Allow 3 parsing attempts per combined attempt
            )
            
            if not arc_success or macro_arc is None:
                print(
                    f"Macro arc generation failed on combined attempt {combined_attempt}; "
                    "requesting another macro arc.",
                    flush=True,
                )
                fidelity_correction = (
                    "The previous macro arc generation attempt failed; "
                    "please generate a new macro arc."
                )
                continue
            
            # Check fidelity
            fidelity, fidelity_success = request_macro_arc_fidelity(
                macro_arc, 
                combined_attempt=combined_attempt,
                max_attempts=3  # Allow 3 parsing attempts per combined attempt
            )
            
            if fidelity_success and fidelity.get("valid"):
                print(
                    f"Macro-arc fidelity check passed on combined attempt "
                    f"{combined_attempt}.",
                    flush=True,
                )
                return (macro_arc, True)
            
            # Fidelity failed; prepare correction for next iteration
            last_macro_arc = macro_arc
            issues = fidelity.get("issues", ["Unknown fidelity issue"])
            fidelity_correction = (
                "The low-temperature macro fidelity check rejected the previous "
                "arc: " + " ".join(issues)
            )
            print(
                f"Macro-arc fidelity check failed on combined attempt "
                f"{combined_attempt}; requesting another macro arc: "
                + " ".join(issues),
                flush=True,
            )
        
        # Max combined attempts reached
        print(
            f"Macro arc validation reached maximum combined attempts ({max_attempts}); "
            "accepting best effort result.",
            flush=True,
        )
        return (last_macro_arc, False)

    def request_phase_validation(
        phase_beats,
        macro_arc,
        current_phase,
        generation_attempt,
        previous_beats,
    ):
        phases = macro_arc["phases"]
        phase_index = current_phase["phase_number"] - 1
        previous_phase = phases[phase_index - 1] if phase_index > 0 else None
        next_phase = (
            phases[phase_index + 1]
            if phase_index + 1 < len(phases)
            else None
        )
        response_attempt = 0
        last_error = None
        while True:
            response_attempt += 1
            messages = build_beat_phase_validation_messages(
                phase_beats,
                current_phase,
                next_phase=next_phase,
                previous_phase=previous_phase,
                previous_beat=previous_beats[-1] if previous_beats else None,
                previous_beats=previous_beats,
            )
            if last_error:
                messages[-1]["content"] += (
                    "\n\nYOUR PREVIOUS VALIDATION RESPONSE WAS STRUCTURALLY "
                    "INVALID\n"
                    f"{last_error}\nReturn the complete validation JSON again."
                )
            raw_validation = llm_request(
                messages,
                response_format=build_beat_phase_validation_response_format(
                    current_phase["beat_start"],
                    current_phase["beat_end"],
                ),
                history_metadata={
                    **(history_metadata or {}),
                    "purpose": "beat_phase_validation",
                    "attempt": generation_attempt,
                    "response_attempt": response_attempt,
                    "total_segments": total_segments,
                    "batch_start": current_phase["beat_start"],
                    "batch_end": current_phase["beat_end"],
                    "phase_number": current_phase["phase_number"],
                },
                **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                return parse_beat_phase_validation(
                    raw_validation,
                    beat_start=current_phase["beat_start"],
                    beat_end=current_phase["beat_end"],
                )
            except ValueError as error:
                last_error = error
                print(
                    "LM Studio returned an invalid phase-validation response; "
                    f"requesting another response: {last_error}",
                    flush=True,
                )

    def request_phase_repair(
        phase_beats,
        macro_arc,
        current_phase,
        validation,
        previous_beats,
        generation_attempt,
        repair_round,
    ):
        phases = macro_arc["phases"]
        phase_index = current_phase["phase_number"] - 1
        previous_phase = phases[phase_index - 1] if phase_index > 0 else None
        next_phase = (
            phases[phase_index + 1]
            if phase_index + 1 < len(phases)
            else None
        )
        repair_ranges = beat_phase_validation_repair_ranges(validation)
        repair_ids = beat_ids_for_repair_ranges(repair_ranges)
        response_attempt = 0
        correction = ""
        while True:
            response_attempt += 1
            print(
                f"Requesting targeted repair for phase "
                f"{current_phase['phase_number']} Beat ID"
                f"{'' if len(repair_ids) == 1 else 's'} "
                + ", ".join(str(beat_id) for beat_id in repair_ids)
                + f" (repair round {repair_round}, response attempt "
                f"{response_attempt}; 10 times then best effort or Ctrl+Q).",
                flush=True,
            )
            messages = build_beat_phase_repair_messages(
                phase_beats,
                current_phase,
                validation,
                next_phase=next_phase,
                previous_phase=previous_phase,
                previous_beats=previous_beats,
                correction=correction,
                phrase_exclusions=phrase_exclusions,
            )
            raw_repair = llm_request(
                messages,
                response_format=build_beat_plan_repair_response_format(
                    repair_ranges,
                ),
                history_metadata={
                    **(history_metadata or {}),
                    "purpose": "beat_phase_repair",
                    "attempt": generation_attempt,
                    "repair_round": repair_round,
                    "response_attempt": response_attempt,
                    "total_segments": total_segments,
                    "batch_start": current_phase["beat_start"],
                    "batch_end": current_phase["beat_end"],
                    "phase_number": current_phase["phase_number"],
                    "repair_beat_ids": repair_ids,
                },
                **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                replacements = parse_beat_plan_repair(
                    raw_repair,
                    repair_ranges,
                )
                current_prefix = list(previous_beats) + list(phase_beats)
                repaired_prefix = splice_beat_plan_repair(
                    current_prefix,
                    repair_ranges,
                    replacements,
                )
                repaired_phase = repaired_prefix[
                    current_phase["beat_start"] - 1:current_phase["beat_end"]
                ]
                introduction_issues = validate_generated_beat_macro_introductions(
                    repaired_phase,
                    macro_arc,
                    beat_start=current_phase["beat_start"],
                )
                if introduction_issues:
                    raise ValueError(
                        "Targeted phase repair violates macro introduction timing: "
                        + " ".join(introduction_issues)
                    )
                exclusion_issues = validate_generated_beat_exclusions(
                    repaired_phase,
                    phrase_exclusions,
                    beat_start=current_phase["beat_start"],
                )
                if exclusion_issues:
                    raise ValueError(" ".join(exclusion_issues))
                return repaired_phase
            except ValueError as error:
                correction = str(error)
                print(
                    "LM Studio returned an invalid targeted phase repair; "
                    f"requesting another repair response: {correction}",
                    flush=True,
                )

    def generate_batches(macro_arc, audit_correction=""):
        generated = []
        phase_batches = build_phase_generation_batches(macro_arc)
        for phase_batch in phase_batches:
            current_phase = phase_batch["phase"]
            batch_start = phase_batch["batch_start"]
            batch_end = phase_batch["batch_end"]
            batch_size = batch_end - batch_start + 1
            print(
                f"Generating macro phase {current_phase['phase_number']} "
                f"({batch_size} beats, global beats {batch_start}-{batch_end} "
                f"of {total_segments}).",
                flush=True,
            )
            response_format = build_beats_response_format(
                batch_size,
                beat_start=batch_start,
            )
            correction = ""
            last_error = None
            batch_beats = None
            attempt = 0
            while True:
                attempt += 1
                attempt_label = (
                    f"{attempt}/{BEAT_PHASE_GENERATION_ATTEMPTS}"
                    if attempt <= BEAT_PHASE_GENERATION_ATTEMPTS
                    else (
                        f"{attempt}; waiting for the next structurally usable "
                        "beat list"
                    )
                )
                print(
                    f"Requesting beats for phase {current_phase['phase_number']} "
                    f"(attempt {attempt_label}).",
                    flush=True,
                )
                messages = build_beat_generation_messages(
                    story,
                    total_segments,
                    correction,
                    beat_instructions,
                    subject_information,
                    batch_start=batch_start,
                    batch_end=batch_end,
                    previous_beats=generated,
                    macro_arc=macro_arc,
                    current_phase=current_phase,
                    audit_correction=audit_correction,
                    phrase_exclusions=phrase_exclusions,
                    gen_rules=gen_rules,
                )
                verify_subjects_in_beat_messages(
                    messages,
                    _format_beat_arc_subject_names(subject_information),
                )
                raw_result = llm_request(
                    messages,
                    response_format=response_format,
                    history_metadata={
                        **(history_metadata or {}),
                        "purpose": "beat_generation",
                        "attempt": attempt,
                        "total_segments": total_segments,
                        "batch_start": batch_start,
                        "batch_end": batch_end,
                        "phase_number": current_phase["phase_number"],
                    },
                    **BEAT_LLM_SAMPLING_PARAMETERS,
                )
                try:
                    batch_beats = parse_generated_beats(
                        raw_result,
                        batch_size,
                        expected_start=batch_start,
                        phrase_exclusions=phrase_exclusions,
                    )
                    prior_normalized = {
                        " ".join(previous.split()).casefold()
                        for previous in generated
                    }
                    duplicate = next(
                        (
                            beat for beat in batch_beats
                            if " ".join(beat.split()).casefold() in prior_normalized
                        ),
                        None,
                    )
                    if duplicate:
                        raise ValueError(
                            "Generated batch repeats an earlier beat: "
                            f"{duplicate!r}."
                        )
                    introduction_issues = (
                        validate_generated_beat_macro_introductions(
                            batch_beats,
                            macro_arc,
                            beat_start=batch_start,
                        )
                    )
                    if introduction_issues:
                        raise ValueError(
                            "Generated phase violates macro introduction timing: "
                            + " ".join(introduction_issues)
                        )
                except ValueError as error:
                    last_error = error
                    correction = str(error)
                    if attempt >= BEAT_PHASE_GENERATION_ATTEMPTS:
                        try:
                            batch_beats = parse_generated_beats(
                                raw_result,
                                batch_size,
                                expected_start=batch_start,
                                enforce_content_validation=False,
                                phrase_exclusions=phrase_exclusions,
                            )
                        except ValueError as fallback_error:
                            batch_beats = None
                            print(
                                f"Phase {current_phase['phase_number']} response "
                                f"on attempt {attempt} is not structurally usable: "
                                f"{fallback_error} Continuing until the next usable "
                                "beat list is returned.",
                                flush=True,
                            )
                            continue
                        print(
                            f"Phase {current_phase['phase_number']} still failed "
                            f"beat-list validation on attempt {attempt}; using the "
                            f"beats returned on that attempt: {last_error}",
                            flush=True,
                        )
                    else:
                        batch_beats = None
                        print(
                            "LLM returned an invalid beat list; requesting a "
                            f"corrected list: {last_error}"
                        )
                        continue
                if not ENABLE_BEAT_PHASE_LLM_VALIDATION:
                    break
                phase_repair_round = 0
                passed_phase_beat_ids = set()
                while True:
                    phase_validation = request_phase_validation(
                        batch_beats,
                        macro_arc,
                        current_phase,
                        attempt,
                        generated,
                    )
                    phase_validation, ignored_issues = (
                        reconcile_beat_phase_validation(
                            phase_validation,
                            batch_start,
                            batch_end,
                            passed_phase_beat_ids,
                        )
                    )
                    if ignored_issues:
                        ignored_ids = sorted({
                            issue["beat_id"] for issue in ignored_issues
                        })
                        print(
                            "Ignoring new validation claims against previously "
                            "accepted, unchanged Beat ID"
                            f"{'' if len(ignored_ids) == 1 else 's'} "
                            + ", ".join(str(beat_id) for beat_id in ignored_ids)
                            + ".",
                            flush=True,
                        )
                    if phase_validation["valid"]:
                        break
                    if phase_repair_round >= BEAT_PHASE_REPAIR_ROUNDS:
                        remaining_ids = sorted({
                            issue["beat_id"]
                            for issue in phase_validation["issues"]
                        })
                        print(
                            f"Phase {current_phase['phase_number']} reached the "
                            f"{BEAT_PHASE_REPAIR_ROUNDS}-round targeted-repair "
                            "limit; accepting the structurally valid beats returned "
                            "by round 10 without requesting another repair. Final "
                            "validation still disputed Beat ID"
                            f"{'' if len(remaining_ids) == 1 else 's'} "
                            + ", ".join(str(beat_id) for beat_id in remaining_ids)
                            + ".",
                            flush=True,
                        )
                        break
                    phase_repair_round += 1
                    issue_summary = " ".join(
                        f"Beat {issue['beat_id']}: {issue['problem']}"
                        for issue in phase_validation["issues"]
                    )
                    print(
                        f"Phase {current_phase['phase_number']} failed "
                        "post-generation validation; repairing only its "
                        "violating beats: "
                        + issue_summary,
                        flush=True,
                    )
                    batch_beats = request_phase_repair(
                        batch_beats,
                        macro_arc,
                        current_phase,
                        phase_validation,
                        generated,
                        attempt,
                        phase_repair_round,
                    )
                break
            generated.extend(batch_beats)
            print(
                f"Accepted macro phase {current_phase['phase_number']}; collected "
                f"{len(generated)}/{total_segments} beats.",
                flush=True,
            )
        return generated

    def review_explicit_instructions(beats, macro_arc):
        if not beat_instructions:
            return beats
        original_beats = list(beats)
        phase_batches = build_phase_generation_batches(macro_arc)
        compliance_error = ""
        review_pass = 0
        while True:
            review_pass += 1
            reviewed_beats = []
            for phase_batch in phase_batches:
                current_phase = phase_batch["phase"]
                batch_start = phase_batch["batch_start"]
                batch_end = phase_batch["batch_end"]
                batch_size = batch_end - batch_start + 1
                print(
                    f"Reviewing beat batch {batch_start}-{batch_end} of "
                    f"{total_segments} ({batch_size} beats).",
                    flush=True,
                )
                candidate_batch = original_beats[batch_start - 1:batch_end]
                review_error = compliance_error
                reviewed_batch = None
                review_attempt = 0
                while True:
                    review_attempt += 1
                    print(
                        f"Requesting beat-instruction review for batch "
                        f"{batch_start}-{batch_end} (pass {review_pass}, attempt "
                        f"{review_attempt}; 10 times then best effort or Ctrl+Q).",
                        flush=True,
                    )
                    review_messages = build_beat_instruction_review_messages(
                        story,
                        total_segments,
                        candidate_batch,
                        review_error,
                        subject_information,
                        batch_start=batch_start,
                        batch_end=batch_end,
                        complete_beats=original_beats,
                        macro_arc=macro_arc,
                        current_phase=current_phase,
                        phrase_exclusions=phrase_exclusions,
                    )
                    verify_subjects_in_beat_messages(
                        review_messages,
                        subject_information,
                    )
                    reviewed_raw = llm_request(
                        review_messages,
                        response_format=build_beats_response_format(
                            batch_size,
                            beat_start=batch_start,
                        ),
                        history_metadata={
                            **(history_metadata or {}),
                            "purpose": "beat_instruction_review",
                            "attempt": review_attempt,
                            "review_pass": review_pass,
                            "total_segments": total_segments,
                            "batch_start": batch_start,
                            "batch_end": batch_end,
                            "phase_number": current_phase["phase_number"],
                        },
                        **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
                    )
                    try:
                        reviewed_batch = parse_generated_beats(
                            reviewed_raw,
                            batch_size,
                            expected_start=batch_start,
                            phrase_exclusions=phrase_exclusions,
                        )
                        introduction_issues = (
                            validate_generated_beat_macro_introductions(
                                reviewed_batch,
                                macro_arc,
                                beat_start=batch_start,
                            )
                        )
                        if introduction_issues:
                            raise ValueError(
                                "Reviewed phase violates macro introduction timing: "
                                + " ".join(introduction_issues)
                            )
                    except ValueError as error:
                        review_error = str(error)
                        print(
                            "LM Studio returned an invalid instruction-compliance "
                            f"edit; requesting another edit: {error}"
                        )
                        continue
                    break
                reviewed_beats.extend(reviewed_batch)
                print(
                    f"Accepted reviewed beat batch {batch_start}-{batch_end}; "
                    f"collected {len(reviewed_beats)}/{total_segments} reviewed "
                    "beats.",
                    flush=True,
                )
            reviewed_beats = parse_generated_beats(
                {"beats": reviewed_beats},
                total_segments,
                phrase_exclusions=phrase_exclusions,
            )
            compliance_issues = validate_generated_beat_instructions(
                reviewed_beats,
                beat_instructions,
            )
            if not compliance_issues:
                return reviewed_beats
            compliance_error = (
                "The prior complete review still violated explicit "
                "beat_instructions: " + " ".join(compliance_issues)
            )
            print(
                f"{compliance_error} Starting another review pass; attempts are "
                "10 times then best effort or Ctrl+Q.",
                flush=True,
            )

    def request_plan_audit(
        beats,
        macro_arc,
        plan_attempt,
        audit_round=0,
        repaired_beat_ids=None,
    ):
        last_error = None
        audit_content_attempt = 0
        while True:
            audit_content_attempt += 1
            print(
                f"Requesting global beat-plan audit for plan attempt "
                f"{plan_attempt} (response attempt {audit_content_attempt}; "
                "10 times then best effort or Ctrl+Q).",
                flush=True,
            )
            audit_messages = build_beat_plan_audit_messages(
                story,
                total_segments,
                beats,
                macro_arc,
                subject_information=subject_information,
                beat_instructions=beat_instructions,
                repaired_beat_ids=repaired_beat_ids,
            )
            if last_error:
                audit_messages[-1]["content"] += (
                    "\n\nYOUR PREVIOUS AUDIT RESPONSE WAS STRUCTURALLY INVALID\n"
                    f"{last_error}\nReturn the complete audit JSON again."
                )
            verify_subjects_in_beat_messages(
                audit_messages,
                subject_information,
            )
            raw_audit = llm_request(
                audit_messages,
                response_format=build_beat_plan_audit_response_format(
                    total_segments
                ),
                history_metadata={
                    **(history_metadata or {}),
                    "purpose": "beat_plan_audit",
                    "attempt": plan_attempt,
                    "response_attempt": audit_content_attempt,
                    "audit_round": audit_round,
                    "total_segments": total_segments,
                },
                **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                return parse_beat_plan_audit(
                    raw_audit,
                    total_segments=total_segments,
                )
            except ValueError as error:
                last_error = error
                print(
                    "LM Studio returned an invalid beat-plan audit; requesting "
                    f"another audit response: {last_error}"
                )

    def request_plan_verification(
        beats,
        macro_arc,
        frozen_issues,
        pending_issue_ids,
        plan_attempt,
        verification_round,
    ):
        last_error = None
        response_attempt = 0
        pending_issue_ids = sorted(set(pending_issue_ids))
        while True:
            response_attempt += 1
            print(
                f"Verifying {len(pending_issue_ids)} frozen beat-plan blocker"
                f"{'' if len(pending_issue_ids) == 1 else 's'} "
                f"(round {verification_round}, response attempt "
                f"{response_attempt}; 10 times then best effort or Ctrl+Q).",
                flush=True,
            )
            messages = build_beat_plan_verification_messages(
                story,
                total_segments,
                beats,
                macro_arc,
                frozen_issues,
                pending_issue_ids,
                subject_information=subject_information,
            )
            if last_error:
                messages[-1]["content"] += (
                    "\n\nYOUR PREVIOUS VERIFICATION RESPONSE WAS STRUCTURALLY "
                    "INVALID\n"
                    f"{last_error}\nReturn the verification JSON again."
                )
            verify_subjects_in_beat_messages(
                messages,
                subject_information,
            )
            raw_verification = llm_request(
                messages,
                response_format=build_beat_plan_verification_response_format(
                    pending_issue_ids
                ),
                history_metadata={
                    **(history_metadata or {}),
                    "purpose": "beat_plan_verify",
                    "attempt": plan_attempt,
                    "verification_round": verification_round,
                    "response_attempt": response_attempt,
                    "total_segments": total_segments,
                    "pending_issue_ids": pending_issue_ids,
                },
                **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                return parse_beat_plan_verification(
                    raw_verification,
                    pending_issue_ids,
                )
            except ValueError as error:
                last_error = error
                print(
                    "LM Studio returned an invalid frozen-blocker verification; "
                    f"requesting another response: {last_error}",
                    flush=True,
                )

    def request_plan_repair(
        beats,
        macro_arc,
        repair_ranges,
        blocking_issues,
        plan_attempt,
        repair_round,
        response_attempt,
        correction="",
    ):
        requested_ids = beat_ids_for_repair_ranges(repair_ranges)
        repair_messages = build_beat_plan_repair_messages(
            story,
            total_segments,
            beats,
            macro_arc,
            blocking_issues,
            repair_ranges,
            subject_information=subject_information,
            beat_instructions=beat_instructions,
            correction=correction,
            phrase_exclusions=phrase_exclusions,
        )
        verify_subjects_in_beat_messages(
            repair_messages,
            subject_information,
        )
        raw_repair = llm_request(
            repair_messages,
            response_format=build_beat_plan_repair_response_format(
                repair_ranges,
            ),
            history_metadata={
                **(history_metadata or {}),
                "purpose": "beat_plan_repair",
                "attempt": plan_attempt,
                "repair_round": repair_round,
                "response_attempt": response_attempt,
                "total_segments": total_segments,
                "repair_ranges": [
                    {
                        "beat_start": repair_range["beat_start"],
                        "beat_end": repair_range["beat_end"],
                    }
                    for repair_range in repair_ranges
                ],
                "repair_beat_ids": requested_ids,
            },
            **BEAT_AUDIT_LLM_SAMPLING_PARAMETERS,
        )
        return parse_beat_plan_repair(
            raw_repair,
            repair_ranges,
        )

    def accept_plan(beats, audit, plan_attempt, completed_repair_rounds):
        exclusion_issues = validate_generated_beat_exclusions(
            beats,
            phrase_exclusions,
        )
        if exclusion_issues:
            raise ValueError(" ".join(exclusion_issues))
        if audit["warnings"]:
            print(
                "Global beat-plan audit warnings (accepted): "
                + " ".join(audit["warnings"]),
                flush=True,
            )
        if completed_repair_rounds:
            print(
                "Global beat-plan audit passed after "
                f"{completed_repair_rounds} targeted repair round"
                f"{'' if completed_repair_rounds == 1 else 's'}.",
                flush=True,
            )
        else:
            print(
                f"Global beat-plan audit passed on plan attempt "
                f"{plan_attempt}.",
                flush=True,
            )
        print_generated_beats(beats)
        save_generated_beats(
            beats,
            path,
            lora_directive=lora_directive,
            macro_arc=macro_arc,
        )
        print(f"Generated {len(beats)} story beats and saved them to {path}.")
        return load_beats(path)

    if saved_macro_arc is not None:
        macro_arc = saved_macro_arc
        print(f"Using existing story arc from {story_arc_path}.", flush=True)
    else:
        # Outer process loop: try up to 10 times, regenerating story_arc.json on each failure
        macro_arc = None
        process_attempt = 0
        max_process_attempts = 10
        
        while process_attempt < max_process_attempts:
            process_attempt += 1
            print(
                f"\n=== Global beat macro arc process attempt {process_attempt}/{max_process_attempts} ===",
                flush=True,
            )
            
            # Delete story_arc files to force regeneration
            hash_path = get_story_arc_hash_path(story_arc_path)
            if os.path.exists(story_arc_path):
                os.remove(story_arc_path)
                print(f"Deleted cached story arc: {story_arc_path}", flush=True)
            if os.path.exists(hash_path):
                os.remove(hash_path)
                print(f"Deleted cache hash: {hash_path}", flush=True)
            
            # Request macro arc with validation
            macro_arc, validation_success = request_valid_macro_arc(max_attempts=10)
            
            if validation_success and macro_arc is not None:
                print(
                    f"Macro arc validation succeeded on process attempt {process_attempt}.",
                    flush=True,
                )
                break
            
            # Validation failed but we have a macro_arc as best effort
            if process_attempt < max_process_attempts:
                print(
                    f"Macro arc validation failed on process attempt {process_attempt}; "
                    f"restarting macro arc generation (process attempt {process_attempt + 1}/{max_process_attempts}).",
                    flush=True,
                )
            else:
                print(
                    f"Macro arc process reached maximum attempts ({max_process_attempts}); "
                    "accepting best effort result.",
                    flush=True,
                )
        
        if macro_arc is None:
            raise ValueError(
                "Failed to generate a valid macro arc after "
                f"{max_process_attempts} process attempts."
            )
    audit_correction = ""
    last_audit = None
    plan_attempt = 0
    while True:
        plan_attempt += 1
        if (
            plan_attempt > 1
            and last_audit
            and not last_audit["macro_arc_consistent_with_source"]
        ):
            # Outer process loop for audit-triggered regeneration
            audit_macro_arc = None
            audit_process_attempt = 0
            audit_max_process_attempts = 10
            audit_correction = (
                "The global audit found the macro arc inconsistent with the "
                "source story: "
                + format_beat_plan_blocking_issues(
                    last_audit["blocking_issues"]
                )
            )
            
            while audit_process_attempt < audit_max_process_attempts:
                audit_process_attempt += 1
                print(
                    f"\n=== Audit-triggered macro arc process attempt "
                    f"{audit_process_attempt}/{audit_max_process_attempts} ===",
                    flush=True,
                )
                
                # Delete story_arc files to force regeneration
                hash_path = get_story_arc_hash_path(story_arc_path)
                if os.path.exists(story_arc_path):
                    os.remove(story_arc_path)
                    print(f"Deleted cached story arc: {story_arc_path}", flush=True)
                if os.path.exists(hash_path):
                    os.remove(hash_path)
                    print(f"Deleted cache hash: {hash_path}", flush=True)
                
                # Request macro arc with validation and audit correction
                audit_macro_arc, audit_validation_success = request_valid_macro_arc(
                    correction=audit_correction,
                    max_attempts=10
                )
                
                if audit_validation_success and audit_macro_arc is not None:
                    print(
                        f"Audit-triggered macro arc validation succeeded on "
                        f"process attempt {audit_process_attempt}.",
                        flush=True,
                    )
                    macro_arc = audit_macro_arc
                    break
                
                # Validation failed but we have a macro_arc as best effort
                if audit_process_attempt < audit_max_process_attempts:
                    print(
                        f"Audit-triggered macro arc validation failed on process attempt "
                        f"{audit_process_attempt}; restarting macro arc generation "
                        f"(process attempt {audit_process_attempt + 1}/{audit_max_process_attempts}).",
                        flush=True,
                    )
                else:
                    print(
                        f"Audit-triggered macro arc process reached maximum attempts "
                        f"({audit_max_process_attempts}); accepting best effort result.",
                        flush=True,
                    )
                    macro_arc = audit_macro_arc
            
            if macro_arc is None:
                raise ValueError(
                    "Failed to generate a valid macro arc for audit correction after "
                    f"{audit_max_process_attempts} process attempts."
                )
        beats = generate_batches(macro_arc, audit_correction=audit_correction)
        beats = review_explicit_instructions(beats, macro_arc)
        audit = request_plan_audit(beats, macro_arc, plan_attempt)
        repaired_beat_ids = set()
        completed_repair_rounds = 0
        fallback_reason = ""
        frozen_issues = []
        pending_issue_ids = []
        last_audit = audit

        if not audit["macro_arc_consistent_with_source"]:
            fallback_reason = (
                "the audit found the macro arc inconsistent with the hard "
                "source requirements"
            )
        else:
            initial_normalized = normalize_beat_plan_repair_ranges(
                audit["blocking_issues"],
                total_segments,
                story=story,
                beat_instructions=beat_instructions,
            )
            discarded_count = (
                audit.get("discarded_blocking_issues", 0)
                + len(initial_normalized["discarded"])
            )
            broad_downgrades = list(initial_normalized["downgraded"])
            if broad_downgrades:
                for issue in broad_downgrades:
                    print(
                        "Global beat-plan audit warning only; not auto-repairing "
                        f"broad Beats {issue['beat_start']}-{issue['beat_end']} "
                        f"({issue['type']}). Targeted auto-repairs are limited "
                        f"to {MAX_TARGETED_BEAT_REPAIR_SPAN} beats.",
                        flush=True,
                    )

            if not initial_normalized["issues"]:
                if discarded_count:
                    fallback_reason = (
                        "the audit's blocking ranges were malformed or outside "
                        "the beat plan and could not be localized safely"
                    )
                else:
                    accepted_audit = dict(audit)
                    accepted_audit["valid"] = True
                    accepted_audit["blocking_issues"] = []
                    accepted_audit["warnings"] = list(audit.get("warnings", []))
                    accepted_audit["warnings"].extend(
                        f"Broad audit issue was not auto-repaired: Beats "
                        f"{issue['beat_start']}-{issue['beat_end']} "
                        f"({issue['type']}): {issue['problem']}"
                        for issue in broad_downgrades
                    )
                    return accept_plan(
                        beats,
                        accepted_audit,
                        plan_attempt,
                        completed_repair_rounds,
                    )
            else:
                # Freeze the initial global audit's blocker identities. Every
                # subsequent LLM call may only resolve or retain these issues;
                # it may never discover a new blocker or move the goalposts.
                frozen_issues = list(initial_normalized["issues"])
                pending_issue_ids = list(range(1, len(frozen_issues) + 1))
                print(
                    "Initial global beat-plan audit reported "
                    f"{len(frozen_issues)} frozen blocking issue"
                    f"{'' if len(frozen_issues) == 1 else 's'}; verifying them "
                    "before making repairs.",
                    flush=True,
                )
                pending_issue_ids = request_plan_verification(
                    beats,
                    macro_arc,
                    frozen_issues,
                    pending_issue_ids,
                    plan_attempt,
                    verification_round=0,
                )

                if not pending_issue_ids:
                    accepted_audit = dict(audit)
                    accepted_audit["valid"] = True
                    accepted_audit["blocking_issues"] = []
                    return accept_plan(
                        beats,
                        accepted_audit,
                        plan_attempt,
                        completed_repair_rounds,
                    )

                repair_round = 0
                while pending_issue_ids:
                    repair_round += 1
                    pending_issues = [
                        frozen_issues[issue_id - 1]
                        for issue_id in pending_issue_ids
                    ]
                    normalized = normalize_beat_plan_repair_ranges(
                        pending_issues,
                        total_segments,
                        story=story,
                        beat_instructions=beat_instructions,
                    )
                    discarded_count = len(normalized["discarded"])
                    if discarded_count or not normalized["issues"]:
                        fallback_reason = (
                            "a frozen blocker could no longer be localized safely"
                        )
                        break

                    repair_ranges = normalized["ranges"]
                    if not repair_ranges:
                        fallback_reason = (
                            "the frozen blockers produced no safely localized "
                            "repair range"
                        )
                        break

                    print(
                        "Frozen beat-plan verification still has "
                        f"{len(pending_issue_ids)} unresolved blocker"
                        f"{'' if len(pending_issue_ids) == 1 else 's'}: "
                        + ", ".join(
                            f"Issue {issue_id}" for issue_id in pending_issue_ids
                        ),
                        flush=True,
                    )
                    print(f"Issues: {pending_issues}", flush=True)
                    working_beats = list(beats)
                    for range_number, repair_range in enumerate(
                        repair_ranges,
                        start=1,
                    ):
                        range_issues = [
                            issue
                            for issue in pending_issues
                            if not (
                                issue["beat_end"] < repair_range["beat_start"]
                                or issue["beat_start"] > repair_range["beat_end"]
                            )
                        ]
                        range_label = format_beat_plan_repair_ranges(
                            [repair_range]
                        )
                        print(
                            f"Repair round {repair_round}, localized request "
                            f"{range_number}/{len(repair_ranges)}: repairing "
                            f"{range_label} only.",
                            flush=True,
                        )
                        correction = ""
                        repaired_beats = None
                        response_attempt = 0
                        while True:
                            response_attempt += 1
                            try:
                                replacement_beats = request_plan_repair(
                                    working_beats,
                                    macro_arc,
                                    [repair_range],
                                    range_issues,
                                    plan_attempt,
                                    repair_round,
                                    response_attempt,
                                    correction=correction,
                                )
                                repaired_beats = splice_beat_plan_repair(
                                    working_beats,
                                    [repair_range],
                                    replacement_beats,
                                )
                                introduction_issues = (
                                    validate_generated_beat_macro_introductions(
                                        repaired_beats,
                                        macro_arc,
                                    )
                                )
                                if introduction_issues:
                                    raise ValueError(
                                        "Repaired complete plan violates macro "
                                        "introduction timing: "
                                        + " ".join(introduction_issues)
                                    )
                                instruction_issues = (
                                    validate_generated_beat_instructions(
                                        repaired_beats,
                                        beat_instructions,
                                    )
                                )
                                if instruction_issues:
                                    raise ValueError(
                                        "Repaired complete plan violates explicit "
                                        "beat instructions: "
                                        + " ".join(instruction_issues)
                                    )
                                exclusion_issues = validate_generated_beat_exclusions(
                                    repaired_beats,
                                    phrase_exclusions,
                                )
                                if exclusion_issues:
                                    raise ValueError(" ".join(exclusion_issues))
                            except Exception as error:
                                correction = str(error)
                                repaired_beats = None
                                print(
                                    f"Repair round {repair_round}, {range_label} "
                                    f"response failed validation (attempt "
                                    f"{response_attempt}; 10 times then best "
                                    f"effort or Ctrl+Q): {error}",
                                    flush=True,
                                )
                                continue
                            break

                        working_beats = repaired_beats

                    beats = working_beats
                    completed_repair_rounds = repair_round
                    repaired_beat_ids.update(
                        beat_ids_for_repair_ranges(repair_ranges)
                    )
                    print(
                        f"Repair round {repair_round} completed; verifying only "
                        f"the {len(pending_issue_ids)} remaining frozen blocker"
                        f"{'' if len(pending_issue_ids) == 1 else 's'}.",
                        flush=True,
                    )
                    pending_issue_ids = request_plan_verification(
                        beats,
                        macro_arc,
                        frozen_issues,
                        pending_issue_ids,
                        plan_attempt,
                        verification_round=repair_round,
                    )

                if not pending_issue_ids and not fallback_reason:
                    accepted_audit = dict(audit)
                    accepted_audit["valid"] = True
                    accepted_audit["blocking_issues"] = []
                    return accept_plan(
                        beats,
                        accepted_audit,
                        plan_attempt,
                        completed_repair_rounds,
                    )

        last_audit = audit
        if pending_issue_ids:
            remaining_frozen = [
                frozen_issues[issue_id - 1]
                for issue_id in pending_issue_ids
            ]
            audit_correction = format_beat_plan_blocking_issues(remaining_frozen)
        else:
            audit_correction = (
                format_beat_plan_blocking_issues(audit["blocking_issues"])
                if audit["blocking_issues"]
                else fallback_reason
            )
        print(
            "Falling back to full-plan regeneration because "
            f"{fallback_reason}. Remaining blockers: "
            f"{audit_correction}. Plan attempts are unlimited until successful "
            "or Ctrl+Q.",
            flush=True,
        )


def load_or_generate_beats(
    path,
    story,
    total_segments,
    llm_request=None,
    history_metadata=None,
    beat_instructions="",
    subject_information="",
    story_arc_path=None,
    story_arc_source=None,
    phrase_exclusions=(),
    force_generate=False,
    gen_rules="",
):
    raw = load_text_file(path, required=not force_generate)
    try:
        beats, lora_directive = parse_beats_content(raw)
    except ValueError:
        if not force_generate:
            raise
        beats, lora_directive = [], ""
    if beats and not force_generate:
        exclusion_issues = validate_generated_beat_exclusions(
            beats,
            phrase_exclusions,
        )
        if exclusion_issues:
            raise ValueError(
                f"{path} violates phrase_exclusions.txt: "
                + " ".join(exclusion_issues)
            )
        return beats
    if force_generate:
        print(
            f"Asking LM Studio to replace {path} with {total_segments} creative "
            "story beats."
        )
    else:
        print(
            f"{path} is empty; asking LM Studio to create {total_segments} "
            "creative story beats before generation starts."
        )
    return generate_beats_from_story(
        story,
        total_segments,
        path=path,
        llm_request=llm_request,
        history_metadata=history_metadata,
        beat_instructions=beat_instructions,
        subject_information=subject_information,
        lora_directive=lora_directive,
        story_arc_path=story_arc_path,
        story_arc_source=story_arc_source,
        phrase_exclusions=phrase_exclusions,
        reuse_story_arc=not force_generate,
        gen_rules=gen_rules,
    )


def build_story_context(
    story,
    active_beat=None,
    lookahead_beats=None,
    subject_definitions="",
    max_chars=STORY_CONTEXT_MAX_CHARS,
):
    """Select relevant current-story paragraphs without favoring the ending."""
    story = str(story or "").strip()
    if len(story) <= max_chars:
        return story
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", story) if part.strip()]
    terms = set(re.findall(r"[a-z0-9]+", " ".join([
        str(active_beat or ""),
        " ".join(str(item) for item in (lookahead_beats or [])),
        str(subject_definitions or ""),
    ]).lower()))
    scored = []
    for index, paragraph in enumerate(paragraphs):
        paragraph_terms = set(re.findall(r"[a-z0-9]+", paragraph.lower()))
        score = len(terms & paragraph_terms)
        if score:
            scored.append((score, index))
    selected_indexes = set()
    if scored:
        for _, index in sorted(scored, key=lambda item: (-item[0], item[1])):
            selected_indexes.update(
                neighbor for neighbor in (index - 1, index, index + 1)
                if 0 <= neighbor < len(paragraphs)
            )
    else:
        # No reliable match: use only the opening premise as a bounded fallback,
        # rather than granting the source ending special authority.
        selected_indexes.add(0)

    omission = (
        "\n\n[Other source-story material omitted; use BEAT STATE and "
        "AUTHORITATIVE OPENING STATE for current authority.]"
    )
    content_budget = max(1, max_chars - len("CURRENT STORY CONTEXT\n\n") - len(omission))
    selected = []
    used_chars = 0
    for index in sorted(selected_indexes):
        paragraph = paragraphs[index]
        remaining = content_budget - used_chars
        if remaining <= 0:
            continue
        paragraph = paragraph[:remaining].rstrip()
        selected.append(paragraph)
        used_chars += len(paragraph) + 2
    if not selected:
        selected = [story[:max_chars].rstrip()]
    return (
        "CURRENT STORY CONTEXT\n\n"
        + "\n\n".join(selected)
        + omission
    )


# ============================================================
# DIRECTOR PROMPT
# ============================================================

def is_hard_cut_segment(segment_number):
    """Hard cuts are disabled; refresh/latent continuity remains continuous."""
    del segment_number
    return False


DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE = """You are a movie director expanding on a an idea into an {segment_seconds} second segment. This segment will be based on beat {beat_number}.  The continuity state from the previous segment is provided. 
 
For extra context, you are provided the overarching story and the overarching phase.  You will be provided the full beat list for the phase.   
 
- Only write the specified beat.  
- Only write what would be necessary for visual and audio input. 
- Focus on actions, camera movement, and audio 
 
Use your best judgement as a director and with the given context: the camera state/movements in addition to the scene itself."""

H3_AUDIOVISUAL_FORMATTER_SYSTEM = """You are a MiniMax H3 audiovisual prompt formatter. 
 
Your job is to take the user's scene description and rewrite it into a clear chronological video prompt for the requested duration. 
 
Preserve the intended events, characters, dialogue, clothing, physical states, and order of actions. Do not invent new story events, characters, dialogue, transformations, props, or outcomes just to make the prompt more detailed. 
 
Write only things that can be visibly seen or audibly heard. 

BEAT EXECUTION AND CONTINUITY

The RAW SCENE contains the assigned beat. The assigned beat's primary action must
visibly occur during this segment; do not merely set it up, hint at it, reveal its
consequences, or end on a reaction to it. The final visible state must show clear
progress through the assigned beat.

AUTHORITATIVE OPENING STATE is only the starting state at frame 0. Establish that
continuity once at the beginning of Shot 1, then immediately advance into the new
beat. Do not repeat the opening continuity in a second description, later shot, or
restatement. Continuity must not consume the segment.

Do not substitute a reveal, reaction, atmospheric moment, or invented cinematic
action for the beat's required action. Do not invent slow motion, impacts, pauses,
characters freezing, characters leaving frame, or other major actions unless they
are needed to execute the assigned beat. For segments 5 seconds or shorter, prefer
1-3 shots. Do not create additional shots merely to provide camera variety.

If the beat has multiple required actions, show them in order and complete the
visible progression before the segment ends. For example, if the beat says a
werewolf emerges, chases Amy, and gains ground, visibly show the werewolf emerge,
Amy flee, the werewolf pursue her, and the distance between them decrease before
the segment ends.
 
OUTPUT 
 
Return only these 3 fields as plain text: 
 
detailed_description: 
overall_soundscape: 
non_diegetic_music: 
 
If the user specifies I2VA, FL2VA, or L2VA, put the required reference-picture alignment instruction before these fields. For T2VA, begin directly with the three fields. 
 
VIDEO DESCRIPTION 
 
Begin with [Shot 1] and establish the opening visual composition without a timestamp. 
 
Describe events in chronological order through the requested duration. 
 
Use additional shots only when a real cut or viewpoint change is useful. Number them sequentially. A later shot begins with a timestamp such as: 
 
[Shot 2] At 00:03.500, the camera cuts to... 
 
Prefer camera movement instead of a cut when the scene remains continuous. 
 
Describe camera movement naturally using terms such as: 
Push In, Pull Out, Pan Left, Pan Right, Truck Left, Truck Right, Tilt Up, Tilt Down, Pedestal Up, Pedestal Down, Arc Shot, Tracking Shot, Static Shot, POV, or camera roll. 
 
Add speed or amplitude only when useful. 

DIALOGUE 
 
Preserve supplied dialogue exactly. Never create dialogue. 
 
Use stable speaker IDs such as (S1) and (S2). 
 
Spoken dialogue must use: 
 
<d>[Language] exact dialogue</d> 
 
AUDIO 
 
overall_soundscape contains only ambient sound, action sounds, and nonverbal human sounds. Do not repeat dialogue there. 
 
non_diegetic_music contains only music the characters cannot hear. Use N/A when there is none. 
 
KEYFRAME MODES 
 
I2VA: Picture 1 is the exact opening frame. Preserve its visible identity, appearance, composition, and scene state, then develop forward. 
 
FL2VA: Picture 1 is the opening frame and Picture 2 is the ending frame. Describe a continuous physical and visual path connecting them. 
 
L2VA: Picture 1 is the ending frame. Begin from a plausible earlier state and progressively converge on that exact final composition. 
 
Follow the requested duration exactly. Return only the finished MiniMax H3 prompt."""


def build_director_rules(
    total_length,
    segment_length,
    total_segments,
    subject_definitions,
    segment_number,
    beats_enabled=True,
    conditioning_mode=None,
    gen_rules="",
):
    """Return the narrow Request-1 Director system prompt.

    The legacy signature is retained so repair/resume callers do not need a
    separate compatibility path.  Only segment duration and beat number matter
    to this micro-prompt; all narrative context is supplied in the user turn.
    """
    del total_length, total_segments, subject_definitions, beats_enabled
    del conditioning_mode, gen_rules
    return DIRECTOR_RAW_SCENE_SYSTEM_TEMPLATE.format(
        segment_seconds=f"{float(segment_length):g}",
        beat_number=int(segment_number),
    )


def _phase_beats_text(beats, current_phase, beat_number):
    """Render the complete numbered beat list for the active macro phase."""
    if not beats:
        return "N/A"
    try:
        active_id = int(beat_number)
    except (TypeError, ValueError):
        active_id = 1
    phase = current_phase if isinstance(current_phase, dict) else {}
    try:
        start = int(phase.get("beat_start", active_id))
        end = int(phase.get("beat_end", active_id))
    except (TypeError, ValueError):
        start = end = active_id
    start = max(1, min(start, len(beats)))
    end = max(start, min(end, len(beats)))
    return "\n".join(
        f"{beat_id}. {beats[beat_id - 1]}"
        for beat_id in range(start, end + 1)
    )


def _normalize_raw_scene_result(raw_result):
    """Return Request 1 as plain raw_scene text without semantic rewriting."""
    if isinstance(raw_result, dict):
        for key in ("raw_scene", "scene", "description"):
            value = raw_result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if len(raw_result) == 1:
            value = next(iter(raw_result.values()))
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(raw_result, ensure_ascii=False)
    text = str(raw_result or "").strip()
    if text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:-3].strip()
    text = re.sub(r"(?is)^\s*raw_scene\s*:\s*", "", text, count=1)
    if not text:
        raise RuntimeError("Director Request 1 returned an empty raw_scene.")
    return text


def build_h3_formatter_messages(
    raw_scene,
    mode,
    segment_seconds,
    continuity_summary="",
):
    """Build Request 2: a pure MiniMax H3 audiovisual formatting job."""
    mode = str(mode or "T2VA").strip().upper()
    continuity_text = str(continuity_summary or "").strip()
    opening_block = (
        "AUTHORITATIVE OPENING STATE:\n"
        + (continuity_text if continuity_text else "N/A")
    )
    user_content = (
        f"MODE: {mode}\n"
        f"DURATION: {float(segment_seconds):g} seconds \n\n"
        f"{opening_block}\n\n"
        "RAW SCENE:\n"
        f"{str(raw_scene or '').strip()}"
    )
    return [
        {"role": "system", "content": H3_AUDIOVISUAL_FORMATTER_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def _extract_h3_formatter_fields(raw_result):
    """Return Request 2's raw fields without validation.

    Returns (description, soundscape, music, reference_alignment).  Each of the
    three content fields may be None when the LLM omitted it, so callers can
    decide whether to fail or salvage.
    """
    reference_alignment = ""
    if isinstance(raw_result, dict):
        description = raw_result.get("detailed_description")
        if description is None:
            description = raw_result.get("detailed_description")
        soundscape = raw_result.get("overall_soundscape")
        music = raw_result.get("non_diegetic_music")
        reference_alignment = str(
            raw_result.get("reference_alignment", "") or ""
        ).strip()
    else:
        text = str(raw_result or "").strip()
        if text.startswith("```") and text.endswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:-3].strip()
        field_re = re.compile(
            r"(?im)^\s*(detailed_description|overall_soundscape|"
            r"non_diegetic_music)\s*:\s*"
        )
        matches = list(field_re.finditer(text))
        values = {}
        if matches:
            reference_alignment = text[:matches[0].start()].strip()
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                values[match.group(1).lower()] = text[match.end():end].strip()
        description = values.get("detailed_description")
        soundscape = values.get("overall_soundscape")
        music = values.get("non_diegetic_music")
    return description, soundscape, music, reference_alignment


def parse_h3_formatter_result(raw_result, completed_beat_id=None):
    """Parse Request 2's three plain-text fields with optional mode preamble."""
    description, soundscape, music, reference_alignment = (
        _extract_h3_formatter_fields(raw_result)
    )

    if not isinstance(description, str) or not description.strip():
        raise RuntimeError(
            "Director Request 2 is missing detailed_description."
        )
    if not isinstance(soundscape, str) or not soundscape.strip():
        raise RuntimeError("Director Request 2 is missing overall_soundscape.")
    if not isinstance(music, str) or not music.strip():
        raise RuntimeError("Director Request 2 is missing non_diegetic_music.")

    completed = []
    if completed_beat_id is not None:
        try:
            completed = [int(completed_beat_id)]
        except (TypeError, ValueError):
            completed = []
    return {
        "detailed_description": description.strip(),
        "overall_soundscape": soundscape.strip(),
        "non_diegetic_music": music.strip(),
        "completed_beat_ids": completed,
        "reference_alignment": reference_alignment,
    }


def _salvage_h3_formatter_result(raw_result, completed_beat_id=None, fallback_text=""):
    """Best-effort Request 2 result from the last raw LLM output.

    Used only after the formatter retry budget is exhausted so a missing field
    never becomes a fatal error.  The description falls back to the last raw
    LLM output (when it is free-form text), then to the raw scene text (the
    source the formatter was asked to render); missing soundscape/music become
    "N/A".  Beat completion metadata is still attached so downstream
    checkpointing behaves normally.
    """
    description, soundscape, music, reference_alignment = (
        _extract_h3_formatter_fields(raw_result)
    )
    fallback_text = str(fallback_text or "").strip()
    raw_output_text = ""
    if not isinstance(raw_result, dict):
        raw_output_text = str(raw_result or "").strip()
    if not isinstance(description, str) or not description.strip():
        description = raw_output_text or fallback_text or "N/A"
    if not isinstance(soundscape, str) or not soundscape.strip():
        soundscape = "N/A"
    if not isinstance(music, str) or not music.strip():
        music = "N/A"
    completed = []
    if completed_beat_id is not None:
        try:
            completed = [int(completed_beat_id)]
        except (TypeError, ValueError):
            completed = []
    return {
        "detailed_description": str(description).strip() or "N/A",
        "overall_soundscape": str(soundscape).strip() or "N/A",
        "non_diegetic_music": str(music).strip() or "N/A",
        "completed_beat_ids": completed,
        "reference_alignment": reference_alignment,
    }

def get_detailed_description(llm_result, default=""):
    """Read the renamed description field while accepting old checkpoints."""
    if not isinstance(llm_result, dict):
        return default
    value = llm_result.get("detailed_description")
    if value is None:
        value = llm_result.get("detailed_description", default)
    return value


def format_recent_segment(segment_number, llm_result):
    payload = {
        key: value
        for key, value in llm_result.items()
        if key != "completed_beat_ids"
    }
    if "detailed_description" not in payload:
        legacy_description = payload.pop(
            "detailed_description",
            None,
        )
        if legacy_description is not None:
            payload["detailed_description"] = legacy_description
    result = (
        f"--- EXACT RECENT SEGMENT {segment_number} ---\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + f"\n--- END SEGMENT {segment_number} ---"
    )
    return result


def build_summary_messages(recent_results):
    """Build a stateless eight-field previous-state conversation."""
    recent_pair = list(recent_results)[-RECENT_SEGMENTS_MAX:]
    if not recent_pair:
        raise ValueError("A previous state requires at least one segment.")

    exact_prompts = "\n\n".join(
        format_recent_segment(number, result)
        for number, result in recent_pair
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a movie continuity state summarizer. Summarize only the "
                "generated prompts supplied by the user. Return exactly "
                "eight plain-text lines in the required field format, one for "
                "each field: Location/environment, Character positions, "
                "Character appearance/physical condition, Clothing, Props/objects, "
                "Camera/framing, Ongoing physical action, and Ongoing audio. "
                "The newest segment is authoritative. "
                "Use the older segment only for facts visibly or explicitly "
                "unchanged. Report only current visible facts. Do not invent "
                "positions, poses, locations, or actions from vague group wording. "
                "If a fact is not visible or explicitly established in the newest "
                "segment, write N/A. Never carry an older position into a newer "
                "composition that contradicts it. Do not give directing advice."
            )
        },
        {
            "role": "user",
            "content": (
                "Write the eight-field previous state for these exact "
                f"generated prompt(s):\n\n{exact_prompts}\n\n"
                "Use only explicit facts from the newest generated prompt and "
                "write N/A for unknown facts."
            )
        }
    ]


def normalize_five_bullet_summary(summary):
    """Return canonical five-bullet text, or None for malformed content."""
    if not isinstance(summary, str):
        return None

    candidate = summary.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline != -1:
            candidate = candidate[first_newline + 1:-3].strip()

    bullet_texts = []
    for line in candidate.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        text = None
        for marker in ("- ", "* ", "• "):
            if stripped.startswith(marker):
                text = stripped[len(marker):].strip()
                break
        if text is None:
            number, separator, remainder = stripped.partition(". ")
            if not (separator and number.isdigit()):
                number, separator, remainder = stripped.partition(") ")
            if separator and number.isdigit():
                text = remainder.strip()
        if not text:
            return None
        bullet_texts.append(text)

    if len(bullet_texts) != 5:
        return None
    return "\n".join(f"- {text}" for text in bullet_texts)


def sanitize_previous_state_value(value):
    """Replace unsupported dash glyphs in continuity summaries."""
    if not isinstance(value, str):
        return value
    cleaned = value.replace("\u2014", ", ").replace("â€”", ", ")
    cleaned = re.sub(r"\s*,\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r",\s*([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = cleaned.strip()
    # Normalize N/A with parenthetical explanations to plain "N/A".
    if re.match(r"(?i)^n/?a\b(?:\s*\(|\s*$)", cleaned):
        return "N/A"
    return cleaned


def normalize_previous_state(summary):
    if not isinstance(summary, str):
        return None
    values = {}
    for line in summary.strip().splitlines():
        line = re.sub(r"^\s*-\s*", "", line)
        label, separator, value = line.partition(":")
        if separator and label.strip() in PREVIOUS_STATE_FIELDS:
            normalized_value = sanitize_previous_state_value(value.strip())
            values[label.strip()] = normalized_value or "N/A"
    if set(values) != set(PREVIOUS_STATE_FIELDS):
        return None
    return "\n".join(
        f"- {field}: {values[field]}"
        for field in PREVIOUS_STATE_FIELDS
    )


def request_five_bullet_summary(
    recent_results,
    llm_request=None,
    content_attempts=SUMMARY_CONTENT_ATTEMPTS,
    subject_definitions="",
    history_metadata=None,
):
    """Summarize recent results in a separate text-only LLM thread."""
    if llm_request is None:
        llm_request = ask_llm
    base_messages = build_summary_messages(recent_results)
    for attempt in range(1, content_attempts + 1):
        messages = [dict(message) for message in base_messages]
        if attempt > 1:
            messages[-1] = {
                "role": "user",
                "content": (
                    base_messages[-1]["content"]
                    + "\n\n"
                    "The prior response did not contain exactly the eight required "
                    "field lines. Return all eight labels exactly once, each with "
                    "a concrete value or N/A, and no other text."
                )
            }
        summary = llm_request(
            messages,
            response_format=None,
            **({"history_metadata": history_metadata} if history_metadata else {}),
        )
        summary = normalize_summary_subject_references(
            summary,
            subject_definitions,
        )
        normalized = normalize_previous_state(summary)
        if normalized is not None:
            return normalized

    raise RuntimeError(
        "LM Studio did not return an exact eight-field previous state "
        f"after {content_attempts} attempts."
    )


def extract_final_timeline_excerpt(description):
    """Return the last explicitly timed beat plus trailing untimed prose."""
    text = str(description or "").strip()
    if not text:
        return "N/A"
    matches = list(_CONTINUITY_TIMESTAMP_RE.finditer(text))
    if not matches:
        # Without timestamps, the final two sentences are the best bounded proxy.
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        return " ".join(sentences[-2:]) if sentences else text
    start = matches[-1].start()
    # Back up to the sentence boundary so the final timed action remains readable.
    boundary = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
    if boundary >= 0:
        start = boundary + 1
    return text[start:].strip() or text


def build_structured_continuity_messages(
    recent_results,
    committed_state,
    subject_definitions,
    active_beat_text="",
    future_beat_texts=None,
    new_subjects=None,
):
    """Ask the LLM for changes only; Python owns the actual state."""
    del future_beat_texts, new_subjects
    recent_results = list(recent_results or [])
    registry_text = json.dumps(
        parse_subject_registry(subject_definitions),
        ensure_ascii=False,
        indent=2,
    )
    state_text = json.dumps(
        continuity_state_for_registry(subject_definitions, committed_state),
        ensure_ascii=False,
        indent=2,
    )
    newest_segment_number = int(recent_results[-1][0]) if recent_results else None
    newest_description = (
        str(get_detailed_description(recent_results[-1][1], "") or "")
        if recent_results else ""
    )
    final_moment_excerpt = extract_final_timeline_excerpt(newest_description)

    return [
        {
            "role": "system",
            "content": """
You extract a continuity DELTA after one generated video segment. Return only
facts that the newest segment establishes, changes, or makes visibly true at
its final frame.

Python owns the continuity state. COMMITTED STATE is authoritative and Python
copies it forward. Do NOT rewrite already-known unchanged persistent facts and
do NOT return a complete replacement state.

IMPORTANT BOOTSTRAP RULE:
- N/A, an empty list, or another empty field in COMMITTED STATE means UNKNOWN.
- If the newest segment clearly establishes an UNKNOWN continuity fact, include
  it in the delta even when that fact did not change during this segment.
- Example categories include location, wardrobe, physical condition, body state,
  attachments, relationships, and other persistent facts visible in the prompt.
- Once a fact is already known in COMMITTED STATE, omit it unless this segment
  changes it or a current-frame field needs a new final value.

Rules:
- Use only registered Subject names/IDs. Do not create new identities.
- ACTIVE BEAT and LATEST GENERATED PROMPT are the only new-event evidence.
- Do not use future story events or infer off-screen changes.
- Report persistent anatomy/topology, wardrobe, injuries, substances,
  attachments, held props, and other lasting physical facts when the newest
  segment changes them OR when the corresponding committed value is UNKNOWN.
- Clothing, garment presence/absence, nudity, shirtless/topless/bottomless state,
  and footwear state belong ONLY in `wardrobe`; never put them in
  `persistent_effects`.
- position, pose_action, physical_condition, spatial_relationships, camera,
  ongoing_action, ongoing_audio, and environment.persistent_state are current
  final-frame facts. Report them when visibly established.
- Completed actions are history, not ongoing_action.
- If something is definitively removed/destroyed, report the resulting state,
  not the removal process.
- List fields contain short strings, never objects.
- Omit already-known persistent fields that did not change.

Allowed top-level keys are: environment, camera, subjects, ongoing_action,
ongoing_audio. Subject delta keys may include position, pose_action, topology,
body_state, physical_condition, wardrobe, attached_objects, injuries,
substances, spatial_relationships, persistent_effects, and held_props.
""".strip(),
        },
        {
            "role": "user",
            "content": (
                "CURRENT SEGMENT\n"
                f"{newest_segment_number or 'N/A'}\n\n"
                "REGISTERED SUBJECTS\n"
                f"{registry_text}\n\n"
                "COMMITTED STATE\n"
                f"{state_text}\n\n"
                "ACTIVE BEAT\n"
                f"{str(active_beat_text or 'N/A').strip()}\n\n"
                "FINAL-MOMENT EXCERPT\n"
                f"{final_moment_excerpt or 'N/A'}\n\n"
                "LATEST GENERATED PROMPT\n"
                f"{newest_description or 'N/A'}\n\n"
                "Return only the continuity DELTA as JSON. Omit already-known "
                "unchanged fields, but populate UNKNOWN/N/A fields when the newest "
                "segment clearly establishes them."
            ),
        },
    ]


_CONTINUITY_DELTA_SUBJECT_FIELDS = frozenset({
    "position",
    "pose_action",
    "topology",
    "body_state",
    "physical_condition",
    "wardrobe",
    "attached_objects",
    "injuries",
    "substances",
    "spatial_relationships",
    "persistent_effects",
    "held_props",
})


def sanitize_continuity_delta(candidate, subject_definitions, committed_state):
    """Keep only legal changes; Python owns identities and copy-forward."""
    if not isinstance(candidate, dict):
        return None

    committed = continuity_state_for_registry(
        subject_definitions,
        committed_state,
    )
    cleaned = {}

    environment = candidate.get("environment")
    if isinstance(environment, dict):
        cleaned_environment = {
            field: copy.deepcopy(environment[field])
            for field in ("location", "persistent_state")
            if field in environment
        }
        if cleaned_environment:
            cleaned["environment"] = cleaned_environment

    for field in ("camera", "ongoing_action", "ongoing_audio"):
        if field in candidate:
            cleaned[field] = copy.deepcopy(candidate[field])

    raw_subjects = candidate.get("subjects")
    if not isinstance(raw_subjects, dict):
        raw_subjects = {}

    id_to_name = {
        str(record.get("subject_id")): name
        for name, record in committed.get("subjects", {}).items()
        if isinstance(record, dict) and record.get("subject_id") is not None
    }

    cleaned_subjects = {}
    for raw_name, raw_update in raw_subjects.items():
        if not isinstance(raw_update, dict):
            continue

        raw_name_text = str(raw_name).strip()
        proposed_name = str(raw_update.get("name") or raw_name_text).strip()
        subject_id = raw_update.get("subject_id")
        if subject_id is None:
            tagged_id = re.fullmatch(
                r"(?i)<\s*Subject\s+(\d+)\s*>",
                raw_name_text,
            )
            if tagged_id is not None:
                subject_id = int(tagged_id.group(1))
        canonical_name = _find_existing_subject_name(
            committed.get("subjects", {}),
            proposed_name,
            subject_id=subject_id,
            speaker_id=raw_update.get("speaker_id"),
        )
        if canonical_name is None and raw_name_text.isdigit():
            canonical_name = id_to_name.get(raw_name_text)
        if canonical_name is None:
            print(
                "WARNING: Ignoring continuity delta for unknown Subject "
                f"{proposed_name or raw_name!r}; identities are Python-owned."
            )
            continue

        update = {
            field: copy.deepcopy(raw_update[field])
            for field in _CONTINUITY_DELTA_SUBJECT_FIELDS
            if field in raw_update
        }
        wardrobe = update.get("wardrobe")
        if isinstance(wardrobe, dict):
            update["wardrobe"] = {
                field: copy.deepcopy(wardrobe[field])
                for field in ("upper", "lower", "footwear", "other")
                if field in wardrobe
            }
            if not update["wardrobe"]:
                update.pop("wardrobe", None)
        elif "wardrobe" in update:
            update.pop("wardrobe", None)

        if update:
            cleaned_subjects[canonical_name] = update

    if cleaned_subjects:
        cleaned["subjects"] = cleaned_subjects

    return cleaned


def build_continuity_state_validation_messages(
    committed_state,
    candidate_state,
    subject_definitions,
    active_beat_text,
    newest_description,
):
    """Ask the LLM only whether Python's resulting state is factually sound."""
    committed = continuity_state_for_registry(
        subject_definitions,
        committed_state,
    )
    candidate = continuity_state_for_registry(
        subject_definitions,
        candidate_state,
    )
    return [
        {
            "role": "system",
            "content": (
                "You validate a Python-built final-frame continuity state. "
                "Do not rewrite it. Report only clear factual continuity "
                "errors. Return only JSON."
            ),
        },
        {
            "role": "user",
            "content": f"""
Validate CANDIDATE STATE as the physical state at the END of the newest segment.

Rules:
- COMMITTED STATE is authoritative before this segment.
- Unchanged persistent facts may survive even when the newest prompt does not
  repeat them.
- ACTIVE BEAT and FINAL CLEANED H3 PROMPT are the only evidence for changes.
- Reject only for a clear contradiction, a missing lasting change, loss of a
  previously persistent fact without evidence, or an invented/future fact.
- Current-frame fields may be N/A when the final frame does not establish them.
- The only Subjects that exist for this validation are the exact subject keys
  present in COMMITTED STATE and CANDIDATE STATE. Never invent, expect, or
  report a missing Subject that is absent from both states.
- `persistent_structural_change` is Python-owned metadata. Do not treat a
  persistent condition that is merely being established for the first time as
  a structural change.
- Clothing, garment presence/absence, nudity, and footwear are represented only
  by `wardrobe`. Do not require or preserve duplicate clothing facts in
  `persistent_effects`.
- Semantic equivalence is fine. Do not critique wording, detail, or style.

COMMITTED STATE
{json.dumps(committed, ensure_ascii=False, indent=2)}

ACTIVE BEAT
{str(active_beat_text or 'N/A').strip()}

FINAL CLEANED H3 PROMPT
{str(newest_description or 'N/A').strip()}

CANDIDATE STATE
{json.dumps(candidate, ensure_ascii=False, indent=2)}

Return only one of these shapes:
{{"valid": true, "issues": []}}
{{"valid": false, "issues": ["concise factual issue"]}}
""".strip(),
        },
    ]


def parse_continuity_state_validation(raw_result):
    """Parse the narrow continuity-state validator response."""
    candidate = raw_result
    if isinstance(candidate, str):
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(
                "Continuity-state validation must return valid JSON."
            ) from error
    if not isinstance(candidate, dict):
        raise ValueError("Continuity-state validation must return an object.")
    valid = candidate.get("valid")
    issues = candidate.get("issues")
    if not isinstance(valid, bool):
        raise ValueError("Continuity-state validation 'valid' must be boolean.")
    if not isinstance(issues, list) or any(
        not isinstance(issue, str) or not issue.strip()
        for issue in issues
    ):
        raise ValueError("Continuity-state validation 'issues' must be strings.")
    issues = [" ".join(issue.split()) for issue in issues]
    if valid != (not issues):
        raise ValueError(
            "Continuity-state validation 'valid' must match whether issues is empty."
        )
    return {"valid": valid, "issues": issues}


def _contains_structural_phrase(text, phrase):
    """Match a neutral region or qualifier without partial-word collisions."""
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def _structural_change_has_evidence(subject_name, candidate_value, description):
    """Require matching region-specific details in the newest prompt."""
    candidate = str(candidate_value or "").casefold()
    source = str(description or "").casefold()

    candidate_regions = {
        phrase
        for phrase in _STRUCTURAL_REGION_PHRASES
        if _contains_structural_phrase(candidate, phrase)
    }
    if candidate_regions and not all(
        _contains_structural_phrase(source, phrase)
        for phrase in candidate_regions
    ):
        return False

    candidate_qualifiers = {
        qualifier
        for qualifier in _STRUCTURAL_REGION_QUALIFIERS
        if _contains_structural_phrase(candidate, qualifier)
    }
    if candidate_regions and not all(
        _contains_structural_phrase(source, qualifier)
        for qualifier in candidate_qualifiers
    ):
        return False

    candidate_terms = {
        token
        for token in re.findall(r"[a-z][a-z'-]{3,}", candidate)
        if token not in _STRUCTURAL_EVIDENCE_STOPWORDS
    }
    if not candidate_terms:
        return True
    source_terms = set(re.findall(r"[a-z][a-z'-]{3,}", source))
    shared_terms = candidate_terms & source_terms
    required_matches = 1 if len(candidate_terms) == 1 else 2
    if len(shared_terms) < required_matches:
        return False

    # If the subject is named, keep the evidence close enough to that identity
    # to avoid borrowing an unrelated change elsewhere in the same description.
    name = str(subject_name or "").strip().casefold()
    if name and name in source:
        evidence_positions = []
        for term in shared_terms:
            evidence_positions.extend(
                match.start() for match in re.finditer(rf"\b{re.escape(term)}\b", source)
            )
        name_positions = [match.start() for match in re.finditer(re.escape(name), source)]
        if evidence_positions and name_positions:
            if not any(abs(evidence - subject_pos) <= 260 for evidence in evidence_positions for subject_pos in name_positions):
                return False
    return True


def _future_subject_name_is_reserved(name, active_beat_text, future_beat_texts):
    """Block durable subjects whose distinctive name belongs only to lookahead."""
    tokens = [
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", str(name or ""))
        if token.casefold() not in {"alien", "creature", "spider", "woman", "man", "girl", "boy"}
    ]
    if not tokens:
        return False
    active = str(active_beat_text or "").casefold()
    future = "\n".join(str(item or "") for item in (future_beat_texts or [])).casefold()
    return any(token in future and token not in active for token in tokens)


def _new_subject_is_animate(record):
    """Accept new durable Subjects only with an explicit animate classification."""
    if not isinstance(record, dict):
        return False
    return str(record.get("entity_kind", "")).strip().casefold() == "animate"


def extract_dialogue_subject_declarations(detailed_description):
    """Extract stable Subject declarations from either supported dialogue form."""
    text = str(detailed_description or "")
    found = []
    seen = set()

    for record in extract_inline_dialogue_subjects(text):
        key = (
            int(record["subject_id"]),
            str(record["speaker_id"]).casefold(),
            str(record["name"]).casefold(),
        )
        if key not in seen:
            seen.add(key)
            found.append(dict(record))

    attribution = re.compile(
        r"(?:<Subject\s+(?P<subject>\d+)>\s+)?"
        r"(?P<name>[A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*){0,4})\s+"
        r"\((?P<speaker>S\d+)\)\s+"
        r"(?:says in an off-screen voiceover|says?|asks?|answers?|replies|"
        r"shouts?|whispers?|yells?|tells?|exclaims?|narrates?|yelps?|cries|"
        r"calls?|murmurs?|mutters?|growls?|screams?)"
        r"[^<>.!?]{0,120}:?\s*$",
        re.I,
    )
    for block in re.finditer(r"<d>.*?</d>", text, re.I | re.S):
        before = text[max(0, block.start() - 300):block.start()]
        previous = before.lower().rfind("</d>")
        if previous >= 0:
            before = before[previous + len("</d>"):]
        match = attribution.search(before)
        if not match:
            continue
        name = " ".join(match.group("name").split())
        if name.casefold() in {"he", "she", "they", "it"}:
            continue
        speaker_id = match.group("speaker").upper()
        explicit_subject = match.group("subject")
        subject_id = (
            int(explicit_subject)
            if explicit_subject is not None
            else int(speaker_id[1:])
        )
        key = (subject_id, speaker_id.casefold(), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "subject_id": subject_id,
            "name": name,
            "picture_ids": [],
            "picture_id": None,
            "speaker_id": speaker_id,
        })
    return found


def _subject_hint_is_collective(name):
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(name or "").casefold())
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"^(?:the|a|an)\s+", "", normalized)
    return normalized in {
        "family", "crowd", "group", "people", "children", "adults",
        "visitors", "tourists", "guests", "workers", "staff", "guards",
        "soldiers", "aliens", "creatures", "monsters", "robots", "drones",
        "scouts", "figures", "bystanders", "pedestrians", "passengers",
    }


def _subject_name_is_promotable(name):
    """Reject labels that explicitly describe incidental or non-Subject roles."""
    normalized = _subject_identity_key(name)
    if not normalized or _subject_hint_is_collective(name):
        return False
    disallowed_words = {
        "anonymous", "background", "bystander", "crowd", "effect", "generic",
        "group", "incidental", "object", "passerby", "prop", "temporary",
        "unidentified", "unknown", "unnamed",
    }
    return not (set(normalized.split()) & disallowed_words)


def register_named_subject_hints(
    continuity_state,
    subject_definitions,
    detailed_description,
    subject_hints,
    origin_segment=None,
):
    """Register planned named characters only when they visibly appear now."""
    state = continuity_state_for_registry(
        subject_definitions,
        copy.deepcopy(continuity_state),
    )
    description = str(detailed_description or "")
    added_names = []
    for raw_name in subject_hints or []:
        name = " ".join(str(raw_name).split()).strip(" ,.;:-")
        if not _subject_name_is_promotable(name):
            continue
        if _find_existing_subject_name(state["subjects"], name) is not None:
            continue
        if re.search(
            rf"(?<![\w]){re.escape(name)}(?![\w])",
            description,
            re.I,
        ) is None:
            continue
        used_ids = {
            int(record.get("subject_id"))
            for record in state["subjects"].values()
            if str(record.get("subject_id", "")).isdigit()
        }
        subject_id = max(used_ids, default=0) + 1
        speaker_id = available_subject_speaker_id(
            subject_id,
            state["subjects"].values(),
        )
        state["subjects"][name] = new_subject_continuity_record({
            "subject_id": subject_id,
            "name": name,
            "gender": infer_subject_gender(description, name),
            "picture_ids": [],
            "picture_id": None,
            "speaker_id": speaker_id,
            "origin_segment": origin_segment,
        })
        added_names.append(name)
    return state, added_names


def register_inline_dialogue_subjects(
    continuity_state,
    subject_definitions,
    detailed_description,
    origin_segment=None,
):
    """Persist stable identities declared by dialogue attribution."""
    state = continuity_state_for_registry(
        subject_definitions,
        copy.deepcopy(continuity_state),
    )
    added_names = []
    for speaking_subject in extract_dialogue_subject_declarations(
        detailed_description
    ):
        proposed_name = speaking_subject["name"]
        existing_name = _find_existing_subject_name(
            state["subjects"],
            proposed_name,
        )
        if existing_name is not None:
            continue

        subject_id = int(speaking_subject["subject_id"])
        speaker_id = str(speaking_subject["speaker_id"]).upper()
        subject_collision = any(
            str(record.get("subject_id")) == str(subject_id)
            for record in state["subjects"].values()
        )
        speaker_collision = any(
            str(record.get("speaker_id") or "").casefold()
            == speaker_id.casefold()
            for record in state["subjects"].values()
        )
        if subject_collision or speaker_collision:
            print(
                "WARNING: Ignoring colliding dialogue Subject "
                f"{proposed_name!r} (<Subject {subject_id}>, {speaker_id})."
            )
            continue

        state["subjects"][proposed_name] = new_subject_continuity_record({
            **speaking_subject,
            "gender": infer_subject_gender(
                detailed_description,
                proposed_name,
            ),
            "origin_segment": origin_segment,
        })
        added_names.append(proposed_name)
    return state, added_names


def _complete_partial_continuity_candidate(candidate, committed_snapshot):
    """Backfill omitted fields without overriding explicit candidate values.

    Local models occasionally return a useful continuity delta despite being
    asked for a complete snapshot. Rejecting that whole response silently
    freezes wardrobe and Subject persistence. Stable/omitted data is therefore
    inherited here, while explicit ``N/A`` and empty arrays retain replacement
    semantics.
    """
    candidate = copy.deepcopy(candidate)
    candidate.setdefault("version", CONTINUITY_STATE_VERSION)
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        candidate.setdefault(field, "N/A")

    environment = candidate.get("environment")
    if not isinstance(environment, dict):
        environment = {}
        candidate["environment"] = environment
    committed_environment = committed_snapshot.get("environment", {})
    environment.setdefault(
        "location",
        committed_environment.get("location", "N/A"),
    )
    environment.setdefault("persistent_state", "N/A")

    subjects = candidate.get("subjects")
    if subjects is None:
        subjects = {}
        candidate["subjects"] = subjects
    elif not isinstance(subjects, dict):
        return candidate

    committed_subjects = committed_snapshot.get("subjects", {})
    known_by_name = {
        name.casefold(): (name, record)
        for name, record in committed_subjects.items()
        if isinstance(record, dict)
    }
    known_by_id = {
        str(record.get("subject_id")): (name, record)
        for name, record in committed_subjects.items()
        if isinstance(record, dict) and record.get("subject_id") is not None
    }
    supplied_known_names = set()
    defaults = new_subject_continuity_record({
        "subject_id": 0,
        "name": "",
        "picture_ids": [],
        "picture_id": None,
        "speaker_id": None,
        "origin_segment": None,
    })

    for raw_name, record in list(subjects.items()):
        if not isinstance(record, dict):
            continue
        raw_text = str(raw_name).strip()
        known = known_by_name.get(raw_text.casefold())
        if known is None and raw_text.isdigit():
            known = known_by_id.get(raw_text)
        if known is None:
            proposed_name = str(record.get("name", "")).strip()
            known = known_by_name.get(proposed_name.casefold())
        if known is None and record.get("subject_id") is not None:
            known = known_by_id.get(str(record.get("subject_id")))

        if known is not None:
            canonical_name, baseline = known
            supplied_known_names.add(canonical_name)
        else:
            canonical_name = str(record.get("name") or raw_text).strip()
            baseline = defaults

        record.setdefault("subject_id", baseline.get("subject_id", 0))
        record.setdefault("name", baseline.get("name") or canonical_name)
        record.setdefault("gender", baseline.get("gender", "N/A"))
        record.setdefault("picture_ids", list(baseline.get("picture_ids", [])))
        record.setdefault("picture_id", baseline.get("picture_id"))
        record.setdefault("speaker_id", baseline.get("speaker_id"))
        record.setdefault("origin_segment", baseline.get("origin_segment"))
        record["persistent_structural_change"] = bool(
            baseline.get("persistent_structural_change", False)
        )
        for field in CURRENT_SUBJECT_SCALAR_FIELDS:
            # Inherit stable current-frame scalars from the baseline when the
            # candidate omits them. Only an explicit N/A should signal a
            # deliberate clearing.
            record.setdefault(field, baseline.get(field, "N/A"))
        for field in PERSISTENT_SUBJECT_SCALAR_FIELDS:
            record.setdefault(field, baseline.get(field, "N/A"))

        wardrobe = record.get("wardrobe")
        if not isinstance(wardrobe, dict):
            wardrobe = {}
            record["wardrobe"] = wardrobe
        baseline_wardrobe = baseline.get("wardrobe", {})
        for field in ("upper", "lower", "footwear", "other"):
            wardrobe.setdefault(field, baseline_wardrobe.get(field, "N/A"))
        for field in SUBJECT_LIST_FIELDS:
            record.setdefault(field, list(baseline.get(field, [])))
        for field in CURRENT_SUBJECT_LIST_FIELDS:
            record.setdefault(field, [])

    for name, record in committed_subjects.items():
        if name not in supplied_known_names:
            inherited = copy.deepcopy(record)
            for field in CURRENT_SUBJECT_SCALAR_FIELDS:
                inherited[field] = "N/A"
            for field in CURRENT_SUBJECT_LIST_FIELDS:
                inherited[field] = []
            subjects[name] = inherited
    return candidate


def _coerce_continuity_string(value, field_name=""):
    """Repair harmless scalar/list representation mistakes from a local LLM."""
    if isinstance(value, str):
        return value
    if value is None:
        return "N/A"
    if isinstance(value, (list, tuple)):
        parts = [
            cleaned
            for item in value
            if (cleaned := _continuity_item_text(item, field_name))
        ]
        return "; ".join(parts) if parts else "N/A"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return "N/A"


def _coerce_continuity_candidate_types(candidate):
    if not isinstance(candidate, dict):
        return candidate
    candidate = copy.deepcopy(candidate)
    environment = candidate.get("environment")
    if isinstance(environment, dict):
        for field in ("location", "persistent_state"):
            if field in environment:
                environment[field] = _coerce_continuity_string(
                    environment[field],
                    f"environment.{field}",
                )
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        if field in candidate:
            candidate[field] = _coerce_continuity_string(candidate[field], field)

    subjects = candidate.get("subjects")
    if not isinstance(subjects, dict):
        return candidate
    for raw_name, record in subjects.items():
        if not isinstance(record, dict):
            continue
        for field in (
            "position", "pose_action", "topology", "body_state",
            "physical_condition",
        ):
            if field in record:
                record[field] = _coerce_continuity_string(record[field], field)
        wardrobe = record.get("wardrobe")
        if isinstance(wardrobe, dict):
            for garment in ("upper", "lower", "footwear", "other"):
                if garment in wardrobe:
                    wardrobe[garment] = _coerce_continuity_string(
                        wardrobe[garment],
                        f"wardrobe.{garment}",
                    )
        for field in SUBJECT_LIST_FIELDS:
            if field not in record:
                continue
            value = record[field]
            if isinstance(value, tuple):
                record[field] = list(value)
            elif isinstance(value, str):
                record[field] = [] if value.strip().upper() == "N/A" else [value]
            elif isinstance(value, dict):
                record[field] = [value]
        for field in ("subject_id", "origin_segment", "picture_id"):
            value = record.get(field)
            if isinstance(value, str) and value.strip().isdigit():
                record[field] = int(value.strip())
        if isinstance(record.get("picture_ids"), tuple):
            record["picture_ids"] = list(record["picture_ids"])
        if isinstance(record.get("picture_ids"), list):
            record["picture_ids"] = [
                int(value) if isinstance(value, str) and value.strip().isdigit() else value
                for value in record["picture_ids"]
            ]
        if isinstance(record.get("speaker_id"), int):
            record["speaker_id"] = f"S{record['speaker_id']}"
        if "name" not in record or not str(record.get("name") or "").strip():
            record["name"] = str(raw_name)
    return candidate


def _known_replacement_value(value, field_name=""):
    """Return a usable new value, or None when the candidate says unknown."""
    cleaned = _scrub_snapshot_text(
        _coerce_continuity_string(value, field_name),
        field_name,
    )
    if not cleaned or re.match(r"(?i)^N/A(?:\b|\s|[(:;\-\[])", cleaned):
        return None
    return cleaned


_COMPLETED_ACTION_RE = re.compile(
    r"(?i)^(?:the\s+)?(?:action\s+)?(?:has\s+|is\s+)?"
    r"(?:complete(?:d)?|finish(?:ed)?|ended|stopped|ceased|done)\b"
)


def _current_frame_replacement_value(value, field_name=""):
    """Normalize a current-frame value while preserving an explicit N/A."""
    cleaned = _scrub_snapshot_text(
        _coerce_continuity_string(value, field_name),
        field_name,
    )
    if field_name == "ongoing_action" and _COMPLETED_ACTION_RE.search(cleaned):
        return "N/A"
    return cleaned or "N/A"


_WARDROBE_COMPONENT_PATTERNS = {
    "upper": re.compile(
        r"(?i)\b(?:shirt|blouse|top|sweater|sweatshirt|hoodie|jacket|coat|"
        r"blazer|vest|waistcoat|tunic|jersey|cardigan|bodice)s?\b"
    ),
    "lower": re.compile(
        r"(?i)\b(?:pants?|trousers?|jeans|shorts|skirt|leggings|slacks|"
        r"breeches|culottes|bottoms?|lower\s+garments?)\b"
    ),
    "footwear": re.compile(
        r"(?i)\b(?:shoes?|boots?|sneakers?|sandals?|heels?|loafers?|"
        r"slippers?|footwear)\b"
    ),
    "other": re.compile(
        r"(?i)\b(?:dress|gown|robe|jumpsuit|coveralls|overalls|hat|cap|"
        r"scarf|tie|belt|gloves?|necklace|bracelet|watch|glasses|"
        r"accessor(?:y|ies))\b"
    ),
}


_WARDROBE_ONLY_STATE_RE = re.compile(
    r"(?i)\b(?:nude|naked|unclothed|undressed|shirtless|topless|"
    r"bottomless|pantsless|trouserless|barefoot|bare[- ]chested)\b"
)


def _continuity_fact_belongs_to_wardrobe(value):
    """Return whether a persistent-effect string is actually clothing state."""
    text = str(value or "").strip()
    if not text:
        return False
    if _WARDROBE_ONLY_STATE_RE.search(text):
        return True
    return any(
        pattern.search(text)
        for pattern in _WARDROBE_COMPONENT_PATTERNS.values()
    )


def _remove_wardrobe_owned_persistent_effects(record):
    """Keep wardrobe/nudity state exclusively in the structured wardrobe slots."""
    if not isinstance(record, dict):
        return record
    effects = record.get("persistent_effects")
    if not isinstance(effects, list):
        return record

    filtered = []
    for item in effects:
        cleaned = _continuity_item_text(item, "persistent_effects")
        if not cleaned or _continuity_fact_belongs_to_wardrobe(cleaned):
            continue
        filtered.append(cleaned)
    record["persistent_effects"] = list(dict.fromkeys(filtered))
    return record

_WARDROBE_DESCRIPTION_RE = re.compile(
    r"(?i)\b(?:wears?|wearing|dressed\s+in|clad\s+in|draped\s+in|"
    r"outfitted\s+in|outfit\s+(?:consists?\s+of|comprises)|"
    r"two-piece\s+outfit\s+(?:consists?\s+of|with))\s+"
    r"(?P<items>[^.!?;\r\n]{1,240})"
)

_WARDROBE_ACTION_BOUNDARY_RE = re.compile(
    r"(?i)\s+\b(?:while|then|before|after|stands?|sits?|walks?|runs?|"
    r"moves?|turns?|looks?|holds?|carries?|raises?|lowers?(?!\s+garments?\b)|reaches?|"
    r"speaks?|says?|enters?|exits?)\b.*$"
)


def _wardrobe_component_field(value):
    """Return the structured slot named by an explicit garment phrase."""
    text = str(value or "")
    matches = [
        field for field, pattern in _WARDROBE_COMPONENT_PATTERNS.items()
        if pattern.search(text)
    ]
    return matches[0] if len(matches) == 1 else None


def _split_wardrobe_components(value):
    """Split a plainly enumerated outfit into independently classifiable parts."""
    text = str(value or "").strip(" ,;:-")
    if not text:
        return []
    text = _WARDROBE_ACTION_BOUNDARY_RE.sub("", text).strip(" ,;:-")
    raw_parts = re.split(
        r"\s*(?:;|,|\s+(?:and|plus)\s+)\s*",
        text,
        flags=re.IGNORECASE,
    )
    parts = []
    for raw_part in raw_parts:
        part = re.sub(r"(?i)^(?:and\s+)?(?:a|an|the)\s+", "", raw_part)
        part = part.strip(" ,;:-")
        field = _wardrobe_component_field(part)
        if part and field:
            parts.append((field, part))
    return parts


def _join_wardrobe_components(values):
    values = list(dict.fromkeys(value for value in values if value))
    return _english_join(values) if values else "N/A"


def _decompose_candidate_wardrobe(wardrobe):
    """Move enumerated garments out of an overloaded wardrobe slot."""
    if not isinstance(wardrobe, dict):
        return wardrobe
    original = {
        field: _known_replacement_value(wardrobe.get(field), f"wardrobe.{field}")
        for field in _WARDROBE_COMPONENT_PATTERNS
    }
    repaired = dict(wardrobe)
    for source_field, value in original.items():
        if value is None:
            continue
        components = _split_wardrobe_components(value)
        component_fields = {field for field, _ in components}
        if not components or (
            component_fields == {source_field} and len(components) == 1
        ):
            continue
        if len(component_fields) < 2 and source_field in component_fields:
            continue

        grouped = {}
        for field, component in components:
            grouped.setdefault(field, []).append(component)
        for field, values in grouped.items():
            repaired[field] = _join_wardrobe_components(values)
        if source_field not in grouped:
            repaired[source_field] = "N/A"
    return repaired


def _explicit_wardrobe_from_description(description, subject_name):
    """Extract only plainly stated, subject-scoped wardrobe enumerations."""
    text = str(description or "")
    name = str(subject_name or "").strip()
    if not name or not re.search(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", text):
        return {}
    context = _subject_description_context(text, name)
    extracted = {}
    for match in _WARDROBE_DESCRIPTION_RE.finditer(context):
        for field, component in _split_wardrobe_components(match.group("items")):
            extracted.setdefault(field, []).append(component)
    return {
        field: _join_wardrobe_components(values)
        for field, values in extracted.items()
    }


def _wardrobe_absence_fields(description, subject_name):
    """Find wardrobe slots whose absence is explicitly established."""
    text = str(description or "")
    name = str(subject_name or "").strip()
    if not name or not re.search(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", text):
        return set()
    context = _subject_description_context(text, name)
    absent = set()
    for field, garment_pattern in _WARDROBE_COMPONENT_PATTERNS.items():
        garment = garment_pattern.pattern.removeprefix("(?i)")
        patterns = (
            rf"(?i)\b(?:no|without)\b[^.!?;]{{0,50}}{garment}",
            rf"(?i){garment}[^.!?;]{{0,40}}\b(?:absent|gone|missing|"
            rf"removed|destroyed|discarded|torn\s+away)\b",
            rf"(?i)\b(?:removes?|discards?|loses?)\b[^.!?;]{{0,50}}{garment}",
        )
        if any(re.search(pattern, context) for pattern in patterns):
            absent.add(field)
    return absent


def _wardrobe_action_updates(description, subject_name):
    """Return final explicit put-on/take-off wardrobe actions for one Subject."""
    text = str(description or "")
    name = str(subject_name or "").strip()
    if not name or not re.search(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", text):
        return {}
    context = _subject_description_context(text, name)
    events = []
    possessive = r"(?:his|her|their|the|a|an)\s+"
    for field, garment_pattern in _WARDROBE_COMPONENT_PATTERNS.items():
        garment = garment_pattern.pattern.removeprefix("(?i)")
        removal_patterns = (
            rf"(?i)\b(?:takes?|took|taken|taking|pulls?|pulled|pulling)\s+"
            rf"(?:{possessive})?(?P<item>{garment})\s+off\b",
            rf"(?i)\b(?:takes?|took|taken|taking|pulls?|pulled|pulling)\s+off\s+"
            rf"(?:{possessive})?(?P<item>{garment})\b",
        )
        put_on_patterns = (
            rf"(?i)\b(?:puts?|put|putting|pulls?|pulled|pulling|slips?|slipped|slipping)\s+"
            rf"(?:{possessive})?(?P<item>{garment})\s+(?:back\s+)?on\b",
            rf"(?i)\b(?:puts?|put|putting|slips?|slipped|slipping)\s+on\s+"
            rf"(?:{possessive})?(?P<item>{garment})\b",
            rf"(?i)\b(?:dons?|donned|donning)\s+"
            rf"(?:{possessive})?(?P<item>{garment})\b",
        )
        for pattern in removal_patterns:
            for match in re.finditer(pattern, context):
                events.append((match.start(), field, "absent"))
        for pattern in put_on_patterns:
            for match in re.finditer(pattern, context):
                item = " ".join(str(match.group("item") or "").split()).strip()
                if item:
                    events.append((match.start(), field, item))

    updates = {}
    for _position, field, value in sorted(events, key=lambda event: event[0]):
        updates[field] = value
    return updates


def _repair_candidate_wardrobe_extraction(
    candidate,
    committed_snapshot,
    newest_description,
):
    """Complete explicit wardrobe extraction before snapshot normalization."""
    subjects = candidate.get("subjects")
    if not isinstance(subjects, dict):
        return candidate
    committed_subjects = committed_snapshot.get("subjects", {})
    for raw_name, record in subjects.items():
        if not isinstance(record, dict):
            continue
        name = str(record.get("name") or raw_name).strip()
        wardrobe = _decompose_candidate_wardrobe(record.get("wardrobe"))
        if not isinstance(wardrobe, dict):
            continue
        record["wardrobe"] = wardrobe
        committed_wardrobe = committed_subjects.get(name, {}).get("wardrobe", {})
        extracted = _explicit_wardrobe_from_description(
            newest_description,
            name,
        )
        for field, value in extracted.items():
            current = _known_replacement_value(
                wardrobe.get(field),
                f"wardrobe.{field}",
            )
            previous = _known_replacement_value(
                committed_wardrobe.get(field),
                f"wardrobe.{field}",
            )
            if current is None or (previous is not None and current == previous):
                wardrobe[field] = value

        for field in _wardrobe_absence_fields(newest_description, name):
            if field in extracted:
                continue
            current = _known_replacement_value(
                wardrobe.get(field),
                f"wardrobe.{field}",
            )
            previous = _known_replacement_value(
                committed_wardrobe.get(field),
                f"wardrobe.{field}",
            )
            if current is None or current == previous:
                wardrobe[field] = "absent"

        # Simple garment actions are deterministic state changes. Let Python
        # establish them directly instead of depending on the LLM to classify
        # phrases such as "took shirt off" or "put shirt on" correctly. The
        # last explicit action for each garment slot wins.
        for field, value in _wardrobe_action_updates(
            newest_description,
            name,
        ).items():
            wardrobe[field] = value
    return candidate


_CONTINUITY_FACT_STOPWORDS = frozenset({
    "about", "after", "again", "against", "along", "also", "around",
    "before", "being", "between", "camera", "continues", "current",
    "during", "final", "frame", "from", "have", "into", "latest",
    "near", "newest", "only", "other", "remains", "scene", "shot",
    "state", "still", "subject", "their", "there", "these", "they",
    "this", "through", "toward", "under", "visible", "where", "which",
    "while", "with",
})


def _continuity_fact_tokens(value):
    """Return lightweight comparison tokens for deterministic state cleanup."""
    tokens = []
    for raw_token in re.findall(r"[a-z0-9]+", str(value or "").casefold()):
        if len(raw_token) < 3 or raw_token in _CONTINUITY_FACT_STOPWORDS:
            continue
        token = raw_token
        if len(token) > 5 and token.endswith("ing"):
            token = token[:-3]
        elif len(token) > 4 and token.endswith("ed"):
            token = token[:-2]
        elif len(token) > 5 and token.endswith(("ches", "shes", "sses", "xes", "zes")):
            token = token[:-2]
        elif len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        tokens.append(token)
    return set(tokens)


def _continuity_fact_is_grounded(fact, description, ignored_terms=None):
    """Whether distinctive words from a proposed fact occur in source prose."""
    fact_tokens = _continuity_fact_tokens(fact)
    fact_tokens -= _continuity_fact_tokens(" ".join(ignored_terms or []))
    if not fact_tokens:
        return False
    source_tokens = _continuity_fact_tokens(description)
    return bool(fact_tokens & source_tokens)


def _continuity_fact_is_well_grounded(fact, description, ignored_terms=None):
    """Use a stricter match when deciding whether copied state is still true."""
    fact_tokens = _continuity_fact_tokens(fact)
    fact_tokens -= _continuity_fact_tokens(" ".join(ignored_terms or []))
    if not fact_tokens:
        return False
    matches = fact_tokens & _continuity_fact_tokens(description)
    required = 1 if len(fact_tokens) <= 2 else 2
    return len(matches) >= required


_TERMINAL_RESTORATION_RE = re.compile(
    r"(?i)\b(?:restore[sd]?|restoring|replace[sd]?|replacing|"
    r"reconstruct(?:s|ed|ing)?|rebuild(?:s|ing)?|rebuilt|"
    r"regenerat(?:e|es|ed|ing)|reappear(?:s|ed|ing)?|return(?:s|ed|ing)?|"
    r"reattach(?:es|ed|ing)?|reinstall(?:s|ed|ing)?|"
    r"repair(?:s|ed|ing)?|renew(?:s|ed|ing)?|"
    r"put(?:s|ting)? on|don(?:s|ned|ning)?|equip(?:s|ped|ping)?|"
    r"acquir(?:e|es|ed|ing)|receiv(?:e|es|ed|ing)|fit(?:s|ted|ting)?)\b"
)
_TERMINAL_GENERIC_TOKENS = frozenset({
    "absent", "destroy", "gone", "missing", "present", "remove",
    "state", "current", "remain",
})


def _terminal_state_target_tokens(value, field_name=""):
    """Return stable target words for matching an explicit restoration beat."""
    label = _terminal_state_label(value)
    source = label or str(value or "")
    tokens = _continuity_fact_tokens(source) - _TERMINAL_GENERIC_TOKENS
    if field_name.startswith("wardrobe."):
        garment = field_name.partition(".")[2]
        tokens.update(_continuity_fact_tokens(f"{garment} garment"))
    return tokens


def _active_beat_explicitly_restores(
    active_beat_text,
    committed_value,
    candidate_value,
    field_name="",
):
    """Require both a restoration action and its target in the ACTIVE beat."""
    beat = str(active_beat_text or "")
    if not beat.strip() or _TERMINAL_RESTORATION_RE.search(beat) is None:
        return False
    beat_tokens = _continuity_fact_tokens(beat)
    target_tokens = _terminal_state_target_tokens(committed_value, field_name)
    target_tokens.update(
        _terminal_state_target_tokens(candidate_value, field_name)
    )
    return bool(beat_tokens & target_tokens)


def _authoritative_terminal_replacement(
    committed_value,
    candidate_value,
    field_name,
    active_beat_text,
):
    """Keep terminal state unless the ACTIVE beat explicitly reverses it."""
    committed_clauses = [
        clause.strip(" ,;:-")
        for clause in re.split(r"\s*(?:;|\n+)\s*", str(committed_value or ""))
        if clause.strip(" ,;:-")
    ]
    candidate_clauses = [
        clause.strip(" ,;:-")
        for clause in re.split(r"\s*(?:;|\n+)\s*", str(candidate_value or ""))
        if clause.strip(" ,;:-")
    ]
    if len(committed_clauses) > 1 and any(
        _terminal_state_status(clause) is not None
        for clause in committed_clauses
    ):
        return "; ".join(_preserve_terminal_list_items(
            candidate_clauses,
            committed_clauses,
            field_name,
            active_beat_text,
        ))
    old_status = _terminal_state_status(committed_value)
    if old_status is None or candidate_value is None:
        return candidate_value
    new_status = _terminal_state_status(candidate_value)
    if new_status == old_status:
        return candidate_value
    if old_status == "destroyed" and new_status == "absent":
        return candidate_value
    if _active_beat_explicitly_restores(
        active_beat_text,
        committed_value,
        candidate_value,
        field_name,
    ):
        return candidate_value
    return _known_replacement_value(committed_value, field_name)


def _preserve_terminal_list_items(
    candidate_items,
    committed_items,
    field_name,
    active_beat_text,
):
    """Carry authoritative terminal list facts across non-restoration beats."""
    result = list(candidate_items)
    for old_item in committed_items or []:
        if _terminal_state_status(old_item) is None:
            continue
        related_candidates = [
            item for item in result
            if _terminal_state_target_tokens(old_item, field_name)
            & _terminal_state_target_tokens(item, field_name)
        ]
        if any(
            _active_beat_explicitly_restores(
                active_beat_text,
                old_item,
                item,
                field_name,
            )
            for item in related_candidates
        ):
            result = [item for item in result if item != old_item]
            continue
        result = [
            item for item in result
            if item not in related_candidates
            or _terminal_state_status(item) is not None
        ]
        if not any(
            str(item).casefold() == str(old_item).casefold()
            for item in result
        ):
            result.append(old_item)
    return list(dict.fromkeys(result))


def _current_scalar_replacement(value, committed_value, field_name, description):
    """Collapse obvious copy-forward-plus-append output to its newest clause.

    Singular current-state fields are especially prone to an LLM returning
    ``old value; new value``.  Only remove the old clause when it is reproduced
    verbatim and a later clause is grounded in the newest final-frame prose.
    """
    replacement = _known_replacement_value(value, field_name)
    previous = _known_replacement_value(committed_value, field_name)
    if replacement is None or previous is None or replacement == previous:
        return replacement

    clauses = [
        clause.strip(" ,;:-")
        for clause in re.split(r"\s*(?:;|\n+)\s*", replacement)
        if clause.strip(" ,;:-")
    ]
    if len(clauses) < 2:
        return replacement

    previous_folded = previous.casefold().strip(" ,;:-")
    old_clause_indexes = {
        index
        for index, clause in enumerate(clauses)
        if clause.casefold().strip(" ,;:-") == previous_folded
    }
    if not old_clause_indexes:
        return replacement

    final_excerpt = extract_final_timeline_excerpt(description)
    newer = [
        clause for index, clause in enumerate(clauses)
        if index not in old_clause_indexes
        and _continuity_fact_is_grounded(clause, final_excerpt)
    ]
    if not newer:
        return replacement
    cleaned = re.sub(
        r"(?i)^(?:and\s+)?(?:now|then|currently|instead)\s*[:, -]?\s*",
        "",
        newer[-1],
    ).strip(" ,;:-")
    return cleaned or replacement


def _remove_grounded_copied_prefix(value, committed_value, description):
    """Remove an exact committed prefix at a scene replacement boundary."""
    replacement = str(value or "").strip()
    previous = str(committed_value or "").strip()
    if not replacement or not previous:
        return replacement
    match = re.match(
        rf"(?is)^{re.escape(previous)}\s*(?:;|\n+|\bthen\b|\band\s+now\b)\s*(.+)$",
        replacement,
    )
    if not match:
        return replacement
    suffix = match.group(1).strip(" ,;:-")
    return (
        suffix
        if suffix and _continuity_fact_is_grounded(suffix, description)
        else replacement
    )


_LOCATION_TRANSITION_RE = re.compile(
    r"(?i)\b(?:"
    r"enter(?:s|ed|ing)?|exit(?:s|ed|ing)?|leav(?:e|es|ing)|left|arriv(?:e|es|ed|ing)|"
    r"transport(?:s|ed|ing)?|teleport(?:s|ed|ing)?|swallow(?:s|ed|ing)?|"
    r"emerg(?:e|es|ed|ing)|board(?:s|ed|ing)?|disembark(?:s|ed|ing)?|"
    r"cross(?:es|ed|ing)?\s+(?:into|through)|pass(?:es|ed|ing)?\s+through|"
    r"step(?:s|ped|ping)?\s+(?:inside|into|through)|"
    r"(?:pull(?:s|ed|ing)?|drag(?:s|ged|ging)?|carr(?:y|ies|ied|ying)|"
    r"tak(?:e|es|en|ing)|draw(?:s|n|ing)?)\s+[^.!?]{0,80}\binto|"
    r"(?:scene|view|shot)\s+(?:shifts?|cuts?)\s+to"
    r")\b"
)


def _location_transition_is_grounded(old_location, new_location, description):
    """Detect a clear boundary into a fundamentally different environment."""
    old_value = _known_replacement_value(old_location, "environment.location")
    new_value = _known_replacement_value(new_location, "environment.location")
    if old_value is None or new_value is None:
        return False
    if old_value.casefold() == new_value.casefold():
        return False

    final_excerpt = extract_final_timeline_excerpt(description)
    if not (
        _continuity_fact_is_well_grounded(new_value, final_excerpt)
        or _continuity_fact_is_well_grounded(new_value, description)
    ):
        return False

    old_tokens = _continuity_fact_tokens(old_value)
    new_tokens = _continuity_fact_tokens(new_value)
    location_descriptors = {
        "aboard", "above", "below", "inside", "interior", "outside",
        "exterior", "within",
    }
    old_tokens -= location_descriptors
    new_tokens -= location_descriptors
    old_containment = bool(re.search(r"(?i)\b(?:outside|exterior|open air)\b", old_value))
    new_containment = bool(re.search(r"(?i)\b(?:inside|interior|within|aboard)\b", new_value))
    containment_flip = old_containment and new_containment
    distinct_places = bool(old_tokens and new_tokens and old_tokens.isdisjoint(new_tokens))
    explicit_boundary = _LOCATION_TRANSITION_RE.search(str(description or "")) is not None
    newest_marker = re.search(
        r"(?i)\b(?:now|currently|by the final frame|at the final frame)\b",
        final_excerpt,
    ) is not None
    return containment_flip or (distinct_places and (explicit_boundary or newest_marker))


def _subject_description_context(newest_description, subject_name=None):
    """Limit removal evidence to sentences about the affected Subject."""
    text = str(newest_description or "")
    name = str(subject_name or "").strip()
    if not text.strip() or not name:
        return text
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if sentence.strip()
    ]
    matching = []
    for sentence in sentences:
        if re.search(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", sentence):
            # Prefer clause-level context when a sentence contains multiple
            # subjects. Split on commas, semicolons, and coordinating
            # conjunctions and return only clauses that mention the name.
            clauses = [c.strip() for c in re.split(r"[,;:\n]+|\b(?:and|but|while|when)\b", sentence) if c.strip()]
            clause_matches_idx = [i for i, c in enumerate(clauses) if re.search(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", c)]
            clause_matches = [clauses[i] for i in clause_matches_idx]
            # Include adjacent clauses that lack proper-name tokens (likely
            # modifiers such as appositives: "Maya, wearing a red jacket...").
            for i in clause_matches_idx:
                if i - 1 >= 0:
                    prev = clauses[i - 1]
                    if not re.search(r"\b[A-Z][a-z]{1,}\b", prev):
                        clause_matches.insert(0, prev)
                if i + 1 < len(clauses):
                    nxt = clauses[i + 1]
                    if not re.search(r"\b[A-Z][a-z]{1,}\b", nxt):
                        clause_matches.append(nxt)
            if clause_matches:
                matching.extend(clause_matches)
            else:
                matching.append(sentence)
    return " ".join(matching) if matching else text


def _explicit_list_clear_is_grounded(
    field_name,
    newest_description,
    subject_name=None,
):
    """Require field-specific visible evidence before [] erases old state."""
    text = (
        str(newest_description or "")
        if field_name == "spatial_relationships"
        else _subject_description_context(newest_description, subject_name)
    )
    if not text.strip():
        return False
    patterns = {
        "held_props": (
            r"(?i)\b(?:drop(?:s|ped|ping)?|release[sd]?|releasing|throw(?:s|n|ing)?|"
            r"sets? down|hands? over|gives?|gave|empty-?handed|hands? (?:free|empty))\b"
        ),
        "attached_objects": (
            r"(?i)\b(?:remove[sd]?|removing|detach(?:es|ed|ing)?|unfasten(?:s|ed|ing)?|"
            r"disconnect(?:s|ed|ing)?|pull(?:s|ed|ing)? off|"
            r"pull(?:s|ed|ing)?\b[^.!?]{0,80}\bout)\b"
        ),
        "injuries": (
            r"(?i)\b(?:heals?|healed|healing|wounds? close[sd]?|fully recovered)\b"
        ),
        "substances": (
            r"(?i)\b(?:wipe[sd]? (?:off|away)|wash(?:es|ed|ing)? (?:off|away)|"
            r"clean(?:s|ed|ing)? (?:off|away)|rinse[sd]? off)\b"
        ),
        "persistent_effects": (
            r"(?i)\b(?:stops?|stopp(?:ed|ing)|ceases?|ends?|fades? away|"
            r"dissipat(?:es|ed|ing)|goes? dark|stops? glowing)\b"
        ),
        "spatial_relationships": (
            r"(?i)\b(?:leav(?:e|es|ing)|left|depart(?:s|ed|ing)?|exit(?:s|ed|ing)?|"
            r"move(?:s|d|ing)? away|separat(?:e|es|ed|ing)|alone|"
            r"no longer (?:near|beside|behind|ahead|with|inside|under|above))\b"
        ),
    }
    return re.search(patterns.get(field_name, r"(?!x)x"), text) is not None


def _explicit_scalar_clear_is_grounded(
    field_name,
    committed_value,
    newest_description,
    subject_name=None,
):
    """Allow N/A to clear a known scalar only when the prose proves it ended."""
    text = _subject_description_context(newest_description, subject_name)
    if not text.strip() or _known_replacement_value(committed_value, field_name) is None:
        return False
    patterns = {
        "topology": r"(?i)\b(?:separat(?:e|es|ed|ing)|unfused|restored|returns? to normal)\b",
        "body_state": r"(?i)\b(?:restored|returns? to normal|regains?|reverts?|no longer)\b",
        "physical_condition": r"(?i)\b(?:calms?|composes?|recovers?|relaxes?|dries?|cleans? up|no longer)\b",
        "pose_action": r"(?i)\b(?:stops?|stopp(?:ed|ing)|ceases?|comes? to rest|stands? still|lies? still|motionless)\b",
    }
    return re.search(patterns.get(field_name, r"(?!x)x"), text) is not None


def _transient_clear_is_grounded(
    field_name,
    committed_value,
    newest_description,
    subject_names=None,
):
    """Recognize an explicit newest-frame replacement when the LLM says N/A."""
    previous = _known_replacement_value(committed_value, field_name)
    if previous is None:
        return False
    final_excerpt = extract_final_timeline_excerpt(newest_description)
    if _continuity_fact_is_grounded(
        previous,
        final_excerpt,
        ignored_terms=subject_names,
    ):
        return False
    patterns = {
        "camera": (
            r"(?i)\b(?:camera|shot|close-up|closeup|wide|medium|overhead|"
            r"tracking|static|pan(?:s|ned|ning)?|tilt(?:s|ed|ing)?|zoom(?:s|ed|ing)?)\b"
        ),
        "ongoing_action": (
            r"(?i)\b(?:stops?|stopp(?:ed|ing)|ceases?|ends?|finishes?|comes? to rest|"
            r"stands?|sits?|kneels?|lies?|rests?|motionless)\b"
        ),
        "ongoing_audio": (
            r"(?i)\b(?:falls? silent|silence|quiet|stops?|stopp(?:ed|ing)|ceases?|ends?|"
            r"hum(?:s|ming)?|buzz(?:es|ing)?|music|voice|sound|noise|echo(?:es|ing)?)\b"
        ),
    }
    return re.search(patterns.get(field_name, r"(?!x)x"), final_excerpt) is not None


def _environment_clear_is_grounded(committed_value, newest_description):
    """Allow an unknown candidate to remove explicitly ended scene activity."""
    previous = _known_replacement_value(
        committed_value,
        "environment.persistent_state",
    )
    if previous is None:
        return False
    text = str(newest_description or "")
    if not _continuity_fact_is_grounded(previous, text):
        return False
    return re.search(
        r"(?i)\b(?:stops?|stopp(?:ed|ing)|ceases?|ends?|shuts? down|powers? down|turns? off|"
        r"goes? dark|falls? still|settles?|dissipat(?:es|ed|ing)|"
        r"fades? away|is no longer)\b",
        text,
    ) is not None


def _current_list_replacement(
    cleaned,
    committed_items,
    field_name,
    newest_description,
    subject_name,
    all_subject_names,
    location_transition=False,
):
    """Drop obvious copied-forward obsolete entries from current list fields."""
    if not cleaned:
        return cleaned
    committed_by_folded = {
        str(item).casefold(): str(item)
        for item in committed_items or []
    }
    has_new_fact = any(item.casefold() not in committed_by_folded for item in cleaned)
    if not has_new_fact and not location_transition:
        return cleaned

    final_excerpt = extract_final_timeline_excerpt(newest_description)
    if field_name == "spatial_relationships":
        return [
            item for item in cleaned
            if item.casefold() not in committed_by_folded
            or _continuity_fact_is_well_grounded(
                item,
                final_excerpt,
                ignored_terms=all_subject_names,
            )
        ]

    if not (
        has_new_fact
        and _explicit_list_clear_is_grounded(
            field_name,
            newest_description,
            subject_name=subject_name,
        )
    ):
        return cleaned

    ignored_tokens = _continuity_fact_tokens(" ".join(all_subject_names))
    new_items = [
        item for item in cleaned
        if item.casefold() not in committed_by_folded
    ]

    def copied_item_was_replaced(item):
        item_tokens = _continuity_fact_tokens(item) - ignored_tokens
        return any(
            item_tokens & (_continuity_fact_tokens(new_item) - ignored_tokens)
            for new_item in new_items
        )

    return [
        item for item in cleaned
        if item.casefold() not in committed_by_folded
        or not copied_item_was_replaced(item)
    ]


def normalize_structured_continuity_state(
    candidate,
    subject_definitions,
    committed_state=None,
    origin_segment=None,
    newest_description="",
    active_beat_text="",
    future_beat_texts=None,
    new_subjects=None,
):
    if not isinstance(candidate, dict):
        return None

    subject_scalar_fields = (
        "position",
        "pose_action",
        "topology",
        "body_state",
        "physical_condition",
    )
    wardrobe_fields = ("upper", "lower", "footwear", "other")
    subject_list_fields = SUBJECT_LIST_FIELDS

    committed_snapshot = continuity_state_for_registry(
        subject_definitions,
        committed_state,
    )
    candidate = _coerce_continuity_candidate_types(candidate)
    candidate = _complete_partial_continuity_candidate(
        candidate,
        committed_snapshot,
    )
    candidate = _repair_candidate_wardrobe_extraction(
        candidate,
        committed_snapshot,
        newest_description,
    )

    candidate_subjects = candidate.get("subjects")
    if isinstance(candidate_subjects, dict):
        for record in candidate_subjects.values():
            if isinstance(record, dict):
                record["gender"] = normalize_subject_gender(record.get("gender"))

    def candidate_error():
        required_top_level = {
            "version", "environment", "camera", "subjects",
            "ongoing_action", "ongoing_audio",
        }
        missing = sorted(required_top_level - set(candidate))
        if missing:
            return f"missing top-level field(s): {', '.join(missing)}"
        if isinstance(candidate.get("version"), bool) or not isinstance(
            candidate.get("version"), int
        ):
            return "version must be an integer"
        environment = candidate.get("environment")
        if not isinstance(environment, dict):
            return "environment must be an object"
        for field in ("location", "persistent_state"):
            if field not in environment or not isinstance(environment[field], str):
                return f"environment.{field} must be a string"
        for field in ("camera", "ongoing_action", "ongoing_audio"):
            if not isinstance(candidate.get(field), str):
                return f"{field} must be a string"
        subjects = candidate.get("subjects")
        if not isinstance(subjects, dict):
            return "subjects must be an object"
        for raw_name, record in subjects.items():
            label = str(raw_name)
            if not isinstance(record, dict):
                return f"subjects.{label} must be an object"
            identity_types = {
                "subject_id": lambda value: isinstance(value, int)
                and not isinstance(value, bool),
                "name": lambda value: isinstance(value, str),
                "gender": lambda value: isinstance(value, str),
                "picture_ids": lambda value: isinstance(value, list),
                "picture_id": lambda value: value is None
                or (isinstance(value, int) and not isinstance(value, bool)),
                "speaker_id": lambda value: value is None or isinstance(value, str),
                "origin_segment": lambda value: value is None
                or (isinstance(value, int) and not isinstance(value, bool)),
            }
            for field, valid in identity_types.items():
                if field not in record or not valid(record[field]):
                    return f"subjects.{label}.{field} has an invalid type"
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in record["picture_ids"]
            ):
                return f"subjects.{label}.picture_ids must contain integers"
            for field in subject_scalar_fields:
                if field not in record or not isinstance(record[field], str):
                    return f"subjects.{label}.{field} must be a string"
            wardrobe = record.get("wardrobe")
            if not isinstance(wardrobe, dict):
                return f"subjects.{label}.wardrobe must be an object"
            for field in wardrobe_fields:
                if field not in wardrobe or not isinstance(wardrobe[field], str):
                    return f"subjects.{label}.wardrobe.{field} must be a string"
            for field in subject_list_fields:
                if field not in record or not isinstance(record[field], list):
                    return f"subjects.{label}.{field} must be an array"

        known_by_folded_name = {
            name.casefold(): name
            for name in committed_snapshot.get("subjects", {})
        }
        known_by_identity_key = {
            _subject_identity_key(name): name
            for name in committed_snapshot.get("subjects", {})
            if _subject_identity_key(name)
        }
        known_by_id = {
            str(record.get("subject_id")): name
            for name, record in committed_snapshot.get("subjects", {}).items()
            if record.get("subject_id") is not None
        }
        supplied_known_names = set()
        for raw_name, record in subjects.items():
            raw_text = str(raw_name).strip()
            resolved_name = known_by_folded_name.get(raw_text.casefold())
            if resolved_name is None:
                resolved_name = known_by_identity_key.get(
                    _subject_identity_key(raw_text)
                )
            if resolved_name is None and raw_text.isdigit():
                resolved_name = known_by_id.get(raw_text)
            if resolved_name is None:
                candidate_name = str(record.get("name", "")).strip()
                resolved_name = known_by_folded_name.get(candidate_name.casefold())
                if resolved_name is None:
                    resolved_name = known_by_identity_key.get(
                        _subject_identity_key(candidate_name)
                    )
            if resolved_name is None:
                resolved_name = known_by_id.get(str(record.get("subject_id")))
            if resolved_name is not None:
                supplied_known_names.add(resolved_name)
        missing_subjects = sorted(
            set(committed_snapshot.get("subjects", {})) - supplied_known_names
        )
        if missing_subjects:
            return "missing known Subject record(s): " + ", ".join(missing_subjects)
        return None

    validation_error = candidate_error()
    if validation_error:
        print(f"[Continuity] canonical replacement rejected: {validation_error}")
        return None

    # COPY FORWARD FIRST. This is the central continuity invariant.
    state = continuity_state_for_registry(
        subject_definitions,
        copy.deepcopy(committed_snapshot),
    )

    state, _ = register_inline_dialogue_subjects(
        state,
        subject_definitions,
        newest_description,
        origin_segment=origin_segment,
    )
    state, _ = register_named_subject_hints(
        state,
        subject_definitions,
        newest_description,
        new_subjects,
        origin_segment=origin_segment,
    )

    id_to_name = {
        str(record.get("subject_id")): name
        for name, record in state["subjects"].items()
        if record.get("subject_id") is not None
    }

    committed_environment = committed_snapshot.get("environment", {})
    candidate_location = _current_scalar_replacement(
        candidate["environment"].get("location"),
        committed_environment.get("location", "N/A"),
        "environment.location",
        newest_description,
    )
    if candidate_location is not None:
        state["environment"]["location"] = candidate_location

    location_transition = _location_transition_is_grounded(
        committed_environment.get("location", "N/A"),
        candidate_location,
        newest_description,
    )

    # These fields describe only the newest final frame. Unknown or absent
    # values intentionally replace the prior segment instead of inheriting it.
    state["environment"]["persistent_state"] = (
        _current_frame_replacement_value(
            candidate["environment"].get("persistent_state"),
            "environment.persistent_state",
        )
    )
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        state[field] = _current_frame_replacement_value(
            candidate.get(field),
            field,
        )

    def resolve_subject_name(raw_name, record):
        proposed_name = str(record.get("name", raw_name)).strip()
        resolved = _find_existing_subject_name(
            state["subjects"],
            proposed_name or raw_name,
        )
        if resolved is not None:
            return resolved
        raw_text = str(raw_name)
        if raw_text.isdigit():
            mapped = id_to_name.get(raw_text)
            if mapped:
                return mapped
        if not proposed_name or proposed_name.isdigit():
            return None
        return None

    for raw_name, record in candidate["subjects"].items():
        name = resolve_subject_name(raw_name, record)
        if name is None:
            proposed_name = str(record.get("name", raw_name)).strip()
            if not proposed_name or proposed_name.isdigit():
                continue
            if not _subject_name_is_promotable(proposed_name):
                print(
                    "WARNING: Ignoring anonymous, collective, or temporary "
                    f"video-only subject {proposed_name!r}."
                )
                continue
            if not _new_subject_is_animate(record):
                print(
                    "WARNING: Ignoring inanimate or unclassified video-only "
                    f"subject {proposed_name!r}; new Subjects require "
                    "entity_kind='animate'."
                )
                continue
            if _future_subject_name_is_reserved(
                proposed_name,
                active_beat_text,
                future_beat_texts,
            ):
                print(
                    "WARNING: Ignoring premature future-beat subject "
                    f"{proposed_name!r}."
                )
                continue
            used_ids = {
                int(current.get("subject_id"))
                for current in state["subjects"].values()
                if str(current.get("subject_id", "")).isdigit()
            }
            try:
                proposed_id = int(record.get("subject_id"))
            except (TypeError, ValueError):
                proposed_id = None
            if proposed_id is None or proposed_id <= 0 or proposed_id in used_ids:
                proposed_id = max(used_ids, default=0) + 1
            proposed_speaker_id = available_subject_speaker_id(
                proposed_id,
                state["subjects"].values(),
                record.get("speaker_id"),
            )
            try:
                created_in_segment = int(origin_segment)
            except (TypeError, ValueError):
                try:
                    created_in_segment = int(record.get("origin_segment"))
                except (TypeError, ValueError):
                    created_in_segment = None
            name = proposed_name
            state["subjects"][name] = new_subject_continuity_record({
                "subject_id": proposed_id,
                "name": name,
                "gender": normalize_subject_gender(record.get("gender")),
                "picture_ids": [],
                "picture_id": None,
                "speaker_id": proposed_speaker_id,
                "origin_segment": created_in_segment,
            })
            id_to_name[str(proposed_id)] = name
            print(
                f"[Continuity] registered new Subject {name!r} as "
                f"<Subject {proposed_id}> ({proposed_speaker_id})."
            )

        target = state["subjects"][name]
        committed_record = committed_snapshot.get("subjects", {}).get(name, {})

        # Identity never drifts for an existing Subject.
        if committed_record:
            for identity_field in (
                "subject_id", "name", "gender", "picture_ids", "picture_id",
                "speaker_id", "origin_segment", "persistent_structural_change",
            ):
                if identity_field in committed_record:
                    target[identity_field] = copy.deepcopy(committed_record[identity_field])

        for field in CURRENT_SUBJECT_SCALAR_FIELDS:
            target[field] = _current_frame_replacement_value(
                record.get(field),
                field,
            )

        for field in PERSISTENT_SUBJECT_SCALAR_FIELDS:
            value = _known_replacement_value(record.get(field), field)
            if value is None:
                if _explicit_scalar_clear_is_grounded(
                    field,
                    committed_record.get(field, "N/A"),
                    newest_description,
                    subject_name=name,
                ):
                    target[field] = "N/A"
                continue
            value = _current_scalar_replacement(
                value,
                committed_record.get(field, "N/A"),
                field,
                newest_description,
            )
            if field in {"topology", "body_state"}:
                value = _authoritative_terminal_replacement(
                    committed_record.get(field, "N/A"),
                    value,
                    field,
                    active_beat_text,
                )
            if (
                committed_record
                and CONTINUITY_REJECT_UNEVIDENCED_STRUCTURAL_CHANGES
                and field in {"topology", "body_state"}
                and value != _known_replacement_value(
                    committed_record.get(field, "N/A"), field
                )
                and not _structural_change_has_evidence(
                    name,
                    value,
                    newest_description,
                )
            ):
                print(
                    "WARNING: Ignoring unevidenced structural continuity "
                    f"change for {name} ({field}): {value!r}"
                )
                continue
            previous_value = _known_replacement_value(
                committed_record.get(field, "N/A"),
                field,
            )
            target[field] = value
            if (
                field in {"topology", "body_state"}
                # Establishing an UNKNOWN/N/A structural field for the first
                # time is state bootstrapping, not a structural change. Only a
                # change from an already-known structural value makes pristine
                # Picture references incompatible.
                and previous_value is not None
                and value != previous_value
            ):
                target["persistent_structural_change"] = True

        wardrobe = record.get("wardrobe", {})
        for garment in wardrobe_fields:
            wardrobe_field = f"wardrobe.{garment}"
            value = _known_replacement_value(
                wardrobe.get(garment),
                wardrobe_field,
            )
            if value is not None:
                value = _authoritative_terminal_replacement(
                    committed_record.get("wardrobe", {}).get(garment, "N/A"),
                    value,
                    wardrobe_field,
                    active_beat_text,
                )
                target["wardrobe"][garment] = value

        for field in CURRENT_SUBJECT_LIST_FIELDS:
            target[field] = list(dict.fromkeys(
                item
                for raw_item in record.get(field, [])
                if (item := _continuity_item_text(raw_item, field))
            ))

        for field in (*PERSISTENT_SUBJECT_LIST_FIELDS, "held_props"):
            cleaned = list(dict.fromkeys(
                item
                for raw_item in record.get(field, [])
                if (item := _continuity_item_text(raw_item, field))
            ))
            cleaned = _current_list_replacement(
                cleaned,
                committed_record.get(field, []),
                field,
                newest_description,
                name,
                state["subjects"].keys(),
                location_transition=location_transition,
            )
            cleaned = _preserve_terminal_list_items(
                cleaned,
                committed_record.get(field, []),
                field,
                active_beat_text,
            )
            if cleaned:
                # A non-empty candidate is treated as the model's complete
                # current list, preventing indefinite historical accumulation.
                target[field] = cleaned
            elif target.get(field) and _explicit_list_clear_is_grounded(
                field,
                newest_description,
                subject_name=name,
            ):
                target[field] = []
            # Otherwise [] means "no reliable update" and the committed list
            # survives. This prevents silent loss of lasting physical state.

    state["version"] = CONTINUITY_STATE_VERSION
    state = scrub_continuity_state(state)

    def brief(value):
        rendered = json.dumps(value, ensure_ascii=False)
        return rendered if len(rendered) <= 120 else rendered[:117] + "..."

    print("[Continuity] copy-forward patch accepted")
    if location_transition:
        print(
            "[Continuity] location transition cleanup: "
            f"{brief(committed_environment.get('location', 'N/A'))} -> "
            f"{brief(state['environment']['location'])}"
        )
    for field in ("camera", "ongoing_action", "ongoing_audio"):
        old_value = committed_snapshot.get(field, "N/A")
        if old_value != state[field]:
            print(f"[Continuity] {field}: {brief(old_value)} -> {brief(state[field])}")
    old_names = set(committed_snapshot.get("subjects", {}))
    new_names = set(state.get("subjects", {})) - old_names
    if new_names:
        print("[Continuity] new Subjects: " + ", ".join(sorted(new_names)))
    return state


COMBINED_CONTINUITY_SYSTEM = (
    "You are a state continuity maintainer and editor. You take the end state "
    "of characters and setting from a scene and output, in JSON format, the "
    "reduced continuity state needed to open the next segment of the same "
    "movie. Determine what is visibly or audibly true when the segment has "
    "ended. Keep only the facts necessary to maintain continuity into the next "
    "segment. Remove temporary, completed, redundant, historical, or "
    "non-visual/non-audio information. Describe only the final state, with no "
    "timestamps and no sequence of earlier actions. Do not invent anything "
    "that is not established by the input. Return only one JSON object with no "
    "prose before or after it."
)

PHASE_2_CONTINUITY_H3_SYSTEM = (
    "You are a MiniMax H3 diffusion video prompt writer.  You only write the "
    "continuity state of the prompt that comes before the actual actions happening "
    "in the video. You only describe the opening of the video segment. You keep "
    "it short and succinct. No \"setting the mood\", only facts. Do not include "
    "any timestamps. Do not quibble over small things like \"~10 degrees\". You "
    "are given the overall phase and then the end state of the last segment. "
    "Write as a short opening to a story."
)


def _continuity_json_text(value):
    """Render one LLM JSON result without semantic editing between phases."""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, indent=2)


def _parse_continuity_json_result(raw_result, phase_name):
    """Require a JSON object for the combined continuity call."""
    candidate = raw_result
    if isinstance(candidate, str):
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(f"{phase_name} did not return valid JSON.") from error
    if not isinstance(candidate, dict):
        raise ValueError(f"{phase_name} must return a JSON object.")
    return candidate


def _normalize_continuity_opening_text(raw_result):
    """Return Phase 2 as short plain prose, without adding continuity facts."""
    if isinstance(raw_result, dict):
        # Be tolerant if the model wraps otherwise-correct prose in one key.
        if len(raw_result) == 1:
            value = next(iter(raw_result.values()))
            if isinstance(value, str):
                raw_result = value
        if isinstance(raw_result, dict):
            raw_result = json.dumps(raw_result, ensure_ascii=False)
    text = str(raw_result or "").strip()
    if text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:-3].strip()
    return text


def _print_continuity_phase_result(phase_number, title, value):
    print()
    print("=" * 64)
    print(f"CONTINUITY PHASE {phase_number}: {title}")
    print("=" * 64)
    print(_continuity_json_text(value) if phase_number < 2 else str(value))
    print("=" * 64)


def request_continuity_opening_state(
    reduced_state,
    current_phase,
    llm_request=None,
    history_metadata=None,
):
    """Run only continuity Phase 2 from an already-finalized end state."""
    if llm_request is None:
        llm_request = ask_llm
    phase_json = json.dumps(current_phase or {}, ensure_ascii=False, indent=2)
    state_text = _continuity_json_text(reduced_state)
    phase2_messages = [
        {"role": "system", "content": PHASE_2_CONTINUITY_H3_SYSTEM},
        {"role": "user", "content": phase_json + "\n\n" + state_text},
    ]
    metadata = dict(history_metadata or {})
    metadata.update({"purpose": "continuity_phase_2_h3_opening", "content_attempt": 1})
    raw_opening = llm_request(
        phase2_messages,
        response_format=None,
        temperature=0.10,
        top_p=0.90,
        max_tokens=2000,
        **({"history_metadata": metadata} if metadata else {}),
    )
    opening_state = _normalize_continuity_opening_text(raw_opening)
    if not opening_state:
        raise RuntimeError("Continuity Phase 2 returned an empty opening state.")
    _print_continuity_phase_result(2, "H3 OPENING STATE", opening_state)
    return opening_state


def request_combined_continuity(
    h3_prompt,
    current_phase,
    llm_request=None,
    history_metadata=None,
    content_attempts=SUMMARY_CONTENT_ATTEMPTS,
    defer_opening=False,
):
    """Run the single combined continuity extraction/reduction call.

    The combined call is Phase 1: it reads the final H3 prompt and directly
    returns the reduced continuity JSON needed for the next segment, replacing
    the former Phase 1 (full end state) and Phase 2 (reduction) pair. Phase 2
    (the H3 opening prose) is optionally deferred until rendered visual facts
    are available.
    """
    if llm_request is None:
        llm_request = ask_llm
    attempts = max(1, int(content_attempts))

    combined_messages = [
        {"role": "system", "content": COMBINED_CONTINUITY_SYSTEM},
        {"role": "user", "content": str(h3_prompt or "").strip()},
    ]
    reduced_state = None
    combined_error = None
    for attempt in range(1, attempts + 1):
        metadata = dict(history_metadata or {})
        metadata.update({"purpose": "continuity_combined_reduced_state", "content_attempt": attempt})
        try:
            raw = llm_request(
                combined_messages,
                response_format=None,
                temperature=0.10,
                top_p=0.90,
                max_tokens=6000,
                **({"history_metadata": metadata} if metadata else {}),
            )
            reduced_state = _parse_continuity_json_result(raw, "Continuity")
            break
        except Exception as error:
            combined_error = error
            if attempt < attempts:
                print(f"[Continuity] returned unusable JSON; retrying: {error}")
    if reduced_state is None:
        raise RuntimeError(f"Continuity failed: {combined_error}")
    _print_continuity_phase_result(1, "COMBINED CONTINUITY", reduced_state)

    if defer_opening:
        return {
            "reduced_state": reduced_state,
            "opening_state": "",
        }

    opening_state = request_continuity_opening_state(
        reduced_state,
        current_phase,
        llm_request=llm_request,
        history_metadata=history_metadata,
    )
    return {
        "reduced_state": reduced_state,
        "opening_state": opening_state,
    }


def request_structured_continuity_state(
    recent_results,
    committed_state,
    subject_definitions,
    llm_request=None,
    history_metadata=None,
    active_beat_text="",
    future_beat_texts=None,
    content_attempts=SUMMARY_CONTENT_ATTEMPTS,
    new_subjects=None,
):
    """Extract a small LLM delta, apply it in Python, then validate the result."""
    if llm_request is None:
        llm_request = ask_llm
    base_messages = build_structured_continuity_messages(
        recent_results,
        committed_state,
        subject_definitions,
        active_beat_text=active_beat_text,
        future_beat_texts=future_beat_texts,
        new_subjects=new_subjects,
    )
    origin_segment = max(
        (
            int(segment_number)
            for segment_number, _ in recent_results
            if str(segment_number).isdigit()
        ),
        default=None,
    )
    newest_description = ""
    if recent_results:
        newest_result = list(recent_results)[-1][1]
        newest_description = str(get_detailed_description(newest_result, "") or "")

    validation_feedback = ""
    attempts = max(1, int(content_attempts))
    # Keep the newest state that Python successfully built from a legal delta.
    # The LLM validator may request corrections, but it is not the state owner
    # and must not erase otherwise useful state if every semantic retry fails.
    last_normalized = None
    for attempt in range(1, attempts + 1):
        messages = [dict(message) for message in base_messages]
        if validation_feedback:
            messages[-1]["content"] += (
                "\n\nSTATE VALIDATION FAILED\n"
                + validation_feedback
                + "\nReturn a corrected continuity DELTA only. Do not return "
                  "a complete state. If a reported missing fact is clearly "
                  "established by the newest prompt while COMMITTED STATE has "
                  "N/A/empty for that fact, add it to the delta even though it "
                  "did not change during the segment."
            )
        elif attempt > 1:
            messages[-1]["content"] += (
                "\n\nThe previous response was not a usable continuity DELTA. "
                "Return only a valid delta JSON object using registered Subjects "
                "and allowed update fields."
            )

        metadata = dict(history_metadata or {})
        if metadata:
            metadata["content_attempt"] = attempt

        raw_delta = llm_request(
            messages,
            response_format=None,
            temperature=0.10,
            top_p=0.90,
            **({"history_metadata": metadata} if metadata else {}),
        )
        if isinstance(raw_delta, str):
            try:
                raw_delta = parse_llm_json_content(raw_delta)
            except json.JSONDecodeError:
                raw_delta = None
        if isinstance(raw_delta, dict) and len(raw_delta) == 1:
            for wrapper_key in (
                "continuity_delta",
                "continuity_state",
                "state",
            ):
                if wrapper_key in raw_delta and isinstance(
                    raw_delta[wrapper_key],
                    dict,
                ):
                    raw_delta = raw_delta[wrapper_key]
                    break

        delta = sanitize_continuity_delta(
            raw_delta,
            subject_definitions,
            committed_state,
        )
        if delta is None:
            if attempt < attempts:
                print(
                    "[Continuity] updater response was unusable; requesting a "
                    "corrected delta."
                )
            continue

        # normalize_structured_continuity_state is now the deterministic delta
        # applier: it begins from COMMITTED STATE and copies persistent facts
        # forward before applying the sanitized changes.
        normalized = normalize_structured_continuity_state(
            delta,
            subject_definitions,
            committed_state,
            origin_segment=origin_segment,
            newest_description=newest_description,
            active_beat_text=active_beat_text,
            future_beat_texts=future_beat_texts,
            new_subjects=new_subjects,
        )
        if normalized is None:
            if attempt < attempts:
                print(
                    "[Continuity] Python rejected the delta; requesting a "
                    "corrected delta."
                )
            continue

        # At this point Python has accepted the delta and built a valid state.
        # Remember it before asking the LLM for a semantic opinion.
        last_normalized = normalized

        validation_messages = build_continuity_state_validation_messages(
            committed_state,
            normalized,
            subject_definitions,
            active_beat_text,
            newest_description,
        )
        validation_metadata = dict(history_metadata or {})
        if validation_metadata:
            validation_metadata["purpose"] = "continuity_state_validation"
            validation_metadata["content_attempt"] = attempt

        try:
            raw_validation = llm_request(
                validation_messages,
                response_format=None,
                temperature=0.05,
                top_p=0.90,
                **(
                    {"history_metadata": validation_metadata}
                    if validation_metadata else {}
                ),
            )
            validation = parse_continuity_state_validation(raw_validation)
        except Exception as error:
            # The validator is a semantic safety check, not the state owner.
            print(
                "WARNING: continuity-state LLM validation failed; using the "
                f"Python-built candidate state: {error}"
            )
            return normalized

        if validation["valid"]:
            print("[Continuity] LLM validation passed for Python-built state.")
            return normalized

        validation_feedback = "\n".join(
            f"- {issue}" for issue in validation["issues"]
        )
        print("[Continuity] LLM validation rejected candidate state:")
        for issue in validation["issues"]:
            print(f"  - {issue}")
        if attempt < attempts:
            print("[Continuity] requesting a corrected delta.")

    if last_normalized is not None:
        print(
            "WARNING: continuity-state validation did not fully pass after "
            "all correction attempts; using the latest Python-built candidate "
            "state instead of discarding it."
        )
        return last_normalized

    return None


def build_segment_request(
    segment,
    total_segments,
    segment_length,
    total_length,
    beats,
    conditioning_mode=None,
):
    conditioning_mode = validate_conditioning_mode(conditioning_mode, segment)
    elapsed = (segment - 1) * segment_length
    current_duration = min(segment_length, total_length - elapsed)

    if not beats:
        beat_text = "N/A"
        beat_id = None
    else:
        if len(beats) != total_segments:
            raise RuntimeError(
                f"One-beat-per-segment requires exactly {total_segments} beats, "
                f"but {len(beats)} are loaded."
            )
        beat_id = int(segment)
        beat_text = str(beats[beat_id - 1])

    if conditioning_mode == "initial":
        continuity = "Establish the opening composition; there is no prior clip."
    elif conditioning_mode == "latent_continuation":
        continuity = (
            "Continue directly from the supplied previous AV latent/final frame. "
            "OPENING STATE is already true; do not reconstruct or replay it."
        )
    else:
        continuity = (
            "Continue from the supplied previous final frame. OPENING STATE is "
            "already true; do not replay the action that created it."
        )

    dialogue_rule = ""
    if re.search(
        r"(?i)\b(?:talk\w*|conversation|discuss\w*|dialogue|asks?|says?|"
        r"shouts?|whispers?|yells?)\b",
        beat_text,
    ):
        dialogue_rule = (
            " If speech is required, write the exact audible words with the "
            "registered speaker ID using H3 dialogue syntax."
        )
    else:
        dialogue_rule = " Do not add dialogue unless ACTIVE BEAT requires it."

    completion = f" Return completed_beat_ids as [{beat_id}]." if beat_id else ""
    return (
        f"Create [Shot {segment}] as one {current_duration:g}-second MiniMax H3 "
        f"clip. {continuity} Start from OPENING STATE and visibly complete ACTIVE "
        "BEAT. Use CURRENT PHASE to resolve ambiguity. NEXT BEAT is boundary "
        "context only; do not perform it. Describe concrete visible action and its "
        f"result. The opening has no timestamp; use later local timestamps only "
        f"when they clarify sequence.{dialogue_rule}{completion}"
    )


def build_generation_messages(
    director_rules,
    story,
    beats,
    completed_beat_ids,
    recent_results,
    current_segment,
    total_segments,
    segment_length,
    total_length,
    continuity_summary=None,
    subject_definitions="",
    conditioning_mode=None,
    dialogue_exclusions=(),
    current_phase=None,
):
    """Build Request 1 of the two-stage Director micro-prompt pipeline."""
    del completed_beat_ids, recent_results, total_segments, total_length
    del conditioning_mode, dialogue_exclusions

    phase_text = (
        json.dumps(current_phase, ensure_ascii=False, indent=2)
        if isinstance(current_phase, dict) and current_phase
        else "N/A"
    )
    beats_for_phase = _phase_beats_text(
        beats,
        current_phase,
        current_segment,
    )
    continuity_text = (
        str(continuity_summary or "").strip()
        if int(current_segment) > 1
        else "N/A"
    ) or "N/A"

    subject_text = str(subject_definitions or "").strip() or "N/A"

    user_content = f"""STORY: {story} 

SUBJECT DEFINITIONS:
{subject_text}
 
PHASE: {phase_text}
 
BEATS: 
 
{beats_for_phase}
 
CONTINUITY STATE: 
{continuity_text}"""

    messages = [
        {"role": "system", "content": director_rules},
        {"role": "user", "content": user_content},
    ]
    estimated = estimate_message_tokens(messages)
    if estimated > LLM_INPUT_TOKEN_BUDGET:
        raise RuntimeError(
            f"Director Request 1 is too large ({estimated} estimated tokens; "
            f"budget {LLM_INPUT_TOKEN_BUDGET})."
        )
    return messages, estimated, 0


# ============================================================
# H3 PROMPT
# ============================================================

_CLOTHING_NOUN = re.compile(
    r"(?i)\b(?:shirt|t-?shirt|tee|blouse|jacket|coat|dress|skirt|jeans|"
    r"pants|trousers|shorts|suit|sweater|hoodie|uniform|robe|gown|vest|"
    r"windbreaker|cardigan|overalls|boots|shoes|sneakers|sandals|hat|"
    r"cap|scarf|gloves|tie|belt|socks|blazer|jersey|polo|tank\s+top|"
    r"sweatshirt|pullover|clothes|clothing|outfit)\b"
)
_CLOTHING_ACTION = re.compile(
    r"(?i)(?:,\s*|\s+)(?=<Subject\s+\d+>|(?:and\s+)?(?:he|she|they|who|while|as|then|"
    r"walks?|stands?|sits?|runs?|looks?|holds?|moves?|turns?|steps?|"
    r"crosses?|faces?|watches?|reaches?|leans?|gestures?)\b)"
)

SUBJECT_CONTINUITY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "subject_continuity",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "subjects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject_number": {"type": "integer", "minimum": 1},
                            "name": {"type": "string"},
                            "location": {"type": "string"},
                            "clothing": {"type": "string"},
                            "clothing_state": {"type": "string"},
                        },
                        "required": [
                            "subject_number",
                            "name",
                            "location",
                            "clothing",
                            "clothing_state",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["subjects"],
            "additionalProperties": False,
        },
    },
}


def parse_defined_subjects(subject_definitions):
    subjects = []
    for match in re.finditer(
        r"(?i:<Subject\s+(\d+)>\s*(?:is\s+)?)"
        r"([A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*)*)",
        subject_definitions or "",
        flags=re.IGNORECASE,
    ):
        subject_number = int(match.group(1))
        name = match.group(2).strip()
        if not any(number == subject_number for number, _ in subjects):
            subjects.append((subject_number, name))
    for match in re.finditer(
        r"(?im)^\s*(?:<\s*)?Picture\s+(\d+)\s*(?:>\s*)?"
        r"(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
        r"([A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*)*)"
        r"(?:\s+and\s+aligns\s+with\s+the\s+\d+(?:\.\d+)?-second\s+"
        r"mark\s+of\s+the\s+target\s+video)?\.\s*$",
        subject_definitions or "",
    ):
        subject_number = int(match.group(1))
        name = match.group(2).strip()
        if not any(number == subject_number for number, _ in subjects):
            subjects.append((subject_number, name))
    return subjects


def extract_subject_clothing(subject_name, descriptions):
    escaped_name = re.escape(subject_name)
    explicit_pattern = re.compile(
        rf"(?i)\b{escaped_name}\b(?:\s+\(S\d+\))?[^.!?;]*?"
        r"(?:(?:is|was|remains?)\s+)?(?:still\s+|currently\s+|now\s+)?"
        r"(?:wearing|wears|dressed\s+in|clad\s+in|has\s+on|sports)\s+"
        r"([^.!?;]+)"
    )
    in_pattern = re.compile(
        rf"(?i)\b{escaped_name}\b(?:\s+\(S\d+\))?\s*,?\s+"
        r"(?:(?:is|was|remains?)\s+)?(?:still\s+|currently\s+|now\s+)?in\s+"
        r"([^.!?;]+)"
    )
    possessive_pattern = re.compile(
        rf"(?i)\b{escaped_name}(?:'s|\u2019s)\s+([^.!?;]+)"
    )
    appositive_pattern = re.compile(
        rf"(?i)\b{escaped_name}\b(?:\s+\(S\d+\))?\s*,\s*"
        r"([^.!?;]+)"
    )

    for description in descriptions:
        text = str(description or "")
        match = explicit_pattern.search(text)
        if match is None:
            candidate = in_pattern.search(text)
            if candidate is not None and _CLOTHING_NOUN.search(candidate.group(1)):
                match = candidate
        if match is None:
            candidate = possessive_pattern.search(text)
            if candidate is not None and _CLOTHING_NOUN.search(candidate.group(1)):
                match = candidate
        if match is None:
            candidate = appositive_pattern.search(text)
            if candidate is not None and _CLOTHING_NOUN.search(candidate.group(1)):
                match = candidate
        if match is None:
            continue

        clothing = _CLOTHING_ACTION.split(match.group(1), maxsplit=1)[0]
        clothing = re.sub(r"\s+", " ", clothing).strip(" ,:")
        if clothing and _CLOTHING_NOUN.search(clothing):
            return clothing[:240].rstrip(" ,:")
    return None


def extract_subject_location(subject_name, descriptions):
    escaped_name = re.escape(subject_name)
    location_pattern = re.compile(
        rf"(?i)\b{escaped_name}\b(?:\s+\(S\d+\))?[^.!?;]*?"
        r"\b(?:at|near|beside|behind|in front of|inside|within|under|on|"
        r"outside|outdoors|indoors)\s+(?:the\s+)?([^.!?;]+)"
    )
    for description in descriptions:
        text = str(description or "")
        match = location_pattern.search(text)
        if match is None:
            continue
        location = re.split(
            r"(?i)\s+(?:wearing|in|while|as|and then|and)\s+",
            match.group(1),
            maxsplit=1,
        )[0]
        location = re.sub(r"\s+", " ", location).strip(" ,:")
        if location and location.lower() not in {
            "him",
            "her",
            "them",
            "there",
            "nearby",
        }:
            return location[:240].rstrip(" ,:")
    return None


_CLOTHING_STATE = re.compile(
    r"(?i)\b(?:unchanged|changed|clean|dirty|wet|soaked|damp|dry|torn|"
    r"ripped|stained|muddy|dusty|paint-stained|water-stained|damaged|"
    r"tattered|intact|disheveled|dishevelled)\b"
)


def extract_subject_clothing_state(subject_name, descriptions):
    escaped_name = re.escape(subject_name)
    sentence_pattern = re.compile(
        rf"(?i)\b{escaped_name}\b[^.!?]*"
    )
    clothing_pattern = re.compile(
        r"(?i)\b(?:wearing|wears|dressed\s+in|clad\s+in|has\s+on|sports|"
        r"clothing|outfit|coat|jacket|dress|shirt|pants|jeans|trousers)\b"
    )
    for description in descriptions:
        text = str(description or "")
        for sentence in sentence_pattern.findall(text):
            clothing_match = clothing_pattern.search(sentence)
            if clothing_match is None:
                continue
            state_match = _CLOTHING_STATE.search(sentence, clothing_match.end())
            if state_match is None:
                continue
            state = re.sub(
                r"\s+",
                " ",
                sentence[state_match.start():],
            ).strip(" ,:")
            if state:
                return state[:160].rstrip(" ,:")
    return None


def request_subject_continuity(subjects, descriptions, llm_request=None):
    if llm_request is None:
        llm_request = ask_llm
    subject_text = "\n".join(
        f"{number}: {name}" for number, name in subjects
    )
    source_text = "\n\n".join(
        str(description or "") for description in descriptions if description
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Extract only the latest explicitly established continuity facts "
                "for the listed defined subjects. Return empty strings for facts "
                "not explicitly established. Never infer, invent, or use a "
                "reference image. Return only the requested JSON schema."
            ),
        },
        {
            "role": "user",
            "content": (
                "DEFINED SUBJECTS\n"
                f"{subject_text}\n\n"
                "CHECKPOINTED PRIOR SEGMENT INFORMATION\n"
                f"{source_text}\n\n"
                "For each listed subject, extract location, current clothing, "
                "and explicit clothing state."
            ),
        },
    ]
    raw = llm_request(
        messages,
        response_format=SUBJECT_CONTINUITY_RESPONSE_FORMAT,
    )
    if not isinstance(raw, dict) or not isinstance(raw.get("subjects"), list):
        raise RuntimeError("Subject continuity extraction returned invalid data.")
    allowed = {number: name for number, name in subjects}
    extracted = {}
    for item in raw["subjects"]:
        if not isinstance(item, dict):
            continue
        try:
            number = int(item.get("subject_number"))
        except (TypeError, ValueError):
            continue
        if number not in allowed or item.get("name") != allowed[number]:
            continue
        extracted[number] = {
            "name": allowed[number],
            "location": str(item.get("location") or "").strip(),
            "clothing": str(item.get("clothing") or "").strip(),
            "clothing_state": str(item.get("clothing_state") or "").strip(),
        }
    return extracted


def build_hard_cut_subject_continuity(
    subject_definitions,
    current_result,
    prior_segment_records,
    continuity_summary="",
    llm_request=None,
):
    subjects = parse_defined_subjects(subject_definitions)
    registry = parse_subject_registry(subject_definitions)
    if not subjects:
        return ""

    current_description = get_detailed_description(current_result)
    visible_subject_ids = extract_current_visible_subject_ids(
        current_description
    )
    subjects = [
        (subject_number, subject_name)
        for subject_number, subject_name in subjects
        if subject_number in visible_subject_ids
    ]
    if not subjects:
        return ""

    descriptions = [continuity_summary or ""]
    descriptions.extend(
        get_detailed_description(record.get("llm_result", {}))
        for record in reversed(prior_segment_records or [])
        if isinstance(record, dict)
        and isinstance(record.get("llm_result"), dict)
    )
    descriptions.append(subject_definitions or "")

    facts_by_subject = {}
    missing_subjects = []
    for subject_number, subject_name in subjects:
        facts = {
            "name": subject_name,
            "location": extract_subject_location(subject_name, descriptions),
            "clothing": extract_subject_clothing(subject_name, descriptions),
            "clothing_state": extract_subject_clothing_state(
                subject_name,
                descriptions,
            ),
        }
        facts_by_subject[subject_number] = facts
        if not all(facts[field] for field in ("location", "clothing", "clothing_state")):
            missing_subjects.append((subject_number, subject_name))

    if missing_subjects and llm_request is not None:
        extracted = request_subject_continuity(
            subjects,
            descriptions,
            llm_request=llm_request,
        )
        for subject_number, facts in extracted.items():
            current = facts_by_subject[subject_number]
            for field in ("location", "clothing", "clothing_state"):
                if not current[field] and facts[field]:
                    current[field] = facts[field]

    clauses = []
    for subject_number, subject_name in subjects:
        facts = facts_by_subject[subject_number]
        location = facts["location"]
        clothing = facts["clothing"]
        clothing_state = facts["clothing_state"]
        fact_clauses = []
        if location:
            fact_clauses.append(f"is at {location}")
        if clothing:
            fact_clauses.append(f"wearing {clothing}")
        if clothing_state:
            fact_clauses.append(f"with clothing state: {clothing_state}")
        if all(facts[field] for field in ("location", "clothing", "clothing_state")):
            clauses.append(
                f"<Subject {subject_number}> {subject_name} "
                + ", ".join(fact_clauses)
                + "."
            )
        else:
            print(
                "WARNING: Exact hard-cut continuity could not be recovered for "
                f"<Subject {subject_number}> {subject_name}; omitting the "
                "continuity reminder rather than inventing details."
            )
    if not clauses:
        return ""
    return "Hard-cut subject continuity: " + " ".join(clauses)


def build_hard_cut_subject_continuity_from_state(
    subject_definitions,
    current_result,
    continuity_state,
):
    """Build hard-cut reminders only from the last committed structured state."""
    registry = parse_subject_registry(subject_definitions)
    current_description = get_detailed_description(current_result)
    visible_subject_ids = extract_current_visible_subject_ids(
        current_description
    )
    state = continuity_state_for_registry(subject_definitions, continuity_state)
    clauses = []
    for subject_id, subject in registry.items():
        if subject_id not in visible_subject_ids:
            continue
        record = state["subjects"].get(subject["name"], {})
        location = record.get("position", "N/A")
        wardrobe = record.get("wardrobe", {})
        garments = [
            wardrobe.get(field, "N/A")
            for field in ("upper", "lower", "footwear", "other")
            if wardrobe.get(field, "N/A") not in ("", "N/A")
        ]
        condition = record.get("physical_condition", "N/A")
        if location in ("", "N/A") or not garments:
            continue
        clause = (
            f"<Subject {subject_id}> {subject['name']} is at {location}, "
            f"wearing {', '.join(garments)}"
        )
        if condition not in ("", "N/A"):
            clause += f", with physical condition: {condition}"
        clauses.append(clause + ".")
    if not clauses:
        return ""
    return "Hard-cut subject continuity: " + " ".join(clauses)


def build_hard_cut_clothing_reiteration(
    subject_definitions,
    current_result,
    prior_segment_records,
    continuity_summary=""
):
    """Backward-compatible name for the hard-cut subject-state builder."""
    return build_hard_cut_subject_continuity(
        subject_definitions,
        current_result,
        prior_segment_records,
        continuity_summary,
    )

def strip_field_prefix(value, field_name):
    value = value.strip()
    prefix = f"{field_name}:"
    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix):].lstrip()
    return value


def deduplicate_adjacent_picture_tags(value):
    """Collapse repeated copies of the same adjacent H3 Picture tag."""
    return re.sub(
        r"(?i)(?P<tag><Picture\s+(?P<picture>\d+)>)"
        r"(?:\s+<Picture\s+(?P=picture)>)+",
        r"\g<tag>",
        str(value or ""),
    )


_H3_COLLECTION_PLACEHOLDER = (
    r"(?:(?:[\"']\s*)?(?:N\s*/?\s*A|null|none|unknown|unspecified)"
    r"(?:\s*[\"'])?|[\"']\s*[\"'])"
)
_H3_EMPTY_COLLECTION_RE = re.compile(
    rf"(?:\[\s*(?:{_H3_COLLECTION_PLACEHOLDER}\s*"
    rf"(?:,\s*{_H3_COLLECTION_PLACEHOLDER}\s*)*)?\]|\{{\s*\}})",
    flags=re.IGNORECASE,
)
_H3_PLACEHOLDER_VALUE_RE = re.compile(
    r"(?ix)^\s*(?:"
    r"N\s*/?\s*A|none|null|nil|unknown|unspecified|undetermined|"
    r"not\s+(?:applicable|available|provided|specified|known)|"
    r"no\s+(?:data|value|information)|TBD|TODO|empty|"
    r"\[\s*\]|\{\s*\}|[\"']\s*[\"']|[-\u2013\u2014]+"
    r")(?:\s*\([^\r\n]*\))?\s*[.,;:-]*\s*$"
)
_H3_INLINE_PLACEHOLDER_FIELD_RE = re.compile(
    r"(?ix)"
    r"(?P<lead>(?:^|[,;.])\s*)"
    r"(?P<label>[\"']?[a-z][a-z0-9_ ./-]{0,40}[\"']?\s*[:=]\s*)"
    r"(?:N\s*/?\s*A|none|null|nil|unknown|unspecified|undetermined|"
    r"not\s+(?:applicable|available|provided|specified|known)|"
    r"no\s+(?:data|value|information)|TBD|TODO|empty|"
    r"\[\s*\]|\{\s*\}|[\"']\s*[\"'])"
    r"(?:\s*\([^,;\r\n]*\))?\s*"
    r"(?P<trail>[,;.]*\s*)"
)

_H3_DOLLAR_AMOUNT_RE = re.compile(
    r"\$(?P<dollars>(?:\d{1,3}(?:,\d{3})+|\d+))"
    r"(?:\.(?P<cents>\d{1,2}))?(?!\d|\.\d)"
)


def _is_h3_placeholder_value(value):
    return _H3_PLACEHOLDER_VALUE_RE.fullmatch(str(value or "")) is not None


def _spell_out_h3_dollar_amount(match):
    """Render currency without the dollar-sign syntax reserved by Dynamic Prompts."""
    dollars_text = match.group("dollars")
    dollars = int(dollars_text.replace(",", ""))
    cents_text = match.group("cents")
    cents = int(cents_text.ljust(2, "0")) if cents_text is not None else 0

    parts = []
    if dollars or not cents:
        parts.append(
            f"{dollars_text} {'dollar' if dollars == 1 else 'dollars'}"
        )
    if cents:
        parts.append(f"{cents} {'cent' if cents == 1 else 'cents'}")
    return " and ".join(parts)


def _clean_h3_list_literal(match):
    """Remove placeholder members and collapse a now-empty flat list."""
    items = []
    for raw_item in match.group(1).split(","):
        item = raw_item.strip()
        unquoted = item
        if (
            len(item) >= 2
            and item[0] in {"\"", "'"}
            and item[-1] == item[0]
        ):
            unquoted = item[1:-1].strip()
        if not _is_h3_placeholder_value(unquoted):
            items.append(item)
    return "[" + ", ".join(items) + "]" if items else ""


def sanitize_h3_prompt_component(value):
    """Remove storage placeholders from one H3-only prompt component.

    This function never mutates continuity or generation state.  It operates on
    the strings assembled for H3 so checkpoint serialization retains its full
    schema and sentinel values.
    """
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    # DPRandomGenerator reserves ``$`` for variable access/assignment. Convert
    # ordinary currency while leaving valid future syntax such as ``${name}``
    # untouched.
    text = _H3_DOLLAR_AMOUNT_RE.sub(_spell_out_h3_dollar_amount, text)
    cleaned_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if _is_h3_placeholder_value(re.sub(r"^\s*[-*]\s*", "", stripped)):
            continue

        label_match = re.match(
            r"^(?P<indent>\s*(?:[-*]\s*)?)"
            r"(?P<label>[\"']?[^:]{1,80}[\"']?\s*:)"
            r"(?P<value>.*)$",
            line,
        )
        simple_label = (
            label_match
            and ". " not in label_match.group("label")
            and not label_match.group("label").lstrip().startswith("[")
        )
        if simple_label and _is_h3_placeholder_value(label_match.group("value")):
            continue

        before_inline_cleanup = line
        line = re.sub(r"\[([^\[\]]*)\]", _clean_h3_list_literal, line)
        line = _H3_INLINE_PLACEHOLDER_FIELD_RE.sub(
            lambda match: (
                ". "
                if "." in (match.group("lead") + match.group("trail"))
                else (
                    "; "
                    if ";" in (match.group("lead") + match.group("trail"))
                    else (
                        ", "
                        if "," in (match.group("lead") + match.group("trail"))
                        else ""
                    )
                )
            ),
            line,
        )
        line = re.sub(r"(?i)(?<!\w)N\s*/?\s*A(?!\w)", "", line)
        line = _H3_EMPTY_COLLECTION_RE.sub("", line)
        line = re.sub(
            r"\[\s*(?:(?:[\"']\s*[\"'])?\s*,?\s*)*\]",
            "",
            line,
        )
        if line != before_inline_cleanup:
            line = re.sub(
                r"(?ix)(?:^|(?<=[,;.]))\s*"
                r"[a-z][a-z0-9_ /.-]{0,40}:\s*(?=$|[,;.])",
                "",
                line,
            )
        line = re.sub(r"\.{2,}", ".", line)
        line = re.sub(r"\s+([,;:.])", r"\1", line)
        line = re.sub(r"([,;])\s*([,;])", r"\2", line)
        line = re.sub(r"\(\s*\)", "", line)
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        line = line.strip(" ,;")
        if not line or _is_h3_placeholder_value(line):
            continue
        cleaned_lines.append(line)

    # Remove empty colon-only headings, such as a summary block whose only
    # content was N/A, while retaining headings that still introduce real text.
    keep = [True] * len(cleaned_lines)
    for index, line in enumerate(cleaned_lines):
        stripped = line.strip()
        if not re.fullmatch(r"[^.!?\r\n]{1,80}:", stripped):
            continue
        next_text = next(
            (
                candidate.strip()
                for candidate in cleaned_lines[index + 1:]
                if candidate.strip()
            ),
            "",
        )
        if not next_text or re.fullmatch(r"[^.!?\r\n]{1,80}:", next_text):
            keep[index] = False
    cleaned_lines = [
        line for index, line in enumerate(cleaned_lines) if keep[index]
    ]
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n[ \t]+\n", "\n\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _append_h3_prompt_section(sections, label, value):
    cleaned = sanitize_h3_prompt_component(value)
    if cleaned:
        sections.append(f"{label}: {cleaned}")


def _replace_excluded_picture_tags_for_h3(
    value,
    conditioning_mode,
    excluded_picture_ids=None,
):
    """Redirect incompatible continuation Picture tags to video continuity."""
    text = str(value or "")
    excluded = {
        int(item)
        for item in (excluded_picture_ids or ())
        if isinstance(item, int) or str(item).isdigit()
    }
    if conditioning_mode not in {"clean_refresh", "latent_continuation"} or not excluded or not text:
        return text

    pattern = re.compile(
        r"(?i)<Picture\s+(%s)>" % "|".join(
            str(number) for number in sorted(excluded)
        )
    )
    return pattern.sub("<Video 1>", text)


def _remap_append_picture_tags_for_h3(value, picture_slot_map=None):
    """Remap canonical Picture tags to dense append batch slots in H3 text only."""

    text = str(value or "")
    packed_slots = {
        int(canonical_id): int(packed_slot)
        for canonical_id, packed_slot in (picture_slot_map or {}).items()
        if (isinstance(canonical_id, int) or str(canonical_id).isdigit())
        and (isinstance(packed_slot, int) or str(packed_slot).isdigit())
    }

    def replace(match):
        canonical_id = int(match.group("picture"))
        packed_slot = packed_slots.get(canonical_id)
        return (
            f"<Picture {packed_slot}>"
            if packed_slot is not None
            else match.group(0)
        )

    return re.sub(
        r"(?i)<Picture\s+(?P<picture>\d+)>",
        replace,
        text,
    )


def _condition_append_prompt_for_h3(
    h3_prompt,
    excluded_picture_ids,
    picture_slot_map,
):
    """Apply append-only Picture exclusion and packing at the H3 boundary."""

    conditioned = _replace_excluded_picture_tags_for_h3(
        h3_prompt,
        "latent_continuation",
        excluded_picture_ids,
    )
    return _remap_append_picture_tags_for_h3(
        conditioned,
        picture_slot_map,
    )


def _h3_subject_definitions_for_conditioning(
    subject_definitions,
    conditioning_mode,
    excluded_picture_ids=None,
):
    """Remove incompatible Picture conditioning from continuation subject text."""
    text = str(subject_definitions or "")
    excluded = {
        int(value)
        for value in (excluded_picture_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }
    if conditioning_mode not in {"clean_refresh", "latent_continuation"} or not excluded or not text.strip():
        return text

    try:
        registry = parse_subject_registry(text)
    except ValueError:
        registry = {}

    rendered = []
    replaced_subject_ids = set()
    for line in text.splitlines():
        subject_match = re.match(
            r"(?i)^\s*<Subject\s+(?P<subject>\d+)>\s+(?:is\s+)?"
            r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)",
            line,
        )
        legacy_match = re.match(
            r"(?i)^\s*(?:<\s*)?Picture\s+(?P<picture>\d+)\s*(?:>\s*)?"
            r"(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
            r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)",
            line,
        )

        subject_id = None
        name = None
        if subject_match is not None:
            subject_id = int(subject_match.group("subject"))
            name = subject_match.group("name").strip()
        elif legacy_match is not None:
            subject_id = int(legacy_match.group("picture"))
            name = legacy_match.group("name").strip()

        if subject_id is None:
            rendered.append(line)
            continue

        record = registry.get(subject_id, {})
        picture_ids = {
            int(value)
            for value in record.get("picture_ids", [])
            if isinstance(value, int) or str(value).isdigit()
        }
        if not picture_ids and legacy_match is not None:
            picture_ids = {subject_id}

        if picture_ids & excluded:
            if subject_id not in replaced_subject_ids:
                rendered.append(
                    f"<Subject {subject_id}> is {name}, continued from <Video 1>."
                )
                replaced_subject_ids.add(subject_id)
            continue
        rendered.append(line)

    return "\n".join(rendered)


def extract_previous_visible_subject_ids(recent_results, segment_number):
    """Return Subject IDs tagged in the immediately preceding Director result."""
    if not recent_results or segment_number is None:
        return set()
    previous_segment, previous_result = recent_results[-1]
    try:
        is_immediately_previous = int(previous_segment) == int(segment_number) - 1
    except (TypeError, ValueError):
        return set()
    if not is_immediately_previous or not isinstance(previous_result, dict):
        return set()
    description = previous_result.get("detailed_description")
    if not isinstance(description, str):
        return set()
    return {
        int(subject_id)
        for subject_id in re.findall(r"(?i)<Subject\s+(\d+)>", description)
    }


def extract_current_visible_subject_ids(detailed_description):
    """Return the Subject IDs explicitly tagged in the target Director prose."""
    return {
        int(subject_id)
        for subject_id in re.findall(
            r"(?i)<Subject\s+(\d+)>",
            str(detailed_description or ""),
        )
    }


def _filter_h3_subject_definitions(
    subject_definitions, visible_subject_ids, detailed_description=None
):
    """Keep identity/reference definitions only for target-visible Subjects.

    If a Subject's name appears in `detailed_description` but the explicit
    `<Subject N>` tag does not, treat that Subject as visible and insert
    `<Subject N>` before the name occurrences in the description. Return a
    tuple of (filtered_subject_definitions, possibly_modified_description).
    """
    visible = {
        int(value)
        for value in (visible_subject_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }

    text = str(subject_definitions or "")
    # Map subject id -> original definition line (preserve order)
    lines = [line for line in text.splitlines()]
    lines_by_id = {}
    for line in lines:
        subject_match = re.match(r"(?i)^\s*<Subject\s+(\d+)>", line)
        legacy_match = re.match(
            r"(?i)^\s*(?:<\s*)?Picture\s+(\d+)\s*(?:>\s*)?",
            line,
        )
        match = subject_match or legacy_match
        if match is not None:
            try:
                sid = int(match.group(1))
            except Exception:
                continue
            if sid not in lines_by_id:
                lines_by_id[sid] = line

    # Parse registry to discover names and canonical subject ids
    try:
        registry = parse_subject_registry(text)
    except Exception:
        registry = {}

    modified_description = detailed_description
    # If a subject's name appears in the description, but its <Subject N>
    # tag was not included in visible, add it.
    if isinstance(detailed_description, str) and registry:
        # Sort names by length desc to avoid partial overlaps
        name_items = sorted(
            ((sid, info.get("name") or "") for sid, info in registry.items()),
            key=lambda t: len(t[1] or ""),
            reverse=True,
        )
        for sid, name in name_items:
            if not name:
                continue
            if sid in visible:
                continue
            # Find word-boundary occurrences of the name
            pattern = r"\b" + re.escape(name) + r"\b"
            if not re.search(pattern, modified_description):
                continue
            # Mark subject as visible
            visible.add(sid)
            # Insert <Subject N> before every occurrence of the name that is
            # not already immediately preceded by a Subject tag.
            new_parts = []
            last_idx = 0
            for m in re.finditer(pattern, modified_description):
                start, end = m.start(), m.end()
                # Check preceding text slice for an existing tag ending at start
                pre_slice_start = max(0, start - 40)
                pre_slice = modified_description[pre_slice_start:start]
                if re.search(r"<Subject\s+\d+>\s*$", pre_slice):
                    # already tagged, skip
                    continue
                new_parts.append(modified_description[last_idx:start])
                new_parts.append(f"<Subject {sid}> ")
                new_parts.append(modified_description[start:end])
                last_idx = end
            if new_parts:
                new_parts.append(modified_description[last_idx:])
                modified_description = "".join(new_parts)

    # Now render lines: include only those subject definition lines with ids
    # in visible. Preserve original order. For visible ids without an original
    # line, synthesize a short definition.
    rendered = []
    for line in lines:
        subject_match = re.match(r"(?i)^\s*<Subject\s+(\d+)>", line)
        legacy_match = re.match(
            r"(?i)^\s*(?:<\s*)?Picture\s+(\d+)\s*(?:>\s*)?",
            line,
        )
        match = subject_match or legacy_match
        if match is not None and int(match.group(1)) in visible:
            rendered.append(line)

    # Add synthesized lines for visible subjects missing from original defs
    for sid in sorted(visible):
        if sid not in lines_by_id:
            info = registry.get(sid) or {}
            name = info.get("name") if isinstance(info, dict) else None
            if name:
                rendered.append(f"<Subject {sid}> is {name}.")

    filtered_text = "\n".join(rendered)
    return filtered_text, modified_description


def _remove_video_origin_from_h3_subject_line(line):
    """Remove the canonical video-only origin clause from one H3 definition."""
    cleaned = re.sub(
        r"(?i)(?:,\s*|\s+(?:and\s+)?)(?:(?:continued\s+from)|"
        r"(?:(?:created|established)\s+by))\s+<Video\s+1>\s*\.?,?",
        ".",
        str(line or ""),
    )
    return re.sub(r"\.{2,}", ".", cleaned).strip()


def _append_video_origin_to_h3_subject_definitions(
    subject_definitions,
    previous_visible_subject_ids=(),
):
    """Point only Subjects visible in the prior segment to Video 1."""
    text = str(subject_definitions or "")
    if not text.strip():
        return text

    previous_visible = {
        int(value)
        for value in (previous_visible_subject_ids or ())
        if isinstance(value, int) or str(value).isdigit()
    }

    try:
        registry = parse_subject_registry(text)
    except ValueError:
        registry = {}

    suffix_template = (
        "{name}'s pose, clothing condition, position, and physical state at the "
        "beginning of the target video come from <Video 1>."
    )
    rendered = []
    for line in text.splitlines():
        subject_match = re.match(r"(?i)^\s*<Subject\s+(\d+)>", line)
        legacy_match = re.match(
            r"(?i)^\s*(?:<\s*)?Picture\s+(\d+)\s*(?:>\s*)?",
            line,
        )
        match = subject_match or legacy_match
        subject = registry.get(int(match.group(1))) if match is not None else None
        if subject is None:
            rendered.append(line)
            continue

        subject_id = int(match.group(1))
        if subject_id not in previous_visible:
            rendered.append(_remove_video_origin_from_h3_subject_line(line))
            continue

        stripped_line = line.rstrip()
        # Disabled because this opening-state sentence was doing more harm than
        # good in append-workflow H3 prompts. Keep the implementation available
        # for easy restoration if later testing supports it.
        # suffix = suffix_template.format(name=subject["name"])
        # if suffix not in stripped_line:
        #     separator = " " if stripped_line.endswith((".", "!", "?")) else ". "
        #     stripped_line += separator + suffix
        rendered.append(stripped_line)
    return "\n".join(rendered)


def format_h3_current_appearance_continuity(
    state,
    subject_definitions="",
    visible_subject_ids=None,
):
    """Render compact current appearance facts for latent continuation.

    The preceding AV latent remains the primary continuity source. This block
    only reinforces visible appearance facts that are easy for a video model to
    drift while avoiding scene history, camera state, actions, or spatial prose.
    """
    if not isinstance(state, dict):
        return ""

    normalized = continuity_state_for_registry(
        subject_definitions,
        copy.deepcopy(state),
    )
    visible_ids = (
        None
        if visible_subject_ids is None
        else {
            int(value)
            for value in visible_subject_ids
            if isinstance(value, int) or str(value).isdigit()
        }
    )
    if visible_ids is not None:
        normalized = _h3_continuity_state_for_visible_subjects(
            normalized,
            visible_ids,
        )
    rendered_subjects = []

    for subject_id, name, record in _ordered_continuity_subjects(normalized):
        if visible_ids is not None and subject_id not in visible_ids:
            continue
        facts = []

        wardrobe = record.get("wardrobe")
        if isinstance(wardrobe, dict):
            for field in ("upper", "lower", "footwear", "other"):
                value = _known_continuity_value(wardrobe.get(field))
                if value:
                    facts.append(
                        f"{_WARDROBE_CONTINUITY_LABELS[field]}: {value}"
                    )

        for field, label in (
            ("topology", "structural configuration"),
            ("body_state", "persistent body state"),
        ):
            value = _known_continuity_value(record.get(field))
            if value:
                facts.append(f"{label}: {value}")

        for field, label in (
            ("attached_objects", "attached item"),
            ("held_props", "held item"),
        ):
            values = [
                cleaned
                for item in record.get(field, [])
                if (cleaned := _continuity_item_text(item, field))
            ]
            facts.extend(f"{label}: {value}" for value in values)

        facts = list(dict.fromkeys(facts))
        if not facts:
            continue

        lines = [f"<Subject {subject_id}> {name}:"]
        lines.extend(f"- {fact}" for fact in facts)
        rendered_subjects.append("\n".join(lines))

    if not rendered_subjects:
        return ""
    return "CURRENT APPEARANCE CONTINUITY:\n" + "\n".join(rendered_subjects)


def format_h3_structural_continuity_guard():
    """Return a compact generic guard against unintended persistent reconfiguration."""
    return (
        "STRUCTURAL CONTINUITY:\n"
        "Preserve each visible Subject's current configuration at frame 0. "
        "Do not add, remove, duplicate, restore, or reconfigure persistent visible "
        "features unless detailed_description explicitly requires that change during "
        "this segment. Do not infer a persistent configuration change merely from "
        "camera motion, occlusion, contact, or temporary deformation."
    )


def format_h3_spoken_dialogue_constraint(detailed_description):
    """Return the deterministic H3 speech constraint for one segment."""
    if _DIALOGUE_BLOCK_PATTERN.search(str(detailed_description or "")):
        return ""
    return (
        "SPOKEN DIALOGUE: None. No intelligible spoken words, vocalized "
        "language, or singing occur in this segment."
    )


_H3_CONTINUATION_SHOT_PREFIX = re.compile(
    r"^\s*\[\s*Shot\s+\d+\s*\]\s*",
    re.IGNORECASE,
)


def _open_h3_continuation_description(summary_text, description):
    """Open a continuation description as the canonical ``[Shot 1]`` form.



    The continuity summary begins the section itself, immediately after the
    explicit continuation handoff from the preceding video, per the pipeline
    contract: ``[Shot 1] Continuing directly from the final state of <Video 1>,
    {summary}``.
  The standalone opening-state section no longer precedes the description.
    """
    description = str(description or "").lstrip()
    if summary_text:
        summary_text = str(summary_text).strip()
        opener = (
            "[Shot 1] Continuing directly from the final state of <Video 1>, "
            f"{summary_text}"
        )
        if not re.search(r"[.!?]\s*$", opener):
            opener += "."
    else:
        opener = "[Shot 1] Continuing directly from the final state of <Video 1>."
    if not description:
        return opener
    return f"{opener} {description}"


def build_h3_prompt(
    llm_result,
    subject_definitions,
    hard_cut_clothing_reiteration="",
    previous_state="",
    segment_number=None,
    ff=False,
    conditioning_mode=None,
    excluded_picture_ids=None,
    continuity_state=None,
    previous_visible_subject_ids=None,
):
    description = get_detailed_description(llm_result, None)
    if not isinstance(description, str):
        raise RuntimeError(
            "LLM response is missing text field 'detailed_description'."
        )
    for field in ("overall_soundscape", "non_diegetic_music"):
        if not isinstance(llm_result.get(field), str):
            raise RuntimeError(f"LLM response is missing text field '{field}'.")

    integrated = deduplicate_adjacent_picture_tags(
        strip_field_prefix(
            description,
            "detailed_description",
        )
    )
    reference_alignment = str(
        llm_result.get("reference_alignment", "") or ""
    ).strip()
    soundscape = strip_field_prefix(
        llm_result["overall_soundscape"],
        "overall_soundscape"
    )
    music = strip_field_prefix(
        llm_result["non_diegetic_music"],
        "non_diegetic_music"
    )
    current_visible_subject_ids = extract_current_visible_subject_ids(integrated)

    integrated = _replace_excluded_picture_tags_for_h3(
        integrated,
        conditioning_mode,
        excluded_picture_ids,
    )
    soundscape = _replace_excluded_picture_tags_for_h3(
        soundscape,
        conditioning_mode,
        excluded_picture_ids,
    )
    music = _replace_excluded_picture_tags_for_h3(
        music,
        conditioning_mode,
        excluded_picture_ids,
    )

    if ff and segment_number == 1:
        integrated = re.sub(
            r"^\s*\[\s*Shot\s+1\s*\]\s*",
            "",
            integrated,
            count=1,
            flags=re.IGNORECASE,
        )
        integrated = (
            "[Shot 1] At 00:00.000, begin with the composition established by "
            "<Picture 1>. The opening frame should visually match <Picture 1> "
            "as closely as possible."
            + (f"\n{integrated}" if integrated else "")
        )

    if conditioning_mode == "latent_continuation":
        subject_text = _append_video_origin_to_h3_subject_definitions(
            str(subject_definitions or "").strip(),
            previous_visible_subject_ids,
        )
    else:
        subject_text = _h3_subject_definitions_for_conditioning(
            subject_definitions,
            conditioning_mode,
            excluded_picture_ids=excluded_picture_ids,
        ).strip()
        if conditioning_mode == "initial":
            subject_text = "\n".join(
                _remove_video_origin_from_h3_subject_line(line)
                for line in subject_text.splitlines()
            )
    # `_filter_h3_subject_definitions` may insert `<Subject N>` tags into the
    # detailed description and returns a tuple of (filtered_subject_definitions,
    # possibly_modified_description). Unpack and update `integrated` when
    # provided so later prompt sections use the modified prose.
    subject_text, maybe_modified_description = _filter_h3_subject_definitions(
        subject_text,
        current_visible_subject_ids,
        integrated,
    )
    if isinstance(maybe_modified_description, str) and maybe_modified_description:
        integrated = maybe_modified_description
    if ff and segment_number == 1:
        subject_text += (
            "\n\n<Picture 1> is the opening-frame reference for the target video.\n\n"
            "At 00:00.000, the target video should begin by reproducing <Picture 1> "
            "as closely as possible. Preserve the same camera position, framing, "
            "composition, subject pose, facial expression, clothing, lighting, "
            "environment, object positions, and spatial relationships shown in "
            "<Picture 1>."
        )
    sections = []
    _append_h3_prompt_section(sections, "subject_definitions", subject_text)
    if segment_number is not None and int(segment_number) > 1:
        sections.append(format_h3_structural_continuity_guard())
    if reference_alignment:
        cleaned_alignment = sanitize_h3_prompt_component(reference_alignment)
        if cleaned_alignment:
            sections.append(cleaned_alignment)
    if segment_number is not None and int(segment_number) > 1:
        # The continuity summary opens the description itself, replacing the
        # former standalone opening-state section: "[Shot 1] Continuing
        # directly from the final state of <Video 1>, {continuity summary}".
        summary_text = str(previous_state or "").strip() or ""
        if hard_cut_clothing_reiteration:
            summary_text = (
                (summary_text + "\n" + hard_cut_clothing_reiteration).
                strip()
            )
        if summary_text:
            summary_text = sanitize_h3_prompt_component(summary_text)
        integrated = _open_h3_continuation_description(
            summary_text,
            _H3_CONTINUATION_SHOT_PREFIX.sub("", integrated),
        )
    _append_h3_prompt_section(
        sections,
        "detailed_description",
        integrated,
    )
    _append_h3_prompt_section(sections, "overall_soundscape", soundscape)
    _append_h3_prompt_section(sections, "non_diegetic_music", music)
    spoken_dialogue_constraint = format_h3_spoken_dialogue_constraint(description)
    if spoken_dialogue_constraint:
        sections.append(spoken_dialogue_constraint)
    return "\n\n".join(sections)


# ============================================================
# COMFYUI
# ============================================================

def free_vram():
    try:
        requests.post(
            f"{COMFY_URL}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=60
        ).raise_for_status()
    except requests.RequestException as e:
        print(f"WARNING: ComfyUI could not release VRAM: {e}")


class ComfyUIExecutionError(RuntimeError):
    """A completed ComfyUI prompt failed during node execution."""


class ComfyUIRenderTimeout(RuntimeError):
    """A ComfyUI prompt remained pending past its render deadline."""


def _is_guid_connection_error(error):
    text = str(error).lower()
    if not any(token in text for token in ("guid", "client_id", "client id")):
        return False
    return any(token in text for token in (
        "connect",
        "connection",
        "unable",
        "failed",
        "refused",
    ))


def queue_workflow(
    workflow,
    max_retries=COMFY_QUEUE_RETRIES,
    retry_delay=COMFY_QUEUE_RETRY_DELAY
):
    last_error = None
    client_id = str(uuid.uuid4())
    guid_attempts = 0

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{COMFY_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=60
            )
            if 400 <= response.status_code < 500:
                raise RuntimeError(
                    f"ComfyUI rejected workflow with HTTP "
                    f"{response.status_code}:\n{response.text}"
                )
            response.raise_for_status()
            data = response.json()
            return data["prompt_id"]
        except RuntimeError:
            raise
        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError
        ) as e:
            last_error = e
            if _is_guid_connection_error(e):
                guid_attempts += 1
                if guid_attempts >= 3:
                    previous_client_id = client_id
                    client_id = str(uuid.uuid4())
                    print(
                        f"ComfyUI connection failed for GUID "
                        f"{previous_client_id}; re-submitting prompt "
                        f"with a new client ID {client_id}."
                    )
                    guid_attempts = 0
                else:
                    print(
                        f"ComfyUI queue failed for GUID {client_id} "
                        f"({guid_attempts}/3): {e}"
                    )
            else:
                print(
                    f"ComfyUI queue failed (attempt {attempt}/{max_retries}): {e}"
                )
            if attempt < max_retries:
                time.sleep(retry_delay)

    raise RuntimeError("ComfyUI queue failed repeatedly.") from last_error


def wait_for_completion(
    prompt_id,
    max_consecutive_errors=COMFY_HISTORY_MAX_ERRORS,
    retry_delay=COMFY_HISTORY_RETRY_DELAY,
    timeout=COMFY_RENDER_TIMEOUT,
    clock=time.monotonic,
):
    consecutive_errors = 0
    deadline = clock() + timeout if timeout is not None else None

    while True:
        if deadline is not None and clock() >= deadline:
            raise ComfyUIRenderTimeout(
                f"ComfyUI prompt {prompt_id} remained pending for "
                f"{timeout:g} seconds."
            )
        try:
            response = requests.get(
                f"{COMFY_URL}/history/{prompt_id}",
                timeout=60
            )
            response.raise_for_status()
            history = response.json()
            consecutive_errors = 0

            if prompt_id in history:
                result = history[prompt_id]
                status = result.get("status", {})
                if status.get("completed"):
                    if status.get("status_str") != "success":
                        details = []
                        for message in status.get("messages", []):
                            if not isinstance(message, list) or len(message) < 2:
                                continue
                            if message[0] != "execution_error":
                                continue
                            payload = message[1]
                            if not isinstance(payload, dict):
                                continue
                            details.append(
                                "node={node}, type={exception_type}, "
                                "message={exception_message}, traceback={traceback}"
                                .format(
                                    node=payload.get("node_id", "unknown"),
                                    exception_type=payload.get(
                                        "exception_type", "unknown"
                                    ),
                                    exception_message=payload.get(
                                        "exception_message", "unknown"
                                    ),
                                    traceback=payload.get("traceback", "unknown"),
                                )
                            )
                        detail_text = "\n".join(details) or json.dumps(
                            status, indent=2
                        )
                        raise ComfyUIExecutionError(
                            "ComfyUI execution failed:\n" + detail_text
                        )
                    return result

            sleep_time = 2
            if deadline is not None:
                sleep_time = min(sleep_time, max(0, deadline - clock()))
            time.sleep(sleep_time)
        except (ComfyUIExecutionError, ComfyUIRenderTimeout):
            raise
        except (
            requests.RequestException,
            TypeError,
            ValueError
        ) as e:
            consecutive_errors += 1
            print(
                f"ComfyUI history check failed "
                f"({consecutive_errors}/{max_consecutive_errors}): {e}"
            )
            if consecutive_errors >= max_consecutive_errors:
                raise RuntimeError(
                    "Lost communication with ComfyUI."
                ) from e
            time.sleep(retry_delay)


def get_video_path(result, workflow):
    save_node_id, _ = find_workflow_node(
        workflow,
        SAVE_VIDEO_NODE_NAME,
        "queued workflow",
        "SaveVideo"
    )
    try:
        video = result["outputs"][save_node_id]["images"][0]
        filename = video["filename"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            "Could not locate the Save Video output in ComfyUI history."
        ) from e

    subfolder = video.get("subfolder", "")
    path = os.path.abspath(os.path.join(COMFY_OUTPUT, subfolder, filename))
    if not os.path.exists(path):
        raise FileNotFoundError(f"Generated video not found: {path}")
    return path


def get_video_resolution(video_path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            video_path
        ],
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def extract_video_frame(
    video_path,
    frame_name,
    *,
    input_directory=None,
    final_frame=False,
    frame_index=None,
    temporary_prefix=".minimax_frame_",
    error_label="video frame",
):
    """Atomically extract one exact decoded frame into ComfyUI's input folder."""

    if bool(final_frame) == (frame_index is not None):
        raise ValueError("Choose exactly one of final_frame or frame_index.")
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(
            f"Cannot extract {error_label}: source video is missing: {video_path!r}"
        )
    if not isinstance(frame_name, str) or not frame_name.strip():
        raise ValueError("A destination frame filename is required.")
    if frame_index is not None:
        if (
            not isinstance(frame_index, int)
            or isinstance(frame_index, bool)
            or frame_index < 0
        ):
            raise ValueError("frame_index must be a non-negative integer.")

    input_directory = os.path.abspath(input_directory or COMFY_INPUT)
    os.makedirs(input_directory, exist_ok=True)
    frame_name = frame_name.strip()
    frame_path = os.path.join(input_directory, frame_name)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=temporary_prefix,
        suffix=".png",
        dir=input_directory,
    )
    os.close(descriptor)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-map",
        "0:v:0",
    ]
    if final_frame:
        command.extend(["-vf", "reverse"])
    else:
        command.extend(["-vf", f"select=eq(n\\,{frame_index})", "-vsync", "0"])
    command.extend([
        "-frames:v",
        "1",
        "-update",
        "1",
        "-an",
        temporary_path,
    ])
    try:
        subprocess.run(command, check=True)
        if not os.path.isfile(temporary_path) or os.path.getsize(temporary_path) == 0:
            raise RuntimeError(f"ffmpeg did not produce {error_label}.")
        os.replace(temporary_path, frame_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
    if not os.path.isfile(frame_path) or os.path.getsize(frame_path) == 0:
        raise RuntimeError(f"Extracted {error_label} is missing or empty: {frame_path}")
    return frame_name


def extract_refresh_first_frame(
    previous_video_path,
    segment_number,
    input_directory=None,
):
    """Extract the exact final video frame into ComfyUI's input directory."""

    if not previous_video_path or not os.path.isfile(previous_video_path):
        raise FileNotFoundError(
            f"Cannot refresh segment {segment_number}: previous video is missing: "
            f"{previous_video_path!r}"
        )
    frame_name = f"minimax_refresh_first_frame_{segment_number:04d}.png"
    return extract_video_frame(
        previous_video_path,
        frame_name,
        input_directory=input_directory,
        final_frame=True,
        temporary_prefix=f".refresh_{segment_number:04d}_",
        error_label=f"a refresh frame for segment {segment_number}",
    )


def extract_repair_anchor_frames(
    previous_video_path,
    next_video_path,
    segment_number,
    input_directory=None,
):
    """Extract the two visible-neighbor anchors for one repaired bridge."""

    first_frame_name = f"minimax_repair_first_frame_{segment_number:04d}.png"
    last_frame_name = f"minimax_repair_last_frame_{segment_number:04d}.png"
    first_frame_name = extract_video_frame(
        previous_video_path,
        first_frame_name,
        input_directory=input_directory,
        final_frame=True,
        temporary_prefix=f".repair_first_{segment_number:04d}_",
        error_label=f"the first repair anchor for segment {segment_number}",
    )
    last_frame_name = extract_video_frame(
        next_video_path,
        last_frame_name,
        input_directory=input_directory,
        frame_index=TRIM_FRAMES_AFTER_FIRST,
        temporary_prefix=f".repair_last_{segment_number:04d}_",
        error_label=f"the last repair anchor for segment {segment_number}",
    )
    return first_frame_name, last_frame_name



def get_video_frame_count(video_path):
    """Return the decoded video-frame count using ffprobe."""
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(
            f"Cannot count frames: source video is missing: {video_path!r}"
        )
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-count_frames",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames,nb_frames",
            "-of", "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"ffprobe found no video stream in {video_path!r}.")
    stream = streams[0]
    for field in ("nb_read_frames", "nb_frames"):
        value = str(stream.get(field) or "").strip()
        if value.isdigit() and int(value) > 0:
            return int(value)
    raise RuntimeError(f"ffprobe could not determine frame count for {video_path!r}.")


def extract_visual_end_frames(
    video_path,
    segment_number,
    offsets=VISION_END_FRAME_OFFSETS,
    output_directory=None,
):
    """Extract a tiny chronological window ending on the rendered final frame."""
    output_directory = os.path.abspath(output_directory or VISION_FRAME_OUTPUT)
    segment_directory = os.path.join(
        output_directory,
        f"segment_{int(segment_number):04d}",
    )
    os.makedirs(segment_directory, exist_ok=True)
    frame_count = get_video_frame_count(video_path)

    frame_indices = sorted({
        max(0, frame_count - 1 - int(offset))
        for offset in offsets
        if int(offset) >= 0
    })
    frame_paths = []
    for ordinal, frame_index in enumerate(frame_indices, start=1):
        frame_name = (
            f"end_{ordinal:02d}_frame_{frame_index:05d}.png"
        )
        extracted_name = extract_video_frame(
            video_path,
            frame_name,
            input_directory=segment_directory,
            frame_index=frame_index,
            temporary_prefix=f".vision_{int(segment_number):04d}_{ordinal:02d}_",
            error_label=(
                f"vision end frame {ordinal} for segment {segment_number}"
            ),
        )
        frame_paths.append(os.path.join(segment_directory, extracted_name))
    return frame_paths


def _vision_image_data_url(image_path):
    """Encode one local PNG/JPEG for an OpenAI-compatible multimodal request."""
    extension = os.path.splitext(str(image_path))[1].lower()
    if extension in {".jpg", ".jpeg"}:
        mime_type = "image/jpeg"
    elif extension == ".png":
        mime_type = "image/png"
    else:
        raise ValueError(f"Unsupported vision image type: {image_path!r}")
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


VISUAL_END_STATE_SYSTEM_PROMPT = (
    "You are a visual continuity extractor. Read only what is visibly present "
    "in the supplied ending-frame images from one video segment. Return only "
    "one JSON object. Do not include Markdown or explanations. Do not infer "
    "hidden details, prior actions, intended actions, or story facts. When a "
    "detail is unclear or outside the frame, use 'unknown' or 'not_visible'."
)


def build_visual_end_state_prompt(subject_definitions):
    """Build the deliberately small visual-observer request."""
    return f"""
The supplied images are chronological frames from the very end of one rendered
video segment. The LAST supplied image is the final frame.

Report only what is visibly true at the end.

Return exactly this JSON shape:
{{
  "environment": {{
    "location": "string",
    "persistent_state": "string"
  }},
  "camera": "string",
  "subjects": [
    {{
      "name": "string",
      "visible": true,
      "position": "string",
      "pose_action": "string",
      "wardrobe": {{
        "upper": "string",
        "lower": "string",
        "footwear": "string",
        "other": "string"
      }},
      "held_props": ["string"],
      "visible_injuries": ["string"]
    }}
  ],
  "uncertain_fields": ["string"]
}}

Rules:
- Use the canonical subject names below when the visible person can be identified.
- If a subject is not visible, omit them rather than reconstructing them from text.
- Describe only visible wardrobe. Use "not_visible" for occluded/out-of-frame areas.
- Do not infer clothing beneath other clothing.
- Do not infer footwear when feet are not visible.
- Describe visible physical state rather than inferred intent or activity. For
  example, prefer "eyes closed while lying still" over "sleeping".
- Do not infer what happened earlier in the clip.
- Do not infer what will happen next.

SUBJECT DEFINITIONS:
{str(subject_definitions or 'N/A').strip() or 'N/A'}
""".strip()


def _vision_message_text(content):
    """Extract assistant text from common LM Studio multimodal response shapes."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts)
    raise TypeError("Vision model returned non-text assistant content.")


def ask_vision_model(
    image_paths,
    subject_definitions,
    segment_number,
    max_retries=VISION_REQUEST_RETRIES,
):
    """Ask the currently loaded image-capable LM Studio model for visible state."""
    image_paths = [os.path.abspath(path) for path in image_paths]
    user_text = build_visual_end_state_prompt(subject_definitions)
    user_content = [{"type": "text", "text": user_text}]
    for image_path in image_paths:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": _vision_image_data_url(image_path)},
        })

    payload = {
        "messages": [
            {"role": "system", "content": VISUAL_END_STATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.10,
        "max_tokens": VISION_REQUEST_MAX_TOKENS,
    }
    if VISION_MODEL:
        payload["model"] = VISION_MODEL

    # Log paths and text, never the large base64 image payload.
    history_messages = [
        {"role": "system", "content": VISUAL_END_STATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                user_text
                + "\n\nVISION FRAME PATHS:\n"
                + "\n".join(image_paths)
            ),
        },
    ]

    last_error = None
    for attempt in range(1, max(1, int(max_retries)) + 1):
        append_prompt_history(
            history_messages,
            metadata={
                "purpose": "visual_end_state",
                "segment": int(segment_number),
                "content_attempt": attempt,
                "vision_model": VISION_MODEL or "LM Studio active model",
                "entry_type": "request",
            },
        )
        try:
            response = requests.post(
                f"{VISION_LM_STUDIO_URL}/v1/chat/completions",
                json=payload,
                timeout=600,
            )
            raise_for_lm_studio_status(response)
            data = response.json()
            choice = data["choices"][0]
            text = _vision_message_text(choice["message"]["content"])
            finish_reason = str(choice.get("finish_reason") or "").strip().lower()
            append_prompt_history(
                [{"role": "assistant", "content": text}],
                metadata={
                    "purpose": "visual_end_state",
                    "segment": int(segment_number),
                    "content_attempt": attempt,
                    "vision_model": VISION_MODEL or "LM Studio active model",
                    "finish_reason": finish_reason or None,
                    "entry_type": "response",
                },
            )
            if finish_reason in {"length", "max_tokens"}:
                raise ValueError(
                    "Vision response was truncated at "
                    f"max_tokens={VISION_REQUEST_MAX_TOKENS}."
                )
            result = parse_llm_json_content(text)
            if not isinstance(result, dict):
                raise ValueError("Vision model must return one JSON object.")
            return result
        except (
            requests.RequestException,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            last_error = error
            if attempt < max_retries:
                print(
                    f"[Vision] End-state request failed for segment "
                    f"{segment_number} ({attempt}/{max_retries}); retrying: {error}"
                )
                time.sleep(2)
    raise RuntimeError(
        f"Vision end-state request failed for segment {segment_number}: {last_error}"
    ) from last_error


def _visual_string(value, default="unknown"):
    text = " ".join(str(value or "").split()).strip()
    return text or default


def _visual_string_list(value):
    if not isinstance(value, list):
        return []
    return [
        cleaned
        for item in value
        if (cleaned := " ".join(str(item or "").split()).strip())
    ]


def normalize_visual_end_state(raw_state, subject_definitions):
    """Deterministically normalize only the small visual-observer schema."""
    if not isinstance(raw_state, dict):
        raise TypeError("Visual end state must be a JSON object.")

    registry = parse_subject_registry(subject_definitions)
    canonical_names = {
        record["name"].casefold(): record["name"]
        for record in registry.values()
    }
    environment = raw_state.get("environment")
    if not isinstance(environment, dict):
        environment = {}

    normalized = {
        "environment": {
            "location": _visual_string(environment.get("location")),
            "persistent_state": _visual_string(
                environment.get("persistent_state")
            ),
        },
        "camera": _visual_string(raw_state.get("camera")),
        "subjects": [],
        "uncertain_fields": _visual_string_list(
            raw_state.get("uncertain_fields")
        ),
    }

    for raw_subject in raw_state.get("subjects") or []:
        if not isinstance(raw_subject, dict):
            continue
        raw_name = _visual_string(raw_subject.get("name"), default="")
        if not raw_name:
            continue
        name = canonical_names.get(raw_name.casefold(), raw_name)
        visible = raw_subject.get("visible", True)
        if not isinstance(visible, bool):
            visible = str(visible).strip().casefold() not in {
                "false", "0", "no", "not_visible"
            }
        wardrobe = raw_subject.get("wardrobe")
        if not isinstance(wardrobe, dict):
            wardrobe = {}
        normalized["subjects"].append({
            "name": name,
            "visible": visible,
            "position": _visual_string(raw_subject.get("position")),
            "pose_action": _visual_string(raw_subject.get("pose_action")),
            "wardrobe": {
                field: _visual_string(wardrobe.get(field), default="not_visible")
                for field in ("upper", "lower", "footwear", "other")
            },
            "held_props": _visual_string_list(raw_subject.get("held_props")),
            "visible_injuries": _visual_string_list(
                raw_subject.get("visible_injuries")
            ),
        })
    return normalized


_VISUAL_UNKNOWN_VALUES = frozenset({
    "unknown",
    "not_visible",
    "not visible",
    "n/a",
    "na",
    "unclear",
})


def _visual_value_is_known(value):
    """Return whether the vision model made a positive visible observation."""
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.split()).strip().casefold()
    return bool(normalized) and normalized not in _VISUAL_UNKNOWN_VALUES


def _find_prompt_subject_record(subjects, visual_name):
    """Find a Phase-2 subject record in either common JSON representation."""
    name_key = str(visual_name or "").strip().casefold()
    if not name_key:
        return None
    if isinstance(subjects, dict):
        for key, record in subjects.items():
            if not isinstance(record, dict):
                continue
            record_name = str(record.get("name") or key).strip().casefold()
            if record_name == name_key or str(key).strip().casefold() == name_key:
                return record
        return None
    if isinstance(subjects, list):
        for record in subjects:
            if not isinstance(record, dict):
                continue
            if str(record.get("name") or "").strip().casefold() == name_key:
                return record
    return None


def _prompt_subject_collection(merged_state):
    """Return Phase 1's subject collection, accepting subjects/characters."""
    for key in ("subjects", "characters"):
        value = merged_state.get(key)
        if isinstance(value, (dict, list)):
            return key, value
    merged_state["subjects"] = {}
    return "subjects", merged_state["subjects"]


def _create_prompt_subject_record(merged_state, visual_name):
    """Create a minimal subject record only when Phase 1 omitted a visible one."""
    key, subjects = _prompt_subject_collection(merged_state)
    record = {"name": str(visual_name).strip()}
    if isinstance(subjects, list):
        subjects.append(record)
        return record
    subjects[str(visual_name).strip()] = record
    merged_state[key] = subjects
    return record


def merge_prompt_and_visual_end_state(prompt_state, visual_state):
    """Overlay directly observed rendered facts onto Phase 1 continuity.

    Prompt-derived state supplies facts the camera cannot establish. Visual
    observations take precedence only for positively observed fields. Unknown or
    not-visible vision values never erase prompt-derived continuity.
    """
    merged = copy.deepcopy(prompt_state) if isinstance(prompt_state, dict) else {}
    if not isinstance(visual_state, dict):
        return merged

    visual_environment = visual_state.get("environment")
    if isinstance(visual_environment, dict):
        visual_location = visual_environment.get("location")
        if _visual_value_is_known(visual_location):
            environment_key = "environment"
            environment = merged.get(environment_key)
            if not isinstance(environment, dict):
                alternate = merged.get("setting")
                if isinstance(alternate, dict):
                    environment_key = "setting"
                    environment = alternate
                else:
                    environment = {}
                    merged[environment_key] = environment
            environment["location"] = visual_location

    visual_camera = visual_state.get("camera")
    if _visual_value_is_known(visual_camera):
        camera_key = next(
            (key for key in ("camera", "camera_framing", "camera/framing") if key in merged),
            "camera",
        )
        merged[camera_key] = visual_camera

    _subject_key, subjects = _prompt_subject_collection(merged)
    for visual_subject in visual_state.get("subjects") or []:
        if not isinstance(visual_subject, dict) or not visual_subject.get("visible", True):
            continue
        visual_name = str(visual_subject.get("name") or "").strip()
        if not visual_name:
            continue
        prompt_subject = _find_prompt_subject_record(subjects, visual_name)
        if prompt_subject is None:
            prompt_subject = _create_prompt_subject_record(merged, visual_name)
            subjects = merged.get("subjects")

        for field, aliases in (
            ("position", ("position",)),
            ("pose_action", ("pose_action", "pose", "pose/action")),
        ):
            value = visual_subject.get(field)
            if _visual_value_is_known(value):
                target_field = next(
                    (alias for alias in aliases if alias in prompt_subject),
                    aliases[0],
                )
                prompt_subject[target_field] = value

        visual_wardrobe = visual_subject.get("wardrobe")
        if not isinstance(visual_wardrobe, dict):
            continue
        wardrobe_key = "wardrobe" if "wardrobe" in prompt_subject else (
            "clothing" if isinstance(prompt_subject.get("clothing"), dict) else "wardrobe"
        )
        prompt_wardrobe = prompt_subject.get(wardrobe_key)
        if not isinstance(prompt_wardrobe, dict):
            prompt_wardrobe = {}
            prompt_subject[wardrobe_key] = prompt_wardrobe
        for field in ("upper", "lower", "footwear", "other"):
            value = visual_wardrobe.get(field)
            if _visual_value_is_known(value):
                prompt_wardrobe[field] = value

    return merged


def _request_visual_end_state(video_path, subject_definitions, segment_number):
    """Extract final frames, ask the vision model, and return diagnostic state."""
    frame_paths = extract_visual_end_frames(video_path, segment_number)
    raw_state = ask_vision_model(
        frame_paths,
        subject_definitions,
        segment_number,
    )
    normalized_state = normalize_visual_end_state(
        raw_state,
        subject_definitions,
    )
    return {
        "frame_paths": frame_paths,
        "raw_end_state": raw_state,
        "end_state": normalized_state,
    }


def request_visual_end_state(video_path, subject_definitions, segment_number):
    """Run visual continuity analysis and remove its temporary frames."""
    try:
        return _request_visual_end_state(
            video_path,
            subject_definitions,
            segment_number,
        )
    finally:
        cleanup_generated_frames(vision_segment=segment_number)

def _assert_h3_prompt_contains_continuity(h3_prompt, continuity_summary, segment_number):
    """Reject any final H3 prompt that dropped the authoritative continuity summary."""
    if int(segment_number) <= 1:
        return
    summary_text = str(continuity_summary or "").strip()
    if not summary_text:
        return
    prompt_text = str(h3_prompt or "")
    norm_prompt = re.sub(r"\s+", " ", prompt_text)
    norm_summary = re.sub(r"\s+", " ", summary_text)
    if norm_summary not in norm_prompt:
        raise RuntimeError(
            f"Segment {segment_number} H3 prompt is missing the continuity summary "
            "before queueing the ComfyUI Prompt node."
        )


def _render_segment_with_retries(
    segment,
    current_duration,
    requested_megapixels,
    h3_prompt,
    previous_video_path,
    steps,
    loras=None,
    lora_override=None,
    context_frames=DEFAULT_CONTEXT_FRAMES,
    render_started_event=None,
    refresh_interval=None,
    refresh_input_directory=None,
    continuity_state=None,
    continuity_summary="",
):
    """Render one segment, retrying only recoverable ComfyUI failures."""
    if lora_override is not None:
        if loras:
            raise ValueError("Pass loras or lora_override, not both.")
        loras = [lora_override]
    loras = normalize_lora_list(loras)
    refresh_segment = is_refresh_segment(segment, refresh_interval)
    refresh_frame_name = None
    if refresh_segment:
        refresh_notice = (
            f"AUTO REFRESH: segment {segment} is using "
            f"'{os.path.basename(REFRESH_WORKFLOW_FILE)}'."
        )
        print(refresh_notice, flush=True)
        refresh_frame_name = extract_refresh_first_frame(
            previous_video_path,
            segment,
            input_directory=refresh_input_directory,
        )
        print(refresh_notice, flush=True)
        print(
            f"AUTO REFRESH: extracted the final frame of segment {segment - 1} "
            f"as {refresh_frame_name}.",
            flush=True,
        )
    for retry_number in range(COMFY_RENDER_RETRIES + 1):
        current_megapixels = (
            max(
                0.01,
                requested_megapixels
                - retry_number * COMFY_RETRY_MEGAPIXEL_STEP
            )
            if segment == 1 or refresh_segment
            else requested_megapixels
        )
        if retry_number:
            #free_vram()
            if segment == 1 or refresh_segment:
                print(
                    f"Retrying ComfyUI render ({retry_number}/"
                    f"{COMFY_RENDER_RETRIES}) at "
                    f"{current_megapixels:.2f} MP."
                )
            else:
                print(
                    f"Retrying ComfyUI render ({retry_number}/"
                    f"{COMFY_RENDER_RETRIES}) at inherited resolution."
                )

        lora_kwargs = {"loras": loras} if loras else {}
        if segment == 1:
            workflow = prepare_initial_workflow(
                current_duration,
                current_megapixels,
                h3_prompt,
                segment,
                steps,
                **lora_kwargs,
            )
        elif refresh_segment:
            workflow = prepare_refresh_workflow(
                current_duration,
                current_megapixels,
                h3_prompt,
                refresh_frame_name,
                segment,
                steps,
                **lora_kwargs,
                continuity_state=continuity_state,
            )
        else:
            workflow = prepare_append_workflow(
                current_duration,
                h3_prompt,
                previous_video_path,
                segment,
                steps,
                **lora_kwargs,
                context_frames=context_frames,
                continuity_state=continuity_state,
            )

        try:
            _assert_h3_prompt_contains_continuity(
                h3_prompt,
                continuity_summary,
                segment,
            )
            prompt_id = queue_workflow(workflow)
            print(f"ComfyUI prompt ID: {prompt_id}")
            if render_started_event is not None:
                render_started_event.set()
            comfy_result = wait_for_completion(prompt_id)
            video_path = get_video_path(comfy_result, workflow)
            width, height = get_video_resolution(video_path)
            return workflow, video_path, width, height, current_megapixels
        except (ComfyUIExecutionError, ComfyUIRenderTimeout) as error:
            print(
                f"ComfyUI render attempt failed "
                f"({retry_number + 1}/{COMFY_RENDER_RETRIES + 1}): {error}"
            )
            if retry_number == COMFY_RENDER_RETRIES:
                raise RuntimeError(
                    "ComfyUI render failed after "
                    f"{COMFY_RENDER_RETRIES} retries."
                ) from error

    raise AssertionError("ComfyUI render retry loop did not return or raise.")


def render_segment_with_retries(*args, **kwargs):
    """Render a segment and remove the temporary auto-refresh input frame."""
    segment = args[0] if args else kwargs.get("segment")
    refresh_interval = (
        args[10] if len(args) > 10 else kwargs.get("refresh_interval")
    )
    refresh_input_directory = (
        args[11] if len(args) > 11 else kwargs.get("refresh_input_directory")
    )
    refresh_frame_names = []
    if segment is not None and is_refresh_segment(segment, refresh_interval):
        refresh_frame_names.append(
            f"minimax_refresh_first_frame_{int(segment):04d}.png"
        )
    try:
        return _render_segment_with_retries(*args, **kwargs)
    finally:
        cleanup_generated_frames(
            refresh_frame_names=refresh_frame_names,
            input_directory=refresh_input_directory,
        )


def render_repair_segment_with_retries(
    segment_number,
    duration,
    requested_megapixels,
    h3_prompt,
    first_frame_name,
    last_frame_name,
    steps,
    loras=None,
    continuity_summary="",
):
    """Render an isolated two-keyframe bridge with normal ComfyUI retries."""

    loras = normalize_lora_list(loras)
    for retry_number in range(COMFY_RENDER_RETRIES + 1):
        current_megapixels = max(
            0.01,
            requested_megapixels
            - retry_number * COMFY_RETRY_MEGAPIXEL_STEP,
        )
        if retry_number:
            print(
                f"Retrying repair render ({retry_number}/{COMFY_RENDER_RETRIES}) "
                f"at {current_megapixels:.2f} MP."
            )
        workflow = prepare_repair_workflow(
            duration,
            current_megapixels,
            h3_prompt,
            first_frame_name,
            last_frame_name,
            segment_number,
            steps=steps,
            loras=loras,
        )
        try:
            _assert_h3_prompt_contains_continuity(
                h3_prompt,
                continuity_summary,
                segment_number,
            )
            prompt_id = queue_workflow(workflow)
            print(f"ComfyUI prompt ID: {prompt_id}")
            comfy_result = wait_for_completion(prompt_id)
            video_path = get_video_path(comfy_result, workflow)
            if (
                not os.path.isfile(video_path)
                or os.path.getsize(video_path) == 0
            ):
                raise ComfyUIExecutionError(
                    f"ComfyUI repair output is missing or empty: {video_path}"
                )
            width, height = get_video_resolution(video_path)
            return workflow, video_path, width, height, current_megapixels
        except (ComfyUIExecutionError, ComfyUIRenderTimeout) as error:
            print(
                f"ComfyUI repair attempt failed "
                f"({retry_number + 1}/{COMFY_RENDER_RETRIES + 1}): {error}"
            )
            if retry_number == COMFY_RENDER_RETRIES:
                raise RuntimeError(
                    "ComfyUI repair failed after "
                    f"{COMFY_RENDER_RETRIES} retries."
                ) from error

    raise AssertionError("ComfyUI repair retry loop did not return or raise.")


def prepare_initial_workflow(
    duration,
    megapixels,
    h3_prompt,
    segment_number,
    steps=6,
    loras=None,
    lora_override=None,
):
    if lora_override is not None:
        if loras:
            raise ValueError("Pass loras or lora_override, not both.")
        loras = [lora_override]
    workflow = load_workflow(INITIAL_WORKFLOW_FILE)
    label = f"initial workflow '{INITIAL_WORKFLOW_FILE}'"
    validate_workflow(workflow, label, is_append=False)
    prune_missing_reference_images(workflow, label, "initial")

    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "filename_prefix",
        H3_LATENT_FILENAME_PREFIX,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )

    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "clip_index",
        segment_number,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )

    set_node_input(
        workflow, DURATION_NODE_NAME, "value", duration,
        label, "PrimitiveFloat"
    )
    set_node_input(
        workflow, PROMPT_NODE_NAME, "text", h3_prompt,
        label, "DPRandomGenerator"
    )
    set_node_input(
        workflow, SCHEDULER_NODE_NAME, "steps", steps,
        label, "BasicScheduler"
    )
    set_node_input(
        workflow, NOISE_NODE_NAME, "noise_seed",
        generate_random_seed(),
        label, "RandomNoise"
    )
    set_node_input(
        workflow, RESOLUTION_NODE_NAME, "megapixels", megapixels,
        label, "ResolutionSelector"
    )
    set_node_input(
        workflow, SAVE_VIDEO_NODE_NAME, "filename_prefix",
        f"video/segment_{segment_number:04d}",
        label, "SaveVideo"
    )
    configure_lora_chain(workflow, loras, label)
    return workflow


def prepare_refresh_workflow(
    duration,
    megapixels,
    h3_prompt,
    refresh_frame_name,
    segment_number,
    steps=6,
    loras=None,
    lora_override=None,
    reference_workflow=None,
    continuity_state=None,
    excluded_picture_ids=None,
):
    """Prepare a fresh reference-to-video segment from the prior last frame."""

    if lora_override is not None:
        if loras:
            raise ValueError("Pass loras or lora_override, not both.")
        loras = [lora_override]
    workflow = load_workflow(REFRESH_WORKFLOW_FILE)
    label = f"refresh workflow '{REFRESH_WORKFLOW_FILE}'"
    validate_refresh_workflow(workflow, label)

    if not isinstance(refresh_frame_name, str) or not refresh_frame_name.strip():
        raise ValueError("A refresh frame filename is required.")
    if reference_workflow is None:
        reference_workflow = load_workflow(INITIAL_WORKFLOW_FILE)
    copy_reference_image_inputs(reference_workflow, workflow, label)
    incompatible_picture_ids = set(excluded_picture_ids or ())
    incompatible_picture_ids.update(
        get_refresh_incompatible_picture_ids(continuity_state)
    )
    prune_missing_reference_images(workflow, label, "refresh")
    disconnect_reference_images(
        workflow,
        label,
        "refresh",
        incompatible_picture_ids,
        reason="an active persistent structural change",
    )

    set_node_input(
        workflow,
        REFRESH_FIRST_FRAME_NODE_NAME,
        "image",
        refresh_frame_name.strip(),
        label,
        "LoadImage",
    )
    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "filename_prefix",
        H3_LATENT_FILENAME_PREFIX,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )
    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "clip_index",
        segment_number,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )
    set_node_input(
        workflow,
        DURATION_NODE_NAME,
        "value",
        duration,
        label,
        "PrimitiveFloat",
    )
    set_node_input(
        workflow,
        PROMPT_NODE_NAME,
        "text",
        h3_prompt,
        label,
        "DPRandomGenerator",
    )
    set_node_input(
        workflow,
        SCHEDULER_NODE_NAME,
        "steps",
        steps,
        label,
        "BasicScheduler",
    )
    set_node_input(
        workflow,
        NOISE_NODE_NAME,
        "noise_seed",
        generate_random_seed(),
        label,
        "RandomNoise",
    )
    set_node_input(
        workflow,
        RESOLUTION_NODE_NAME,
        "megapixels",
        megapixels,
        label,
        "ResolutionSelector",
    )
    set_node_input(
        workflow,
        SAVE_VIDEO_NODE_NAME,
        "filename_prefix",
        f"video/segment_{segment_number:04d}",
        label,
        "SaveVideo",
    )
    configure_lora_chain(workflow, loras, label)
    return workflow


def _next_workflow_node_id(workflow):
    numeric_ids = []
    for node_id in workflow:
        try:
            numeric_ids.append(int(node_id))
        except (TypeError, ValueError):
            continue
    next_node_id = max(numeric_ids, default=0) + 1
    while str(next_node_id) in workflow or next_node_id in workflow:
        next_node_id += 1
    return str(next_node_id)


def _repair_last_frame_node(workflow, conditioning, label):
    """Return an existing dedicated last-frame loader or add one dynamically."""

    connection = conditioning["inputs"].get("last_frame")
    if isinstance(connection, list) and len(connection) == 2:
        source = workflow.get(str(connection[0]), workflow.get(connection[0]))
        if (
            isinstance(source, dict)
            and source.get("class_type") == "LoadImage"
            and connection[1] == 0
        ):
            title = source.get("_meta", {}).get("title")
            if (
                isinstance(title, str)
                and title.strip()
                and title.strip() != REFRESH_FIRST_FRAME_NODE_NAME
                and title.strip() not in REFERENCE_IMAGE_NODE_NAMES
            ):
                return str(connection[0]), source, title.strip()

    candidates = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        title = node.get("_meta", {}).get("title")
        if (
            isinstance(title, str)
            and title.strip().lower().endswith("last frame")
            and title != REFRESH_FIRST_FRAME_NODE_NAME
        ):
            candidates.append((str(node_id), node, title.strip()))
    if len(candidates) > 1:
        raise RuntimeError(f"{label} contains multiple dedicated last-frame loaders.")
    if candidates:
        return candidates[0]

    node_id = _next_workflow_node_id(workflow)
    node = {
        "inputs": {"image": ""},
        "class_type": "LoadImage",
        "_meta": {"title": REPAIR_LAST_FRAME_NODE_NAME},
    }
    workflow[node_id] = node
    return node_id, node, REPAIR_LAST_FRAME_NODE_NAME


def validate_repair_workflow(
    workflow,
    workflow_label,
    last_frame_node_name,
    preserved_conditioning=None,
):
    """Validate both repair keyframes and isolated latent persistence."""

    find_workflow_node(
        workflow,
        REFRESH_FIRST_FRAME_NODE_NAME,
        workflow_label,
        "LoadImage",
    )
    find_workflow_node(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        workflow_label,
        "MiniMaxH3HybridRefAndKeyframe",
    )
    validate_named_connection(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        "first_frame",
        REFRESH_FIRST_FRAME_NODE_NAME,
        0,
        workflow_label,
    )
    _, conditioning = find_workflow_node(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        workflow_label,
        "MiniMaxH3HybridRefAndKeyframe",
    )
    for image_index, reference_node_name in enumerate(REFERENCE_IMAGE_NODE_NAMES):
        input_name = f"ref_images.ref_image_{image_index}"
        if input_name not in conditioning["inputs"]:
            continue
        validate_named_connection(
            workflow,
            REFRESH_CONDITIONING_NODE_NAME,
            input_name,
            reference_node_name,
            0,
            workflow_label,
        )
    for input_name, expected_value in (preserved_conditioning or {}).items():
        if conditioning["inputs"].get(input_name) != expected_value:
            raise RuntimeError(
                f"Repair workflow unexpectedly changed conditioning input "
                f"'{input_name}'."
            )
    find_workflow_node(
        workflow,
        last_frame_node_name,
        workflow_label,
        "LoadImage",
    )
    validate_named_connection(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        "last_frame",
        last_frame_node_name,
        0,
        workflow_label,
    )
    _, latent_save = find_workflow_node(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        workflow_label,
        "MiniMaxH3AVSaveLatentForExtend",
    )
    validate_named_connection(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "latent",
        "SamplerCustomAdvanced",
        0,
        workflow_label,
    )
    if latent_save["inputs"].get("filename_prefix") != H3_REPAIR_LATENT_FILENAME_PREFIX:
        raise RuntimeError(
            "Repair workflow must save its latent outside the normal h3_context chain."
        )


def prepare_repair_workflow(
    duration,
    megapixels,
    h3_prompt,
    first_frame_name,
    last_frame_name,
    segment_number,
    steps=6,
    loras=None,
    lora_override=None,
    reference_workflow=None,
):
    """Prepare the refresh graph as an isolated first/last-keyframe bridge."""

    if not isinstance(first_frame_name, str) or not first_frame_name.strip():
        raise ValueError("A repair first-frame filename is required.")
    if not isinstance(last_frame_name, str) or not last_frame_name.strip():
        raise ValueError("A repair last-frame filename is required.")
    workflow = prepare_refresh_workflow(
        duration,
        megapixels,
        h3_prompt,
        first_frame_name,
        segment_number,
        steps=steps,
        loras=loras,
        lora_override=lora_override,
        reference_workflow=reference_workflow,
    )
    label = f"repair workflow '{REFRESH_WORKFLOW_FILE}'"
    _, conditioning = find_workflow_node(
        workflow,
        REFRESH_CONDITIONING_NODE_NAME,
        label,
        "MiniMaxH3HybridRefAndKeyframe",
    )
    preserved_conditioning = {
        input_name: copy.deepcopy(conditioning["inputs"].get(input_name))
        for input_name in (
            "also_ref_first_frame",
            "ref_image_size",
            *(
                f"ref_images.ref_image_{image_index}"
                for image_index in range(len(REFERENCE_IMAGE_NODE_NAMES))
                if f"ref_images.ref_image_{image_index}" in conditioning["inputs"]
            ),
        )
    }
    last_node_id, last_node, last_node_name = _repair_last_frame_node(
        workflow,
        conditioning,
        label,
    )
    if "image" not in last_node.get("inputs", {}):
        raise RuntimeError(
            f"Last-frame LoadImage node '{last_node_name}' has no image input."
        )
    last_node["inputs"]["image"] = last_frame_name.strip()
    conditioning["inputs"]["last_frame"] = [last_node_id, 0]
    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "filename_prefix",
        H3_REPAIR_LATENT_FILENAME_PREFIX,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )
    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "clip_index",
        segment_number,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )
    set_node_input(
        workflow,
        SAVE_VIDEO_NODE_NAME,
        "filename_prefix",
        f"video/repair_segment_{segment_number:04d}",
        label,
        "SaveVideo",
    )
    validate_repair_workflow(
        workflow,
        label,
        last_node_name,
        preserved_conditioning=preserved_conditioning,
    )
    return workflow


def prepare_append_workflow(
    duration,
    h3_prompt,
    previous_video_path,
    segment_number,
    steps=6,
    loras=None,
    lora_override=None,
    context_frames=DEFAULT_CONTEXT_FRAMES,
    continuity_state=None,
    excluded_picture_ids=None,
):
    if lora_override is not None:
        if loras:
            raise ValueError("Pass loras or lora_override, not both.")
        loras = [lora_override]
    workflow = load_workflow(APPEND_WORKFLOW_FILE)
    label = f"append workflow '{APPEND_WORKFLOW_FILE}'"
    validate_workflow(workflow, label, is_append=True)
    incompatible_picture_ids = set(excluded_picture_ids or ())
    incompatible_picture_ids.update(
        get_refresh_incompatible_picture_ids(continuity_state)
    )
    removed_picture_ids, picture_slot_map = prune_missing_reference_images(
        workflow,
        label,
        "append",
        excluded_picture_ids=incompatible_picture_ids,
        return_picture_slot_map=True,
    )
    h3_prompt = _condition_append_prompt_for_h3(
        h3_prompt,
        removed_picture_ids,
        picture_slot_map,
    )

    if not os.path.exists(previous_video_path):
        raise FileNotFoundError(
            f"Previous video does not exist: {previous_video_path}"
        )

    set_node_input(
        workflow, DURATION_NODE_NAME, "value", duration,
        label, "PrimitiveFloat"
    )
    set_node_input(
        workflow, PROMPT_NODE_NAME, "text", h3_prompt,
        label, "DPRandomGenerator"
    )
    set_node_input(
        workflow, SCHEDULER_NODE_NAME, "steps", steps,
        label, "BasicScheduler"
    )
    set_node_input(
        workflow,
        H3_LATENT_LOAD_NODE_NAME,
        "filename_prefix",
        H3_LATENT_FILENAME_PREFIX,
        label,
        "MiniMaxH3AVLoadLatentForExtend",
    )

    set_node_input(
        workflow,
        H3_LATENT_LOAD_NODE_NAME,
        "clip_index",
        segment_number - 1,
        label,
        "MiniMaxH3AVLoadLatentForExtend",
    )

    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "filename_prefix",
        H3_LATENT_FILENAME_PREFIX,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )

    set_node_input(
        workflow,
        H3_LATENT_SAVE_NODE_NAME,
        "clip_index",
        segment_number,
        label,
        "MiniMaxH3AVSaveLatentForExtend",
    )
    set_node_input(
        workflow, SAVE_VIDEO_NODE_NAME, "filename_prefix",
        f"video/segment_{segment_number:04d}",
        label, "SaveVideo"
    )
    set_node_input(
        workflow, NOISE_NODE_NAME, "noise_seed",
        generate_random_seed(),
        label, "RandomNoise"
    )
    set_node_input(
        workflow, VIDEO_EXTEND_NODE_NAME, "context_frames",
        context_frames,
        label, "MiniMaxH3VideoExtendPatched"
    )
    set_node_input(
        workflow, VIDEO_EXTEND_NODE_NAME, "pin_last_frame",
        True,
        label, "MiniMaxH3VideoExtendPatched"
    )
    configure_lora_chain(workflow, loras, label)
    return workflow


# ============================================================
# STITCHING
# ============================================================

def trim_video_start(input_path, output_path, trim_seconds):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ss", f"{trim_seconds:.6f}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ],
        check=True,
    )


def stitch_videos(video_paths):
    if not video_paths:
        raise RuntimeError("No generated videos are available to stitch.")

    os.makedirs(VIDEO_OUTPUT, exist_ok=True)
    stitch_paths = []
    trimmed_paths = []
    for index, video_path in enumerate(video_paths):
        video_path = os.path.abspath(video_path)
        if index == 0:
            stitch_paths.append(video_path)
            continue

        trimmed_path = os.path.join(
            os.path.dirname(video_path),
            f"trimmed_{os.path.basename(video_path)}",
        )
        print(
            f"Trimming first {TRIM_FRAMES_AFTER_FIRST} frames from "
            f"segment {index + 1}."
        )
        trim_video_start(
            video_path,
            trimmed_path,
            TRIM_SECONDS_AFTER_FIRST,
        )
        stitch_paths.append(trimmed_path)
        trimmed_paths.append(trimmed_path)

    list_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix="minimax_stitch_",
            dir=VIDEO_OUTPUT,
            delete=False,
            encoding="utf-8"
        ) as f:
            list_path = f.name
            for path in stitch_paths:
                ffmpeg_path = path.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{ffmpeg_path}'\n")

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                FINAL_VIDEO
            ],
            check=True
        )
    finally:
        if list_path and os.path.exists(list_path):
            try:
                os.remove(list_path)
            except OSError:
                pass

    for trimmed_path in trimmed_paths:
        try:
            os.remove(trimmed_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            print(f"Warning: could not delete trimmed video {trimmed_path}: {error}")

    print(f"Stitching complete: {FINAL_VIDEO}")


def repair_existing_segment(
    segment_number,
    *,
    steps=6,
    global_loras=(),
    generation_state_path=GENERATION_STATE_FILE,
    subjects_path=SUBJECT_DEFINITIONS_FILE,
    beats_path=BEATS_FILE,
    story_path=STORY_FILE,
    input_directory=None,
):
    """Rerender one checkpointed middle segment without changing semantic state."""

    try:
        generation_state = load_generation_state(generation_state_path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Cannot repair because the generation checkpoint is missing: "
            f"{generation_state_path}"
        ) from None
    repair = validate_repair_checkpoint(generation_state, segment_number)
    duration, megapixels = get_repair_render_settings(
        repair["config"],
        segment_number,
    )

    # Preflight every current stitch artifact before spending time on a rerender.
    for expected_segment, record in enumerate(repair["records"], start=1):
        if (
            not isinstance(record, dict)
            or record.get("segment_number") != expected_segment
        ):
            raise RuntimeError(
                "Generation checkpoint segment records are missing or out of order."
            )
        #video_path = record.get("video_path")
        #if (
        #    not isinstance(video_path, str)
        #    or not os.path.isfile(video_path)
        #    or os.path.getsize(video_path) == 0
        #):
        #    raise RuntimeError(
        #        f"Cannot re-stitch after repair: video for segment "
        #        f"{expected_segment} is missing or empty: {video_path!r}"
        #    )

    base_subject_definitions = load_text_file(subjects_path, required=False)
    registry_state = repair["previous_record"].get(
        "subject_registry_state",
        new_continuity_state(),
    )
    historical_subject_definitions = subject_definitions_for_state(
        base_subject_definitions,
        registry_state,
    )
    opening_state = continuity_state_for_registry(
        historical_subject_definitions,
        copy.deepcopy(registry_state),
    )
    excluded_picture_ids = get_refresh_incompatible_picture_ids(opening_state)
    director_opening_summary = str(
        repair["previous_record"].get(
            "continuity_opening_state",
            repair["previous_record"].get("continuity_summary", ""),
        )
        or ""
    ).strip()
    if not director_opening_summary:
        director_opening_summary = format_director_opening_state(
            opening_state,
            historical_subject_definitions,
        )
    h3_opening_summary = director_opening_summary

    beats_raw = load_text_file(beats_path, required=True)
    beats = parse_beats_content(beats_raw)[0]
    if len(beats) < segment_number:
        raise RuntimeError(
            f"Cannot repair segment {segment_number}: {os.path.basename(beats_path)} "
            f"contains only {len(beats)} beat(s)."
        )
    story_source = load_text_file(story_path, required=True)
    story_without_gen_rules, gen_rules = parse_story_gen_rules(story_source)
    story, _beat_instructions = parse_story_beat_instructions(
        story_without_gen_rules
    )
    if not story:
        raise ValueError(
            "story.txt contains no story after beat_instructions/gen_rules metadata."
        )

    conditioning_mode = "clean_refresh"
    repair_macro_arc = load_story_arc(
        STORY_ARC_FILE,
        repair["total_segments"],
        story_without_gen_rules,
    )
    current_phase = story_arc_phase_for_beat(repair_macro_arc, segment_number)
    segment_length = float(repair["config"]["segment_length"])
    total_length = float(repair["config"]["total_length"])
    completed_before_target = set(range(1, segment_number))
    recent_results = [(
        segment_number - 1,
        repair["previous_record"]["llm_result"],
    )]
    dialogue_exclusions = collect_recent_dialogues(
        repair["records"][
            max(0, segment_number - 1 - DIALOGUE_HISTORY_SEGMENTS_MAX):
            segment_number - 1
        ]
    )
    director_rules = build_director_rules(
        total_length,
        duration,
        repair["total_segments"],
        historical_subject_definitions,
        segment_number,
        beats_enabled=True,
        conditioning_mode=conditioning_mode,
        gen_rules=gen_rules,
    )
    messages, _estimated_tokens, _recent_count = build_generation_messages(
        director_rules=director_rules,
        story=story,
        beats=beats,
        completed_beat_ids=completed_before_target,
        recent_results=recent_results,
        current_segment=segment_number,
        total_segments=repair["total_segments"],
        segment_length=segment_length,
        total_length=total_length,
        continuity_summary=director_opening_summary,
        subject_definitions=historical_subject_definitions,
        conditioning_mode=conditioning_mode,
        dialogue_exclusions=dialogue_exclusions,
        current_phase=current_phase,
    )
    director_bundle = {
        "segment": segment_number,
        "current_duration": duration,
        "active_beat_id": segment_number,
        "conditioning_mode": conditioning_mode,
        "messages": messages,
        "opening_state": director_opening_summary,
        "registry_state": opening_state,
        "dialogue_exclusions": dialogue_exclusions,
        "gen_rules": gen_rules,
        "opening_state_sha256": hashlib.sha256(
            json.dumps(
                opening_state,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    director_run_config = dict(repair["config"])
    director_run_config.setdefault(
        "source_sha256",
        hashlib.sha256(beats_raw.encode("utf-8")).hexdigest(),
    )
    print(
        f"Requesting a fresh Director prompt from Beat {segment_number} in "
        f"{os.path.basename(beats_path)}."
    )
    director_payload = request_segment_llm(
        director_bundle,
        beats,
        f"repair-{uuid.uuid4()}",
        director_run_config,
    )
    llm_result = copy.deepcopy(director_payload["llm_result"])
    llm_result["detailed_description"] = inject_persistent_state_into_description(
        get_detailed_description(llm_result, "")
    )
    hard_cut_subject_continuity = ""
    if is_hard_cut_segment(segment_number):
        hard_cut_subject_continuity = build_hard_cut_subject_continuity_from_state(
            historical_subject_definitions,
            llm_result,
            opening_state,
        )
    h3_prompt = build_h3_prompt(
        llm_result,
        historical_subject_definitions,
        hard_cut_subject_continuity,
        h3_opening_summary,
        segment_number,
        ff=False,
        conditioning_mode=conditioning_mode,
        excluded_picture_ids=excluded_picture_ids,
        continuity_state=opening_state,
    )

    loras = beat_loras(beats, segment_number, global_loras)

    print()
    print("=" * 64)
    print(f"REPAIR SEGMENT {segment_number}")
    print("=" * 64)
    print(
        f"Previous anchor: segment {segment_number - 1} final frame"
    )
    print(
        f"Next anchor: segment {segment_number + 1} stitched frame "
        f"{TRIM_FRAMES_AFTER_FIRST}"
    )
    first_frame_name, last_frame_name = extract_repair_anchor_frames(
        repair["previous_record"]["video_path"],
        repair["next_record"]["video_path"],
        segment_number,
        input_directory=input_directory,
    )
    (
        _workflow,
        repaired_video_path,
        width,
        height,
        rendered_megapixels,
    ) = render_repair_segment_with_retries(
        segment_number,
        duration,
        megapixels,
        h3_prompt,
        first_frame_name,
        last_frame_name,
        steps,
        loras=loras,
        continuity_summary=director_opening_summary,
    )
    repaired_video_path = os.path.abspath(repaired_video_path)
    if (
        not os.path.isfile(repaired_video_path)
        or os.path.getsize(repaired_video_path) == 0
    ):
        raise RuntimeError(
            f"Repair output is missing or empty: {repaired_video_path}"
        )
    print(
        f"Created: {repaired_video_path}\n"
        f"Resolution: {width} x {height} "
        f"({width * height / 1_000_000:.3f} MP; "
        f"target {rendered_megapixels:.2f} MP)"
    )

    # Repair preserves the checkpointed story/continuity semantics, but the
    # newly rendered clip may contain different spoken words. Commit that
    # dialogue-only state so later repairs/resumes exclude what is now audible.
    if repair["target_record_checkpointed"]:
        repair["target_record"]["dialogues"] = extract_spoken_dialogues(llm_result)
        generation_state["recent_dialogues"] = collect_recent_dialogues(
            repair["records"]
        )
        save_generation_state(generation_state, generation_state_path)

    print("Repaired video clip saved, you can run stitch.bat to combine them.")
    return {
        "video_path": repaired_video_path,
        "width": width,
        "height": height,
        "megapixels": rendered_megapixels,
    }


DIRECTOR_CONTINUITY_ISSUE_TYPES = (
    "absent_state_reintroduction",
    "persistent_transition_replay",
    "incompatible_state_restoration",
    "unsupported_persistent_change",
    "next_beat_scope_creep",
    "important_generation_rules_violation",
    "generation_rule_violation",
)

DIRECTOR_CONTINUITY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "director_continuity_validation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "valid": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": list(DIRECTOR_CONTINUITY_ISSUE_TYPES),
                            },
                            "problem": {"type": "string", "minLength": 1},
                        },
                        "required": ["type", "problem"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["valid", "issues"],
            "additionalProperties": False,
        },
    },
}


def _director_continuity_validation_state(opening_state):
    """Return the concise Phase 2 opening or legacy structured validation state."""
    if isinstance(opening_state, str):
        return opening_state.strip() or "N/A"
    state = migrate_continuity_state(copy.deepcopy(opening_state))
    payload = {
        "environment": {
            "location": state.get("environment", {}).get("location", "N/A"),
        },
        "subjects": {},
    }
    for name, record in state.get("subjects", {}).items():
        if not isinstance(record, dict):
            continue
        payload["subjects"][name] = {
            "subject_id": record.get("subject_id"),
            "persistent_structural_change": bool(
                record.get("persistent_structural_change", False)
            ),
            "wardrobe": copy.deepcopy(record.get("wardrobe", {})),
            "topology": record.get("topology", "N/A"),
            "body_state": record.get("body_state", "N/A"),
            "physical_condition": record.get("physical_condition", "N/A"),
            "attached_objects": copy.deepcopy(record.get("attached_objects", [])),
            "injuries": copy.deepcopy(record.get("injuries", [])),
            "substances": copy.deepcopy(record.get("substances", [])),
            "persistent_effects": copy.deepcopy(record.get("persistent_effects", [])),
            "held_props": copy.deepcopy(record.get("held_props", [])),
        }
    return payload


def build_director_continuity_validation_messages(
    opening_state,
    active_beat_text,
    detailed_description,
    segment_number,
    next_beat_text="",
    gen_rules="",
    overall_soundscape="",
    non_diegetic_music="",
):
    """Build the final continuity, scope, and custom-rule check for H3 content."""
    validation_state = _director_continuity_validation_state(opening_state)
    rendered_gen_rules = str(gen_rules or "").strip() or "N/A"
    return [
        {
            "role": "system",
            "content": (
                "You are a narrow final continuity gate for one generated video "
                "segment. Check concrete persistent-state contradictions, "
                "material scope creep into the supplied NEXT BEAT, and compliance "
                "with any IMPORTANT GENERATION RULES. "
                "Do not critique style, pacing, camera choices, temporary motion, "
                "or dramatic intensity unless an IMPORTANT GENERATION RULE explicitly "
                "governs it. Return only the requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Validate the candidate Director description for Segment {segment_number}.

IMPORTANT GENERATION RULES
{rendered_gen_rules}

AUTHORITY
- COMMITTED OPENING STATE is already true at frame 0.
- ACTIVE BEAT is the only story progression this segment is required to perform.
- NEXT BEAT, when supplied, is reserved for the next segment.
- CANDIDATE DESCRIPTION may change persistent state only when that change is a
  reasonable direct execution of ACTIVE BEAT.

FAIL only for a concrete violation of one of these rules:
1. An item/component explicitly absent in COMMITTED OPENING STATE is presented
   as currently intact/present again without ACTIVE BEAT explicitly restoring or
   replacing it. Clearly described fragments, residue, or debris are not the
   intact item and should not fail this rule.
2. The candidate replays an irreversible transition that COMMITTED OPENING STATE
   already records as completed.
3. The candidate restores a prior incompatible persistent configuration without
   ACTIVE BEAT explicitly establishing restoration/replacement.
4. The candidate invents a NEW major persistent configuration change that ACTIVE
   BEAT does not require. Contact, impact, danger, camera motion, occlusion, pose,
   or temporary deformation alone do not justify a new lasting configuration.
5. The candidate materially performs, begins, reveals, resolves, or establishes a
   distinctive story event or outcome reserved for NEXT BEAT. Shared characters,
   setting, props, connective motion, active-beat consequences, or reasonable
   preparation that does not itself enact the next event are not scope creep.
6. The candidate concretely violates an IMPORTANT GENERATION RULE. Judge all three
   candidate fields together. Do not invent requirements beyond the supplied rules,
   and do not fail a rule whose compliance cannot be determined from the text.

Use issue types narrowly:
- absent_state_reintroduction
- persistent_transition_replay
- incompatible_state_restoration
- unsupported_persistent_change
- next_beat_scope_creep
- important_generation_rules_violation
- generation_rule_violation
- generation_rule_violation

Do NOT fail because the candidate merely shows an already-existing persistent
condition. Do NOT demand exact wording. Do NOT infer a violation from ambiguity.
If no concrete contradiction or generation-rule violation exists, return valid=true.

COMMITTED OPENING STATE
{validation_state if isinstance(validation_state, str) else json.dumps(validation_state, ensure_ascii=False, indent=2)}

ACTIVE BEAT
{active_beat_text or 'N/A'}

NEXT BEAT
{next_beat_text or 'N/A (this is the final beat)'}

CANDIDATE H3 CONTENT
detailed_description: {detailed_description}
overall_soundscape: {overall_soundscape}
non_diegetic_music: {non_diegetic_music}

Return only JSON with exactly valid and issues.
""".strip(),
        },
    ]


def parse_director_continuity_validation(raw_result, formatter=None):
    """Parse the post-Director continuity gate response."""
    formatter = formatter or ACTIVE_FORMATTER
    candidate = raw_result
    if isinstance(candidate, str):
        candidate = formatter.sanitize_generated_text(candidate)
        try:
            candidate = parse_llm_json_content(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(
                "The Director continuity validation response must be valid JSON."
            ) from error
    if (
        isinstance(candidate, dict)
        and set(candidate) == {"validation"}
        and isinstance(candidate["validation"], dict)
    ):
        candidate = candidate["validation"]
    if not isinstance(candidate, dict) or set(candidate) != {"valid", "issues"}:
        raise ValueError(
            "The Director continuity validation response must contain only "
            "'valid' and 'issues'."
        )
    valid = candidate["valid"]
    issues = candidate["issues"]
    if not isinstance(valid, bool):
        raise ValueError("Director continuity validation 'valid' must be boolean.")
    if not isinstance(issues, list):
        raise ValueError("Director continuity validation 'issues' must be an array.")
    normalized = []
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {"type", "problem"}:
            raise ValueError(
                "Each Director continuity issue must contain exactly type and problem."
            )
        issue_type = issue["type"]
        problem = issue["problem"]
        if issue_type not in DIRECTOR_CONTINUITY_ISSUE_TYPES:
            raise ValueError(
                "Unknown Director continuity issue type: " + str(issue_type)
            )
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError("Director continuity issue problem must be non-empty.")
        normalized.append({
            "type": issue_type,
            "problem": " ".join(problem.split()),
        })
    if valid != (not normalized):
        raise ValueError(
            "Director continuity validation 'valid' must be true exactly when "
            "issues is empty."
        )
    if not valid:
        print("Director continuity validation failed with the following issues:", flush=True)
        for issue in normalized:
            print(f"{issue['problem']}\n", flush=True)
    else:
        print("Director continuity validation passed with no issues.", flush=True)
    return {"valid": valid, "issues": normalized}


def validate_director_continuity_candidate(
    opening_state,
    active_beat_text,
    detailed_description,
    segment_number,
    history_metadata=None,
    llm_request=None,
    next_beat_text="",
    gen_rules="",
    overall_soundscape="",
    non_diegetic_music="",
):
    """Reject continuity, scope, and custom generation-rule violations."""
    llm_request = llm_request or ask_llm
    messages = build_director_continuity_validation_messages(
        opening_state,
        active_beat_text,
        detailed_description,
        segment_number,
        next_beat_text=next_beat_text,
        gen_rules=gen_rules,
        overall_soundscape=overall_soundscape,
        non_diegetic_music=non_diegetic_music,
    )
    request_kwargs = {
        "response_format": DIRECTOR_CONTINUITY_RESPONSE_FORMAT,
        "temperature": 0.05,
    }
    if history_metadata:
        request_kwargs["history_metadata"] = history_metadata
    raw_result = llm_request(messages, **request_kwargs)
    return parse_director_continuity_validation(raw_result)


def format_director_continuity_correction(validation, gen_rules=""):
    """Turn final-gate issues into concise Director regeneration feedback."""
    bullets = "\n".join(
        f"- {issue['type']}: {issue['problem']}"
        for issue in validation.get("issues", [])
    )
    return (
        "DIRECTOR CONTINUITY CORRECTION\n\n"
        "The previous candidate contradicted the committed opening state, "
        "introduced an unsupported persistent change or next-beat scope creep, "
        "or violated an IMPORTANT generation rule:\n"
        f"{bullets}\n\n"
        "Regenerate the segment from the same frame-0 state. Execute only the "
        "ACTIVE beat and leave the NEXT beat unperformed. Preserve explicit "
        "absences and completed persistent transitions unless the ACTIVE beat "
        "itself requires a new change."
        + (
            f"\n\nIMPORTANT: {str(gen_rules).strip()}"
            if str(gen_rules or "").strip()
            else ""
        )
    )


def format_director_dialogue_correction(issues):
    """Return strict regeneration feedback for malformed H3 dialogue."""
    bullets = "\n".join(f"- {issue}" for issue in issues)
    return (
        "DIRECTOR DIALOGUE FORMAT CORRECTION\n\n"
        "The previous candidate violates the required H3 dialogue syntax:\n"
        f"{bullets}\n\n"
        "Regenerate the complete segment. Every exact spoken utterance must use "
        "`Character Name (SN) says: <d>[English] exact words</d>` (or an "
        "equivalent speech verb). Never place spoken words in quotation marks, "
        "never leave spoken words outside <d>...</d>, and never put <Subject N> "
        "inside spoken text or use it instead of (SN)."
    )


def _director_messages_with_correction(messages, correction):
    """Append regeneration feedback without changing LM Studio role alternation."""
    revised = copy.deepcopy(messages)
    if correction and revised:
        revised[-1]["content"] = (
            str(revised[-1].get("content", ""))
            + "\n\n"
            + str(correction).strip()
        )
    return revised


def request_segment_llm(bundle, beats, run_id, run_config):
    """Run the two-stage Director micro-prompt pipeline for one segment.

    Request 1 expands the assigned beat into raw_scene. Request 2 performs only
    MiniMax H3 audiovisual formatting. Python owns beat completion metadata and
    does not send the result through the legacy Director semantic gates.
    """
    del beats
    try:
        segment_number = int(bundle.get("segment", 1))
    except (TypeError, ValueError):
        segment_number = 1
    active_beat_id = bundle.get("active_beat_id")
    duration = float(bundle.get("current_duration") or 0)
    if duration <= 0:
        raise RuntimeError(
            f"Segment {segment_number} has no positive Director duration."
        )
    conditioning_mode = bundle.get("conditioning_mode")
    mode = "I2VA" if conditioning_mode == "clean_refresh" else "T2VA"

    request1_metadata = {
        "run_id": run_id,
        "source_sha256": (run_config or {}).get("source_sha256"),
        "purpose": "director_raw_scene",
        "segment": segment_number,
        "attempt": 1,
        "conditioning_mode": conditioning_mode,
        "opening_state_sha256": bundle.get("opening_state_sha256"),
    }
    raw_scene_result = ask_llm(
        bundle.get("messages", []),
        response_format=None,
        history_metadata=request1_metadata,
        temperature=0.35,
        top_p=0.90,
    )
    raw_scene = _normalize_raw_scene_result(raw_scene_result)

    print()
    print("=" * 64)
    print(f"DIRECTOR REQUEST 1: RAW SCENE - SEGMENT {segment_number}")
    print("=" * 64)
    print(raw_scene)
    print("=" * 64)

    formatter_messages = build_h3_formatter_messages(
        raw_scene,
        mode,
        duration,
        continuity_summary=bundle.get("opening_state")
        or bundle.get("h3_opening_summary")
        or "",
    )
    request2_metadata = {
        "run_id": run_id,
        "source_sha256": (run_config or {}).get("source_sha256"),
        "purpose": "director_h3_formatter",
        "segment": segment_number,
        "attempt": 1,
        "conditioning_mode": conditioning_mode,
        "h3_mode": mode,
        "opening_state_sha256": bundle.get("opening_state_sha256"),
    }
    max_formatter_attempts = 10
    llm_result = None
    for formatter_attempt in range(1, max_formatter_attempts + 1):
        request2_metadata["attempt"] = formatter_attempt
        formatted_result = ask_llm(
            formatter_messages,
            response_format=None,
            history_metadata=request2_metadata,
            temperature=0.10,
            top_p=0.90,
        )
        try:
            llm_result = parse_h3_formatter_result(
                formatted_result,
                completed_beat_id=active_beat_id,
            )
            break
        except RuntimeError as error:
            if formatter_attempt >= max_formatter_attempts:
                print(
                    f"Director Request 2 failed after {max_formatter_attempts} "
                    f"attempts; using the last LLM output as the final result: "
                    f"{error}",
                    flush=True,
                )
                llm_result = _salvage_h3_formatter_result(
                    formatted_result,
                    completed_beat_id=active_beat_id,
                    fallback_text=raw_scene,
                )
            else:
                print(
                    f"Director Request 2 failed (attempt "
                    f"{formatter_attempt}/{max_formatter_attempts}); "
                    f"re-prompting the LLM: {error}",
                    flush=True,
                )
    if llm_result is None:
        raise RuntimeError("Director Request 2 failed unexpectedly.")

    print()
    print("=" * 64)
    print(f"DIRECTOR REQUEST 2: H3 FORMATTER ({mode}) - SEGMENT {segment_number}")
    print("=" * 64)
    if llm_result.get("reference_alignment"):
        print(llm_result["reference_alignment"])
    print("detailed_description:")
    print(llm_result["detailed_description"])
    print("overall_soundscape:")
    print(llm_result["overall_soundscape"])
    print("non_diegetic_music:")
    print(llm_result["non_diegetic_music"])
    print("=" * 64)

    payload = dict(bundle)
    payload["raw_scene"] = raw_scene
    payload["h3_mode"] = mode
    payload["llm_result"] = llm_result
    return payload


# ============================================================
# MAIN
# ============================================================

def _run_main(
    summary_executor,
    director_prefetch_executor=None,
    render_executor=None,
):
    args = parse_args()
    configure_reference_image_overrides(args)
    generate_beats_count = getattr(args, "generate_beats", None)
    generate_beats_only = generate_beats_count is not None
    if generate_beats_only:
        print(
            "Generating the story arc and beats based on story.txt",
            flush=True,
        )
    configure_formatter(getattr(args, "model", "ministral"))
    global_loras = normalize_lora_list(getattr(args, "lora", ()))
    repair_segment = getattr(args, "repair", None)
    if repair_segment is not None:
        validate_runtime_environment()
        verify_global_loras(global_loras)
        return repair_existing_segment(
            repair_segment,
            steps=args.steps,
            global_loras=global_loras,
        )
    run_id = str(uuid.uuid4())

    segment_length = getattr(args, "segment_length", None)
    total_length = getattr(args, "total_length", None)
    megapixels = getattr(args, "megapixels", None)
    refresh_interval = getattr(args, "refresh", None)
    total_segments = (
        int(generate_beats_count)
        if generate_beats_only
        else math.ceil(total_length / segment_length)
    )
    resume_segment = args.resume

    story_source = load_text_file(
        STORY_FILE,
        required=not generate_beats_only,
    )
    story_without_gen_rules, gen_rules = parse_story_gen_rules(story_source)
    story, beat_instructions = parse_story_beat_instructions(
        story_without_gen_rules
    )
    if not story:
        raise ValueError("story.txt must have a story defined.")
    base_subject_definitions = load_text_file(
        SUBJECT_DEFINITIONS_FILE,
        required=False,
    )
    subject_definitions = base_subject_definitions
    subject_information = format_beat_generation_subjects(subject_definitions)
    phrase_exclusions_found = os.path.isfile(PHRASE_EXCLUSIONS_FILE)
    phrase_exclusions = (
        load_phrase_exclusions(PHRASE_EXCLUSIONS_FILE)
        if phrase_exclusions_found
        else []
    )
    if resume_segment == 1:
        reset_prompt_history()
    beats = load_or_generate_beats(
        BEATS_FILE,
        story,
        total_segments,
        history_metadata={"run_id": run_id},
        beat_instructions=beat_instructions,
        subject_information=subject_information,
        story_arc_path=STORY_ARC_FILE,
        story_arc_source=story_without_gen_rules,
        phrase_exclusions=phrase_exclusions,
        force_generate=generate_beats_only,
        gen_rules=gen_rules,
    )
    if beats and len(beats) != total_segments:
        raise ValueError(
            f"One-beat-per-segment requires exactly {total_segments} beats for "
            f"{total_segments} segments, but beats.txt contains {len(beats)} beats."
        )
    if generate_beats_only:
        print("Story arc and beats generated successfully.", flush=True)
        return

    segments_to_generate = get_segments_to_generate(
        resume_segment,
        total_segments,
    )
    macro_arc = load_story_arc(
        STORY_ARC_FILE,
        total_segments,
        story_without_gen_rules,
    )

    # Beat generation deliberately happens before external runtime and workflow
    # validation so an empty beats.txt is populated before normal startup work.
    validate_runtime_environment()

    run_config = build_run_config(
        segment_length,
        total_length,
        megapixels,
        total_segments,
        story,
        beats,
        subject_definitions,
        global_loras,
        refresh_interval,
        gen_rules=gen_rules,
        vision_continuity=args.vision_continuity,
    )
    if resume_segment == 1:
        generation_state = new_generation_state(run_config)
        additional_subject_definitions = []
        completed_beat_ids = set()
        recent_results = []
        generated_video_paths = []
        previous_video_path = None
        latent_path = None
        continuity_summary = ""
        prompt_reduced_continuity_state = {}
        reduced_continuity_state = {}
        # Keep the old structured object only as an internal Subject registry.
        # Creative continuity now comes from the combined continuity LLM call.
        continuity_state = continuity_state_for_registry(
            subject_definitions,
            new_continuity_state(),
        )
        generation_state["subject_registry_state"] = migrate_continuity_state(
            continuity_state
        )
        generation_state["continuity_state"] = {}
        generation_state["continuity_opening_state"] = ""
        continuity_summary_pending = False
    else:
        restored = restore_generation_state(
            resume_segment,
            beats,
            base_subject_definitions=base_subject_definitions,
        )
        generation_state = restored["state"]
        additional_subject_definitions = restored[
            "additional_subject_definitions"
        ]
        subject_definitions = combine_subject_definitions(
            base_subject_definitions,
            additional_subject_definitions,
        )
        completed_beat_ids = restored["completed_beat_ids"]
        recent_results = restored["recent_results"]
        latent_path = restored["latent_path"]
        generated_video_paths = restored["video_paths"]
        previous_video_path = restored["previous_video_path"]
        continuity_summary = restored.get(
            "continuity_opening_state", restored["continuity_summary"]
        )
        reduced_continuity_state = copy.deepcopy(
            restored.get("continuity_state", {})
        )
        prompt_reduced_continuity_state = copy.deepcopy(
            restored.get("continuity_prompt_state", reduced_continuity_state)
        )
        continuity_state = continuity_state_for_registry(
            subject_definitions,
            restored["subject_registry_state"],
        )
        continuity_summary_pending = restored["continuity_summary_pending"]
        generation_state.pop("additional_subject_definitions", None)

    # A prefetched prompt belongs to a live executor/Future. It cannot be
    # trusted after process restart unless that Future is restored as well.
    generation_state.pop("prefetched_next_prompt", None)
    generation_state_lock = threading.RLock()

    def checkpoint_generation_state():
        """Serialize the shared checkpoint without racing a prefetch worker."""
        with generation_state_lock:
            save_generation_state(generation_state)

    print()
    print("=" * 64)
    print("H3 AUTOMATED DIRECTOR")
    print("=" * 64)
    print(f"Segment length:       {segment_length:g} seconds")
    print(f"Total story length:   {total_length:g} seconds")
    print(f"Total segments:       {total_segments}")
    print(f"Starting segment:     {resume_segment}")
    print(f"Initial megapixels:   {megapixels:g}")
    print(f"Steps:                {args.steps}")
    print(f"Visual Continuity:    {args.vision_continuity == 0 and 'disabled' or args.vision_continuity == 1 and 'every segment' or f'every {args.vision_continuity} segments'}")
    print(
        "Extension context:    "
        f"{getattr(args, 'context_frames', DEFAULT_CONTEXT_FRAMES)} frames"
    )
    print(f"Formatter:            {getattr(args, 'model', 'ministral')}")
    print(f"Global LoRAs:         {len(global_loras)}")
    print(
        "Auto refresh:         "
        + (
            f"every {refresh_interval} segment(s)"
            if refresh_interval is not None
            else "disabled"
        )
    )
    print(
        "Vision continuity:    "
        + (
            "disabled"
            if args.vision_continuity == 0
            else (
                "every segment"
                if args.vision_continuity == 1
                else f"every {args.vision_continuity} segment(s)"
            )
        )
    )
    print("Director prompting:    2-stage raw scene -> H3 formatter")
    if beats:
        print(f"Story beats:          {len(beats)}")
        print("Persistent state:     generation_state.json")
    else:
        print("Story beats:          disabled (beats.txt is blank)")
        print("Beat progress file:   disabled")
        print("Persistent state:     generation_state.json")
    print("=" * 64)

    # Validate both workflows before spending time on generation.
    initial_test = load_workflow(INITIAL_WORKFLOW_FILE)
    append_test = load_workflow(APPEND_WORKFLOW_FILE)
    refresh_test = None
    validate_workflow(
        initial_test,
        f"initial workflow '{INITIAL_WORKFLOW_FILE}'",
        is_append=False
    )
    validate_workflow(
        append_test,
        f"append workflow '{APPEND_WORKFLOW_FILE}'",
        is_append=True
    )
    if refresh_interval is not None:
        refresh_test = load_workflow(REFRESH_WORKFLOW_FILE)
        validate_refresh_workflow(
            refresh_test,
            f"refresh workflow '{REFRESH_WORKFLOW_FILE}'",
        )
        copy_reference_image_inputs(
            initial_test,
            refresh_test,
            f"refresh workflow '{REFRESH_WORKFLOW_FILE}'",
        )
    verify_reference_images(
        initial_test,
        append_test,
        refresh_workflow=refresh_test,
    )
    if phrase_exclusions_found:
        exclusion_count_label = (
            "entry" if len(phrase_exclusions) == 1 else "entries"
        )
        print(
            f"Phrase exclusions file found: {PHRASE_EXCLUSIONS_FILE} "
            f"({len(phrase_exclusions)} {exclusion_count_label})."
        )
    verify_global_loras(global_loras)
    print("Workflow validation passed.")
    if resume_segment == 1:
        checkpoint_generation_state()


    def continuity_state_sha(state):
        return hashlib.sha256(
            json.dumps(
                state,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def build_segment_fingerprint(
        segment_number,
        completed_ids,
        recent_items,
        opening_state,
        opening_summary_text,
        dialogue_exclusions,
    ):
        conditioning_mode = conditioning_mode_for_segment(
            segment_number,
            refresh_interval,
        )
        return json.dumps(
            {
                "segment": int(segment_number),
                "conditioning_mode": conditioning_mode,
                "completed_beat_ids": sorted(
                    normalize_completed_beat_ids(beats, completed_ids)
                ),
                "recent_results": list(recent_items),
                "dialogue_exclusions": list(dialogue_exclusions),
                "gen_rules_sha256": hashlib.sha256(
                    str(gen_rules or "").encode("utf-8")
                ).hexdigest(),
                "opening_state_sha256": continuity_state_sha(opening_state),
                "opening_summary_sha256": hashlib.sha256(
                    str(opening_summary_text or "").encode("utf-8")
                ).hexdigest(),
                "subject_definitions_sha256": hashlib.sha256(
                    str(subject_definitions or "").encode("utf-8")
                ).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def build_segment_bundle(
        segment_number,
        completed_ids,
        recent_items,
        opening_state,
        opening_summary_text,
        dialogue_exclusions,
    ):
        elapsed = (segment_number - 1) * segment_length
        current_duration = min(segment_length, total_length - elapsed)
        active_beat_id = segment_number if beats else None
        current_phase = story_arc_phase_for_beat(macro_arc, active_beat_id)
        conditioning_mode = conditioning_mode_for_segment(
            segment_number,
            refresh_interval,
        )
        segment_director_rules = build_director_rules(
            total_length,
            current_duration,
            total_segments,
            subject_definitions,
            segment_number,
            beats_enabled=bool(beats),
            conditioning_mode=conditioning_mode,
            gen_rules=gen_rules,
        )
        opening_summary = (
            str(opening_summary_text or "").strip()
            if segment_number > 1 else ""
        )
        excluded_picture_ids = (
            get_conditioning_excluded_picture_ids(
                opening_state,
                conditioning_mode,
            )
            if conditioning_mode != "initial" else set()
        )
        # Phase 2 is already H3-ready opening prose; use the same concise text
        # for both Director continuity and the final H3 prompt.
        h3_opening_summary = opening_summary
        messages, estimated_tokens, recent_count = build_generation_messages(
            director_rules=segment_director_rules,
            story=story,
            beats=beats,
            completed_beat_ids=completed_ids,
            recent_results=recent_items,
            current_segment=segment_number,
            total_segments=total_segments,
            segment_length=segment_length,
            total_length=total_length,
            continuity_summary=opening_summary,
            subject_definitions=subject_definitions,
            conditioning_mode=conditioning_mode,
            dialogue_exclusions=dialogue_exclusions,
            current_phase=current_phase,
        )
        return {
            "segment": segment_number,
            "current_duration": current_duration,
            "active_beat_id": active_beat_id,
            "conditioning_mode": conditioning_mode,
            "loras": beat_loras(beats, active_beat_id, global_loras),
            "messages": messages,
            "estimated_tokens": estimated_tokens,
            "recent_count": recent_count,
            "opening_state": opening_summary,
            "registry_state": opening_state,
            "opening_summary": opening_summary,
            "h3_opening_summary": h3_opening_summary,
            "excluded_picture_ids": sorted(excluded_picture_ids),
            "dialogue_exclusions": list(dialogue_exclusions),
            "gen_rules": gen_rules,
            "current_phase": copy.deepcopy(current_phase or {}),
            "opening_state_sha256": continuity_state_sha(opening_state),
            "fingerprint": build_segment_fingerprint(
                segment_number,
                completed_ids,
                recent_items,
                opening_state,
                opening_summary,
                dialogue_exclusions,
            ),
        }

    def request_prefetched_segment(bundle, cancellation_event):
        if cancellation_event.is_set():
            raise RuntimeError("prefetched director request was cancelled")
        payload = request_segment_llm(bundle, beats, run_id, run_config)
        if cancellation_event.is_set():
            raise RuntimeError("prefetched director request was cancelled")
        prefetched_checkpoint = {
            "segment_number": int(payload["segment"]),
            "fingerprint": payload["fingerprint"],
            "llm_result": copy.deepcopy(payload["llm_result"]),
        }
        with generation_state_lock:
            # Recheck under the same lock used by render-failure cleanup so a
            # cancelled prefetch cannot be written back after being discarded.
            if cancellation_event.is_set():
                raise RuntimeError("prefetched director request was cancelled")
            generation_state["prefetched_next_prompt"] = prefetched_checkpoint
            save_generation_state(generation_state)
        print(
            f"Prefetched prompt for segment {payload['segment']} saved to "
            "generation_state.json.",
            flush=True,
        )
        return payload

    run_start_time = time.perf_counter()
    prefetched_next = None
    pending_previous_render_future = None
    render_futures_by_segment = {}
    # Set by finalize_skipped_vision_segment once it has finished appending a
    # non-final segment's video path to generated_video_paths. The final
    # segment is always drained synchronously below, so this event is only
    # relevant when a later segment needs the preceding background render.
    pending_render_finalized = threading.Event()
    for segment in segments_to_generate:
        if is_new_phase_start(beats, segment):
            #Dynamic Subject cleanup at phase boundaries is intentionally
            #disabled so Subjects established in earlier phases persist.
            # continuity_state, removed_subject_names = (
            #     reset_generation_state_subjects_for_new_phase(
            #         generation_state,
            #         base_subject_definitions,
            #         continuity_state,
            #     )
            # )
            # additional_subject_definitions = []
            # subject_definitions = base_subject_definitions
            # save_generation_state(generation_state)
            phase_number = beats[segment - 1].phase_number
            print(
                f"Starting phase {phase_number} at segment {segment}; retaining "
                "dynamically created Subjects from earlier phases."
            )
        segment_bundle = build_segment_bundle(
            segment,
            completed_beat_ids,
            recent_results,
            continuity_state,
            continuity_summary,
            generation_state.get("recent_dialogues", []),
        )
        if prefetched_next is not None:
            if prefetched_next["segment"] != segment:
                prefetched_next["cancellation_event"].set()
                if not prefetched_next["future"].done():
                    prefetched_next["future"].cancel()
                with generation_state_lock:
                    removed_prefetch = generation_state.pop(
                        "prefetched_next_prompt",
                        None,
                    )
                    if removed_prefetch is not None:
                        save_generation_state(generation_state)
                prefetched_next = None

        print()
        print("=" * 64)
        print(
            f"SEGMENT {segment}/{total_segments} "
            f"({segment_bundle['current_duration']:g} seconds)"
        )
        print("=" * 64)
        print(
            f"Estimated LLM input context: "
            f"{segment_bundle['estimated_tokens']}/{LLM_INPUT_TOKEN_BUDGET} tokens "
            f"(recent exact segments: {segment_bundle['recent_count']})"
        )

        payload = None
        if prefetched_next is not None:
            try:
                speculative_payload = prefetched_next["future"].result()
                if (
                    speculative_payload["fingerprint"]
                    == segment_bundle["fingerprint"]
                ):
                    payload = speculative_payload
                    print(f"Using prefetched LLM response for segment {segment}.")
                else:
                    print(
                        f"Discarded prefetched LLM response for segment {segment} "
                        "because the confirmed beat, continuity, or subject state "
                        "differed; re-querying the LLM."
                    )
            except Exception as error:
                print(
                    f"WARNING: prefetched LLM response for segment {segment} failed: "
                    f"{error}. Regenerating now."
                )
            finally:
                with generation_state_lock:
                    removed_prefetch = generation_state.pop(
                        "prefetched_next_prompt",
                        None,
                    )
                    if removed_prefetch is not None:
                        save_generation_state(generation_state)
                prefetched_next = None
        if payload is None:
            payload = request_segment_llm(
                segment_bundle,
                beats,
                run_id,
                run_config,
            )

        llm_result = dict(payload["llm_result"])
        llm_result["detailed_description"] = (
            inject_persistent_state_into_description(
                get_detailed_description(llm_result, ""),
            )
        )
        payload["llm_result"] = llm_result
        loras = payload["loras"]
        reported_beat_ids = llm_result.get("completed_beat_ids", [])

        # Register stable identities visible in the Director result before H3.
        # Dialogue uses Character Name (SN), so the speaker ID itself can supply
        # a stable Subject number. Planned named characters are also admitted
        # when their exact name actually appears in this segment.
        detailed_description = get_detailed_description(llm_result, "")
        expected_new_subjects = phase_characters_introduced_for_beat(
            macro_arc,
            segment,
        )
        continuity_state, dialogue_subject_names = register_inline_dialogue_subjects(
            continuity_state,
            subject_definitions,
            detailed_description,
            origin_segment=segment,
        )
        continuity_state, hinted_subject_names = register_named_subject_hints(
            continuity_state,
            subject_definitions,
            detailed_description,
            expected_new_subjects,
            origin_segment=segment,
        )
        newly_registered_names = list(dict.fromkeys(
            dialogue_subject_names + hinted_subject_names
        ))
        if newly_registered_names:
            previous_dynamic_definitions = list(additional_subject_definitions)
            additional_subject_definitions, new_subject_lines = (
                collect_additional_subject_definitions(
                    base_subject_definitions,
                    previous_dynamic_definitions,
                    continuity_state,
                    segment,
                )
            )
            subject_definitions = combine_subject_definitions(
                base_subject_definitions,
                additional_subject_definitions,
            )
            continuity_state = continuity_state_for_registry(
                subject_definitions,
                continuity_state,
            )
            generation_state["subject_registry_state"] = migrate_continuity_state(
                continuity_state
            )
            print("Registered new Subject definition(s) before H3 prompt:")
            for definition in new_subject_lines:
                print(f"  {definition}")

        hard_cut_subject_continuity = ""
        if is_hard_cut_segment(segment):
            hard_cut_subject_continuity = build_hard_cut_subject_continuity_from_state(
                subject_definitions,
                llm_result,
                continuity_state,
            )
        previous_visible_subject_ids = extract_previous_visible_subject_ids(
            recent_results,
            segment,
        )
        h3_prompt = build_h3_prompt(
            llm_result,
            subject_definitions,
            hard_cut_subject_continuity,
            payload["h3_opening_summary"],
            segment,
            ff=args.ff,
            conditioning_mode=segment_bundle["conditioning_mode"],
            excluded_picture_ids=segment_bundle.get("excluded_picture_ids"),
            continuity_state=continuity_state,
            previous_visible_subject_ids=previous_visible_subject_ids,
        )
        # Phase 2 writes the opening of the NEXT segment, so give it the phase
        # that contains the next beat when one exists. On the final segment,
        # retain the current phase for a complete debug record.
        continuity_phase_beat = (
            min(segment + 1, total_segments) if beats else segment
        )
        continuity_phase = story_arc_phase_for_beat(
            macro_arc,
            continuity_phase_beat,
        ) or segment_bundle.get("current_phase", {})
        candidate_future = None
        continuity_pipeline_result = None
        if segment < total_segments:
            candidate_future = summary_executor.submit(
                request_combined_continuity,
                h3_prompt,
                continuity_phase,
                history_metadata={
                    "run_id": run_id,
                    "source_sha256": run_config["source_sha256"],
                    "purpose": "combined_continuity",
                    "segment": segment,
                    "attempt": 1,
                    "conditioning_mode": segment_bundle["conditioning_mode"],
                },
                defer_opening=True,
            )
            print(f"Combined continuity requested for segment {segment} during render.")
        else:
            print(
                f"Skipping continuity for final segment {segment}; "
                "no later segment needs its state."
            )

        prompt_completed_beat_ids, _ = print_minimax_beat_plan(
            beats,
            completed_beat_ids,
            reported_beat_ids
        )

        print()
        print(h3_prompt)
        print()

        if segment > 1 and previous_video_path is None and pending_previous_render_future is not None:
            try:
                _, previous_video_path, _, _, _ = pending_previous_render_future.result()
                generated_video_paths.append(previous_video_path)
            except Exception as error:
                print(
                    f"WARNING: waiting for the previous segment render to finish "
                    f"before starting segment {segment} failed: {error}"
                )
                raise
            finally:
                pending_previous_render_future = None

        if render_executor is None:
            raise RuntimeError("A background ComfyUI render executor is required.")
        vision_required = should_run_vision_continuity(
            segment,
            getattr(args, "vision_continuity", 1),
            refresh_interval,
        )
        render_started = threading.Event()
        render_future = render_executor.submit(
            render_segment_with_retries,
            segment,
            segment_bundle["current_duration"],
            megapixels,
            h3_prompt,
            previous_video_path,
            args.steps,
            loras=loras,
            context_frames=getattr(
                args,
                "context_frames",
                DEFAULT_CONTEXT_FRAMES,
            ),
            render_started_event=render_started,
            refresh_interval=refresh_interval,
            continuity_state=continuity_state,
            continuity_summary=continuity_summary,
        )
        render_futures_by_segment[int(segment)] = render_future
        # A cadence-skipped final render must still be completed on the main
        # path. If it is submitted as a background render, the loop can reach
        # stitch_videos after Future.result() but before the future's done
        # callback has appended the final path. The reusable completion event
        # is not sufficient here: it may already be set by an earlier segment.
        if not vision_required and segment < total_segments:
            pending_previous_render_future = render_future
        while not render_started.wait(0.05):
            if render_future.done():
                # Surface workflow preparation/queue failures instead of waiting
                # forever for a render-start signal that cannot arrive.
                render_future.result()
        print(
            f"ComfyUI render started for segment {segment}; building the "
            "prompt-derived end-state prediction while the video renders."
        )

        # The combined continuity call predicts the ending from the prompt while
        # H3 renders. Phase 2 is deferred until rendered visual facts are
        # available only when the cadence actually requires a visual check.
        if candidate_future is not None:
            try:
                continuity_pipeline_result = candidate_future.result()
            except Exception as error:
                print(
                    f"WARNING: combined continuity for segment {segment} failed: "
                    f"{error}; retaining the last continuity outputs."
                )
                continuity_pipeline_result = None

        if continuity_pipeline_result is not None:
            prompt_reduced_continuity_state = copy.deepcopy(
                continuity_pipeline_result["reduced_state"]
            )
            if vision_required:
                print(
                    f"Combined continuity completed for segment {segment}; "
                    "Phase 2 is waiting for rendered visual state."
                )
            else:
                print(
                    f"Combined continuity completed for segment {segment}; "
                    "vision continuity is disabled for this cadence, so Phase 2 "
                    "uses the prompt-derived state immediately."
                )

        # Dynamic identities still come from explicit Director text and stay in
        # the internal registry only. They are not synthesized from continuity
        # JSON, which keeps the three continuity calls narrowly scoped.
        additional_subject_definitions, appended_subject_lines = (
            collect_additional_subject_definitions(
                base_subject_definitions,
                additional_subject_definitions,
                continuity_state,
                segment,
            )
        )
        subject_definitions = combine_subject_definitions(
            base_subject_definitions,
            additional_subject_definitions,
        )
        continuity_state = continuity_state_for_registry(
            subject_definitions,
            continuity_state,
        )
        if appended_subject_lines:
            print("Registered video-created subject definition(s) internally:")
            for definition in appended_subject_lines:
                print(f"  {definition}")

        if beats:
            completed_beat_ids = apply_reported_beat_completions(
                beats,
                completed_beat_ids,
                reported_beat_ids,
                segment,
            )
            generation_state["beat_progress"] = {
                "completed_beat_ids": sorted(completed_beat_ids),
                "last_segment_number": segment,
                "newly_completed_beat_ids": prompt_completed_beat_ids,
            }
        recent_results.append((segment, llm_result))
        recent_results = recent_results[-RECENT_SEGMENTS_MAX:]
        next_dialogue_exclusions = collect_recent_dialogues(
            list(generation_state.get("segments", []))
            + [{
                "segment_number": segment,
                "llm_result": llm_result,
                "dialogues": extract_spoken_dialogues(llm_result),
            }]
        )
        generation_state["continuity_prompt_state"] = copy.deepcopy(
            prompt_reduced_continuity_state
        )
        generation_state["subject_registry_state"] = migrate_continuity_state(
            continuity_state
        )

        # Persist the two-phase continuity working state before waiting for
        # ComfyUI's render response. The completed-segment record is
        # deliberately added only after ComfyUI returns a verified video path,
        # so an interrupted or failed render is never advertised as resumable.
        checkpoint_generation_state()
        print(
            f"Prompt-derived continuity prediction saved before the ComfyUI "
            f"response for segment {segment}."
        )

        # When the cadence skips rendered-frame vision continuity, the prompt-
        # derived continuity state is authoritative and the next Director prompt
        # can be prefetched without waiting for the render to finish.
        if not vision_required and segment < total_segments:
            next_segment_starts_phase = is_new_phase_start(beats, segment + 1)
            if (
                segment < total_segments
                and director_prefetch_executor is not None
                and not next_segment_starts_phase
            ):
                next_bundle = build_segment_bundle(
                    segment + 1,
                    completed_beat_ids,
                    recent_results,
                    continuity_state,
                    continuity_summary,
                    next_dialogue_exclusions,
                )
                prefetch_cancellation = threading.Event()
                prefetched_next = {
                    "segment": segment + 1,
                    "cancellation_event": prefetch_cancellation,
                    "future": director_prefetch_executor.submit(
                        request_prefetched_segment,
                        next_bundle,
                        prefetch_cancellation,
                    ),
                }
                print(
                    f"Started LLM prefetch for segment {segment + 1} without waiting "
                    f"for segment {segment}'s video render because vision continuity "
                    "is skipped by cadence."
                )
            print(
                "Skipping the render wait for this segment so the next prompt can "
                "start immediately while the render continues in the background."
            )

            skipped_segment_number = int(segment)
            skipped_llm_result = copy.deepcopy(llm_result)
            skipped_completed_beat_ids = sorted(set(completed_beat_ids))
            skipped_prompt_state = copy.deepcopy(prompt_reduced_continuity_state)
            skipped_registry_state = migrate_continuity_state(continuity_state)
            skipped_prompt_completed_beat_ids = list(prompt_completed_beat_ids)

            def finalize_skipped_vision_segment(future):
                nonlocal previous_video_path, pending_previous_render_future
                try:
                    (
                        workflow,
                        video_path,
                        width,
                        height,
                        rendered_megapixels,
                    ) = future.result()
                except Exception:
                    print(
                        f"Segment {skipped_segment_number} render failed after the "
                        "cadence skipped its visual continuity check; the prompt-"
                        "derived state was already allowed to proceed."
                    )
                    pending_previous_render_future = None
                    pending_render_finalized.set()
                    return
                if not isinstance(video_path, str) or not video_path.strip():
                    print(
                        f"Segment {skipped_segment_number} finished without a valid "
                        "video path; skipping the background completion record."
                    )
                    pending_previous_render_future = None
                    pending_render_finalized.set()
                    return
                previous_video_path = os.path.abspath(video_path)
                generated_video_paths.append(previous_video_path)
                pending_previous_render_future = None
                pending_render_finalized.set()
                reduced_continuity_state = copy.deepcopy(skipped_prompt_state)
                continuity_summary = request_continuity_opening_state(
                    reduced_continuity_state,
                    continuity_phase,
                    history_metadata={
                        "run_id": run_id,
                        "source_sha256": run_config["source_sha256"],
                        "purpose": "continuity_phase_2_h3_opening",
                        "segment": skipped_segment_number,
                        "attempt": 1,
                        "conditioning_mode": segment_bundle["conditioning_mode"],
                        "state_source": "prompt_only",
                    },
                )
                with generation_state_lock:
                    completed_record = record_completed_segment(
                        generation_state,
                        skipped_segment_number,
                        video_path,
                        skipped_llm_result,
                        skipped_completed_beat_ids,
                        continuity_summary,
                        continuity_state=reduced_continuity_state,
                        continuity_summary_pending=False,
                        continuity_opening_state=continuity_summary,
                        subject_registry_state=skipped_registry_state,
                    )
                    completed_record["continuity_prompt_state"] = copy.deepcopy(
                        skipped_prompt_state
                    )
                    generation_state["continuity_prompt_state"] = copy.deepcopy(
                        skipped_prompt_state
                    )
                    if beats:
                        generation_state["beat_progress"] = {
                            "completed_beat_ids": sorted(skipped_completed_beat_ids),
                            "last_segment_number": skipped_segment_number,
                            "newly_completed_beat_ids": skipped_prompt_completed_beat_ids,
                        }
                    save_generation_state(generation_state)
                print(
                    f"Completed segment {skipped_segment_number} from the "
                    "prompt-derived state while its render finished in the "
                    "background."
                )

            render_future.add_done_callback(finalize_skipped_vision_segment)
            continue

        try:
            (
                workflow,
                video_path,
                width,
                height,
                rendered_megapixels,
            ) = render_future.result()
        except Exception:
            if prefetched_next is not None:
                prefetched_next["cancellation_event"].set()
                if not prefetched_next["future"].done():
                    prefetched_next["future"].cancel()
                with generation_state_lock:
                    generation_state.pop("prefetched_next_prompt", None)
                    save_generation_state(generation_state)
            print(
                f"Segment {segment} render failed; its LLM-returned working state "
                "was saved, but the segment was not marked complete."
            )
            raise
        print(
            f"Created: {video_path}\n"
            f"Resolution: {width} x {height} "
            f"({width * height / 1_000_000:.3f} MP; "
            f"target {rendered_megapixels:.2f} MP)"
        )

        # Rendered pixels are authoritative for fields they clearly show. The
        # prompt-derived Phase 1 state remains the fallback for occluded/unknown
        # facts.
        visual_result = None
        if segment < total_segments and vision_required:
            try:
                visual_result = request_visual_end_state(
                    video_path,
                    subject_definitions,
                    segment,
                )
                print()
                print("=" * 64)
                print(f"VISUAL END STATE: SEGMENT {segment}")
                print("=" * 64)
                print(json.dumps(
                    visual_result["end_state"],
                    ensure_ascii=False,
                    indent=2,
                ))
                print("=" * 64)
            except Exception as error:
                print(
                    f"WARNING: visual end-state observation for segment {segment} "
                    f"failed: {error}. Generation will continue without it."
                )

            visual_state_for_merge = (
                visual_result["end_state"] if visual_result is not None else {}
            )
            reduced_continuity_state = merge_prompt_and_visual_end_state(
                prompt_reduced_continuity_state,
                visual_state_for_merge,
            )
            print()
            print("=" * 64)
            print(f"MERGED END STATE: SEGMENT {segment} (VISUAL PRECEDENCE)")
            print("=" * 64)
            print(json.dumps(reduced_continuity_state, ensure_ascii=False, indent=2))
            print("=" * 64)
            state_source = "prompt_plus_visual"
        else:
            reduced_continuity_state = copy.deepcopy(prompt_reduced_continuity_state)
            print(
                f"Skipping rendered-frame vision continuity for segment {segment} "
                f"(cadence={getattr(args, 'vision_continuity', 1)}); using the "
                "prompt-derived continuity state."
            )
            state_source = "prompt_only"

        if segment < total_segments:
            try:
                continuity_summary = request_continuity_opening_state(
                    reduced_continuity_state,
                    continuity_phase,
                    history_metadata={
                        "run_id": run_id,
                        "source_sha256": run_config["source_sha256"],
                        "purpose": "continuity_phase_2_h3_opening",
                        "segment": segment,
                        "attempt": 1,
                        "conditioning_mode": segment_bundle["conditioning_mode"],
                        "state_source": state_source,
                    },
                )
            except Exception as error:
                print(
                    f"WARNING: Continuity Phase 2 for segment {segment} failed "
                    f"with {state_source} state: {error}; retaining the previous "
                    "opening continuity text."
                )

        generation_state["continuity_prompt_state"] = copy.deepcopy(
            prompt_reduced_continuity_state
        )
        generation_state["continuity_state"] = copy.deepcopy(
            reduced_continuity_state
        )
        generation_state["continuity_opening_state"] = continuity_summary
        generation_state["continuity_summary"] = continuity_summary

        generated_video_paths.append(video_path)
        previous_video_path = video_path

        # Commit the rendered video and structured continuity state together.
        # The lock also prevents a just-completed prompt prefetch from
        # serializing this dictionary halfway through the commit.
        with generation_state_lock:
            completed_record = record_completed_segment(
                generation_state,
                segment,
                video_path,
                llm_result,
                completed_beat_ids,
                continuity_summary,
                continuity_state=reduced_continuity_state,
                continuity_summary_pending=False,
                continuity_opening_state=continuity_summary,
                subject_registry_state=continuity_state,
            )
            completed_record["continuity_prompt_state"] = copy.deepcopy(
                prompt_reduced_continuity_state
            )
            generation_state["continuity_prompt_state"] = copy.deepcopy(
                prompt_reduced_continuity_state
            )
            if visual_result is not None:
                visual_raw = copy.deepcopy(visual_result["raw_end_state"])
                visual_state = copy.deepcopy(visual_result["end_state"])
                visual_paths = list(visual_result["frame_paths"])
                completed_record["visual_raw_end_state"] = visual_raw
                completed_record["visual_end_state"] = visual_state
                completed_record["visual_end_frame_paths"] = visual_paths
                generation_state["visual_raw_end_state"] = visual_raw
                generation_state["visual_end_state"] = visual_state
                generation_state["visual_end_frame_paths"] = visual_paths
            if beats:
                generation_state["beat_progress"] = {
                    "completed_beat_ids": sorted(completed_beat_ids),
                    "last_segment_number": segment,
                    "newly_completed_beat_ids": prompt_completed_beat_ids,
                }
            save_generation_state(generation_state)
        print(f"Completed segment {segment} committed with its rendered video.")

        next_segment_starts_phase = is_new_phase_start(beats, segment + 1)
        if (
            vision_required
            and segment < total_segments
            and director_prefetch_executor is not None
            and not next_segment_starts_phase
        ):
            next_bundle = build_segment_bundle(
                segment + 1,
                completed_beat_ids,
                recent_results,
                continuity_state,
                continuity_summary,
                next_dialogue_exclusions,
            )
            prefetch_cancellation = threading.Event()
            prefetched_next = {
                "segment": segment + 1,
                "cancellation_event": prefetch_cancellation,
                "future": director_prefetch_executor.submit(
                    request_prefetched_segment,
                    next_bundle,
                    prefetch_cancellation,
                ),
            }
            print(
                f"Started LLM prefetch for segment {segment + 1} after "
                f"segment {segment}'s visual continuity merge."
            )
        elif next_segment_starts_phase and director_prefetch_executor is not None:
            print(
                f"Skipped LLM prefetch for segment {segment + 1} because it "
                "starts a new phase."
            )

        elapsed_seconds = time.perf_counter() - run_start_time
        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)
        print(f"Cumulative runtime: {hours:02d}:{minutes:02d}:{seconds:02d}")

        #if segment % 5 == 0:
        #    free_vram()

    #free_vram()

    if beats:
        remaining = [
            beat_id
            for beat_id in range(1, len(beats) + 1)
            if beat_id not in completed_beat_ids
        ]
        if remaining:
            print("WARNING: Runtime ended with unfinished beats:")
            for beat_id in remaining:
                print(f"  [TODO] Beat {beat_id}: {beats[beat_id - 1]}")
        else:
            print(f"All {len(beats)} story beats were marked complete.")
    else:
        print("Story beat tracking was disabled for this run.")

    # Barrier: every submitted render must be complete before FFmpeg sees the
    # stitch list. Do not rely on the single mutable pending-future reference;
    # background-render callbacks can clear it while another segment is still
    # finishing. Recover paths from completed futures as a second line of
    # defence in case a callback has not appended one yet.
    for expected_segment in sorted(render_futures_by_segment):
        try:
            render_result = render_futures_by_segment[expected_segment].result()
        except Exception as error:
            print(
                f"WARNING: segment {expected_segment} render did not finish "
                f"before stitching: {error}"
            )
            raise
        if not isinstance(render_result, tuple) or len(render_result) < 2:
            raise RuntimeError(
                f"Segment {expected_segment} render returned no video result."
            )
        completed_video_path = render_result[1]
        if not isinstance(completed_video_path, str) or not completed_video_path.strip():
            raise RuntimeError(
                f"Segment {expected_segment} render returned an invalid video path."
            )
        completed_video_path = os.path.abspath(completed_video_path)
        if completed_video_path not in {
            os.path.abspath(path) for path in generated_video_paths
        }:
            generated_video_paths.append(completed_video_path)

    expected_render_count = len(render_futures_by_segment)
    if len(generated_video_paths) < expected_render_count + (resume_segment - 1):
        raise RuntimeError(
            "Cannot stitch video: not every completed segment has been added "
            f"to the stitch list ({len(generated_video_paths)} available)."
        )

    stitch_videos(generated_video_paths)


def main():
    # The context managers guarantee worker shutdown even when generation,
    # ComfyUI, checkpointing, or either LLM task raises an exception.
    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="continuity-summary",
    ) as summary_executor:
        with ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="director-prefetch",
        ) as director_prefetch_executor:
            with ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="comfyui-render",
            ) as render_executor:
                return _run_main(
                    summary_executor,
                    director_prefetch_executor,
                    render_executor,
                )


if __name__ == "__main__":
    install_immediate_interrupt_handlers()
    start_emergency_stop_listener()
    print("Emergency stop: press Ctrl+C (or Ctrl+Q on Windows).")
    try:
        main()
    except KeyboardInterrupt:
        print("\nGeneration cancelled by user.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as e:
        print("\n" + "=" * 64, file=sys.stderr)
        print("MINIMAX VIDEO GENERATION STOPPED", file=sys.stderr)
        print("=" * 64, file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        if os.environ.get("MINIMAX_DEBUG"):
            raise
        print(
            "Set MINIMAX_DEBUG=1 for a full traceback.",
            file=sys.stderr
        )
        raise SystemExit(1) from None
