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
import copy
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

from ministral_formatter import (
    MinistralFormatter,
    normalize_summary_subject_references,
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
COMFY_URL = os.environ.get(
    "MINIMAX_COMFY_URL",
    "http://127.0.0.1:8188"
).rstrip("/")

if os.name == "nt":
    DEFAULT_COMFY_OUTPUT = r"H:\images\output"
    DEFAULT_COMFY_INPUT = r"H:\ComfyUI\input"
else:
    DEFAULT_COMFY_OUTPUT = os.path.expanduser("~/ComfyUI/output")
    DEFAULT_COMFY_INPUT = os.path.expanduser("~/ComfyUI/input")

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

INITIAL_WORKFLOW_FILE = os.path.join(SCRIPT_DIR, "Minimax_auto_API.json")
APPEND_WORKFLOW_FILE = os.path.join(SCRIPT_DIR, "Minimax_auto_append_API.json")
STORY_FILE = os.path.join(SCRIPT_DIR, "story.txt")
BEATS_FILE = os.path.join(SCRIPT_DIR, "beats.txt")
SUBJECT_DEFINITIONS_FILE = os.path.join(SCRIPT_DIR, "subjects.txt")
GENERATION_STATE_FILE = os.path.join(SCRIPT_DIR, "generation_state.json")
PROMPT_HISTORY_FILE = os.path.join(SCRIPT_DIR, "prompt_history.txt")
FINAL_VIDEO = os.path.join(VIDEO_OUTPUT, "final.mp4")
PROMPT_HISTORY_LOCK = threading.Lock()

FRAME_RATE = 24
TRIM_FRAMES_AFTER_FIRST = 2
TRIM_SECONDS_AFTER_FIRST = TRIM_FRAMES_AFTER_FIRST / FRAME_RATE
MAX_COMFY_SEED = (2 ** 63) - 1
MAX_LLM_SEED = (2 ** 31) - 1

COMFY_QUEUE_RETRIES = 10
COMFY_QUEUE_RETRY_DELAY = 10
COMFY_HISTORY_MAX_ERRORS = 30
COMFY_HISTORY_RETRY_DELAY = 10
COMFY_RENDER_TIMEOUT = 15 * 60
COMFY_RENDER_RETRIES = 10
COMFY_RETRY_MEGAPIXEL_STEP = 0.02
CONTINUITY_STATE_VERSION = 3

LLM_INPUT_TOKEN_BUDGET = 14000
CHARS_PER_TOKEN_ESTIMATE = 3.5
STORY_CONTEXT_MAX_CHARS = 12000
DEFAULT_BEAT_LOOKAHEAD = 8
RECENT_SEGMENTS_MAX = 2
MINISTRAL_CONTENT_CORRECTION_ATTEMPTS = 1
SUMMARY_CONTENT_ATTEMPTS = 2
BEAT_GENERATION_CONTENT_ATTEMPTS = 3
BEAT_INSTRUCTION_REVIEW_ATTEMPTS = 3
BEAT_LLM_SAMPLING_PARAMETERS = {
    "temperature": 0.9,
    "top_p": 0.95,
    "presence_penalty": 0.55,
    "frequency_penalty": 0.3,
    "repeat_penalty": 1.08,
}

# Continuity safety rails. These are deliberately conservative: when the
# text-only continuity updater is uncertain, preserving the last committed
# state is safer than inventing a new irreversible body configuration.
SEMANTIC_SEGMENT_AUDIT = os.environ.get(
    "MINIMAX_SEMANTIC_SEGMENT_AUDIT", "1"
).strip().lower() not in {"0", "false", "no", "off"}
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
REFERENCE_IMAGE_NODE_NAMES = tuple(
    f"Reference Image {image_number}"
    for image_number in range(1, 7)
)


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
    parser.add_argument("segment_length", type=float)
    parser.add_argument("total_length", type=float)
    parser.add_argument("megapixels", type=float)
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
        "--model",
        choices=tuple(FORMATTER_CLASSES),
        default="ministral",
        help="select the response formatter (default: ministral)",
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

    return args


def get_segments_to_generate(resume_segment, total_segments):
    if resume_segment > total_segments:
        raise ValueError(
            f"--resume {resume_segment} exceeds the {total_segments} "
            "segments in this run."
        )
    return range(resume_segment, total_segments + 1)


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

    return workflow


def verify_reference_images(initial_workflow, append_workflow, input_directory=None):
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
        "MiniMax H3 Reference to Video",
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

    for image_number in range(1, 7):
        image_name = (
            initial_references.get(image_number)
            or append_references.get(image_number)
        )
        if image_name is None:
            continue
        image_path = os.path.join(input_directory, image_name)
        if not os.path.isfile(image_path):
            print(
                f"WARNING: Image {image_name} for reference slot "
                f"{image_number} was not found: {image_path}"
            )
            continue
        print(f"Image {image_name} verified.")


def build_run_config(
    segment_length,
    total_length,
    megapixels,
    total_segments,
    story="",
    beats=None,
    subject_definitions="",
    global_loras=None,
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


def parse_subject_registry(subject_definitions):
    """Parse independent name, Picture, and speaker mappings."""
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
                r"(?i)\b(?:created|established)\s+(?:by\s+<Video\s+1>|"
                r"in\s+generated\s+"
                r"video\s+segment\s+\d+)",
                line,
            ))
            speaker_id = (
                f"S{speaker}"
                if (speaker := next(iter(re.findall(r"(?i)\(S(\d+)\)", line)), None))
                else None
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
        "picture_ids": picture_ids,
        "picture_id": picture_id,
        "speaker_id": subject.get("speaker_id"),
        "origin_segment": subject.get("origin_segment"),
        "position": "N/A",
        "pose_action": "N/A",
        "wardrobe": {
            "upper": "N/A",
            "lower": "N/A",
            "footwear": "N/A",
            "other": "N/A",
        },
        # Persistent structural relationships belong here instead of being
        # mixed into transient pose/action prose. Examples: "fused to Jenny
        # at the waistline", "head attached", "left hand detached".
        "topology": "N/A",
        "body_state": "N/A",
        "physical_condition": "N/A",
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
            "created in generated video segment 1 and continued from "
            "<Video 1>."
        )
    def copy_continuity_fields(record, existing):
        if not isinstance(existing, dict):
            return
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
        if isinstance(existing.get("wardrobe"), dict):
            for garment in record["wardrobe"]:
                if isinstance(existing["wardrobe"].get(garment), str):
                    record["wardrobe"][garment] = existing["wardrobe"][garment]

    subjects = {}
    used_subject_ids = set()
    for subject_id, subject in registry.items():
        existing = current.get("subjects", {}).get(subject["name"], {})
        record = new_subject_continuity_record({
            **subject,
            "subject_id": subject_id,
        })
        copy_continuity_fields(record, existing)
        subjects[subject["name"]] = record
        used_subject_ids.add(subject_id)

    # A continuing video can establish an important subject that has no Picture
    # reference (a creature, vehicle, or newly introduced person). Preserve these
    # records instead of rebuilding the state exclusively from the Picture registry.
    next_subject_id = max(used_subject_ids, default=0) + 1
    for name, existing in current.get("subjects", {}).items():
        if name in subjects or not isinstance(existing, dict):
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
            "picture_ids": picture_ids,
            "picture_id": picture_ids[0] if picture_ids else None,
            "speaker_id": existing.get("speaker_id"),
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

# Terms that imply an irreversible or topology-changing state. A continuity
# candidate is not allowed to introduce one of these changes unless the newest
# segment description explicitly contains evidence for the same anatomical
# region. This blocks common state hallucinations such as a limb becoming
# detached merely because a different body part was described as detached.
_STRUCTURAL_CHANGE_STEMS = (
    "detach", "sever", "amputat", "decapitat", "fuse", "fusion", "attach",
    "merge", "split", "ruptur", "hatch", "birth", "emerg", "melt",
    "transform", "disintegrat", "crush", "break", "broken", "missing",
    "remove", "tear", "torn", "suspend", "upside-down", "upside down",
)
_ANATOMY_PHRASES = (
    "lower body", "upper body", "head", "face", "neck", "throat", "chest",
    "sternum", "ribcage", "rib cage", "abdomen", "belly", "belly button",
    "waist", "waistline", "torso", "spine", "back", "shoulder", "arm",
    "wrist", "hand", "finger", "breast", "leg", "knee", "foot", "hair",
    "mouth", "jaw", "mandible", "wing", "horn", "tail", "limb",
)


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
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    return cleaned or "N/A"


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


def migrate_continuity_state(state):
    """Return a valid structured state without discarding legacy prose."""
    if not isinstance(state, dict):
        return new_continuity_state()
    migrated = new_continuity_state()
    environment = state.get("environment")
    if isinstance(environment, dict):
        migrated["environment"] = {
            "location": str(environment.get("location", "N/A")),
            "persistent_state": str(
                environment.get("persistent_state", "N/A")
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
                record.setdefault("topology", "N/A")
        migrated["subjects"] = normalized_subjects
    return scrub_continuity_state(migrated)


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


def _subject_picture_tags(record):
    return [
        f"<Picture {picture_id}>"
        for picture_id in record.get("picture_ids", [])
        if picture_id is not None
    ]


def _subject_opening_sentence(subject_id, name, record, summary=False):
    tag = f"<Subject {subject_id}>"
    position = _known_continuity_value(record.get("position"))
    pose_action = _known_continuity_value(record.get("pose_action"))
    wardrobe = _subject_wardrobe(record)
    topology = _known_continuity_value(record.get("topology"))
    body_state = _known_continuity_value(record.get("body_state"))
    physical_condition = _known_continuity_value(
        record.get("physical_condition")
    )
    held_props = [
        str(prop).strip()
        for prop in record.get("held_props", [])
        if str(prop).strip() and str(prop).strip().upper() != "N/A"
    ]

    if summary:
        if record.get("picture_ids"):
            sentence = f"{tag} {name}"
        else:
            sentence = f"{tag} {name} continues from <Video 1>"
        # Keep the Ref2VA summary intentionally compact. The concrete opening
        # state is written once in retention_analysis below; repeating pose and
        # wardrobe here caused competing versions of the same state to reach H3.
        if position:
            sentence += f" remains {position}" if record.get("picture_ids") else f" and remains {position}"
        return sentence.rstrip(".; ") + "."

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
    if topology:
        facts.append(f"Topology: {topology}")
    if body_state:
        facts.append(f"Body state: {body_state}")
    if physical_condition:
        facts.append(f"Physical condition: {physical_condition}")
    if held_props:
        facts.append(f"Held props: {_english_join(held_props)}")
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


def format_authoritative_opening_state(state, subject_definitions=""):
    """Render MiniMax H3 video-continuation and reference-retention guidance."""
    state = continuity_state_for_registry(subject_definitions, state)
    subjects = _ordered_continuity_subjects(state)
    if not subjects:
        raise RuntimeError(
            "Cannot render authoritative continuation guidance: no subjects "
            "were available."
        )

    location = _known_continuity_value(state["environment"].get("location"))
    location_text = location or "environment"
    lines = [
        "<Video 1> is the immediately preceding successfully rendered video "
        "and provides the authoritative continuation starting point. Preserve "
        f"its {location_text}, lighting, spatial layout, subject positions, "
        "wardrobe condition, physical states, props, and environmental "
        "continuity until an action in this target video visibly changes them.",
        "",
        "summary:",
        "",
    ]

    summary_sentences = [
        "[video continuation + reference generation] The target video continues "
        "directly from the final observable state of <Video 1>."
    ]
    summary_sentences.extend(
        _subject_opening_sentence(subject_id, name, record, summary=True)
        for subject_id, name, record in subjects
    )

    picture_numbers = []
    picture_subject_names = []
    for _, name, record in subjects:
        record_pictures = [
            int(value)
            for value in record.get("picture_ids", [])
            if isinstance(value, int) or str(value).isdigit()
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
        picture_tags = _subject_picture_tags(record)
        if picture_tags:
            source = (
                f"Preserve {name}'s identity from {_english_join(picture_tags)}."
            )
        else:
            source = (
                f"Preserve {name}'s established appearance from <Video 1>."
            )
        details = _subject_opening_sentence(subject_id, name, record)
        line = f"<Subject {subject_id}>: fully_preserved - {source}"
        if details:
            line += f" {details}"
        lines.extend([line, ""])

    video_details = []
    persistent_state = _known_continuity_value(
        state["environment"].get("persistent_state")
    )
    camera = _known_continuity_value(state.get("camera"))
    ongoing_action = _known_continuity_value(state.get("ongoing_action"))
    ongoing_audio = _known_continuity_value(state.get("ongoing_audio"))
    if persistent_state:
        video_details.append(persistent_state)
    if camera:
        video_details.append(f"camera/framing: {camera}")
    if ongoing_action:
        video_details.append(f"ongoing action: {ongoing_action}")
    if ongoing_audio:
        video_details.append(f"ongoing audio: {ongoing_audio}")
    subject_names = _english_join(name for _, name, _ in subjects)
    video_line = (
        f"<Video 1>: fully_preserved - Preserve the {location_text}, lighting, "
        f"spatial layout, positions of {subject_names}, wardrobe condition, "
        "physical states, props, and immediate physical continuity from the "
        "final frame of the preceding video."
    )
    if video_details:
        video_line += f" Also preserve {_english_join(video_details)}."
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
            f"  picture_ids: {json.dumps(subject.get('picture_ids', [subject['picture_id']]))}\n"
            f"  continuation_source: "
            f"{'Picture reference(s)' if subject.get('picture_ids') else '<Video 1>'}\n"
            f"  speaker_id: {speaker}"
        )
    return "\n".join(lines)


def append_video_subject_definitions(
    subject_definitions,
    continuity_state,
    origin_segment,
    path=SUBJECT_DEFINITIONS_FILE,
):
    """Persist newly created video-only subjects and return updated definitions."""
    existing_text = str(subject_definitions or "").strip()
    registry = parse_subject_registry(existing_text)
    known_ids = set(registry)
    known_names = {
        subject["name"].lower() for subject in registry.values()
    }
    state = continuity_state_for_registry(existing_text, continuity_state)
    appended_lines = []

    for subject_id, name, record in _ordered_continuity_subjects(state):
        if record.get("picture_ids"):
            continue
        if subject_id in known_ids or name.lower() in known_names:
            continue
        if not re.fullmatch(
            r"(?i)[A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*)*",
            name,
        ):
            print(
                "WARNING: Cannot append video-created subject with invalid "
                f"canonical name {name!r}; use words, spaces, apostrophes, "
                "or hyphens only."
            )
            continue
        try:
            created_in_segment = int(
                record.get("origin_segment") or origin_segment
            )
        except (TypeError, ValueError):
            created_in_segment = int(origin_segment)
        record["origin_segment"] = created_in_segment
        appended_lines.append(
            f"<Subject {subject_id}> is {name}, created in generated "
            f"video segment {created_in_segment} and continued from <Video 1>."
        )
        known_ids.add(subject_id)
        known_names.add(name.lower())

    if not appended_lines:
        return existing_text, []

    updated_text = "\n".join(
        part for part in (existing_text, "\n".join(appended_lines)) if part
    )
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix="subjects_",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(updated_text + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
    return updated_text, appended_lines


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


def new_generation_state(run_config):
    return {
        "version": 1,
        "config": dict(run_config),
        "segments": [],
        "continuity_summary": "",
        "continuity_state": new_continuity_state(),
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


def restore_generation_state(
    resume_segment,
    run_config,
    beats,
    path=GENERATION_STATE_FILE,
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
    if len(records) < required_count:
        raise RuntimeError(
            f"Cannot resume at segment {resume_segment}: checkpoint contains "
            f"only {len(records)} completed segment(s)."
        )

    restored_records = []
    video_paths = []
    recent_results = []
    completed_beat_ids = set()
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
        restored_records.append(record)
        video_paths.append(video_path)
        recent_results.append((expected_segment, llm_result))
        completed_beat_ids = normalize_completed_beat_ids(
            beats,
            record.get("completed_beat_ids", []),
        )

    state["segments"] = restored_records
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
        state["continuity_summary"] = restored_records[-1].get(
            "continuity_summary",
            state.get("continuity_summary", ""),
        )
        state["continuity_summary_pending"] = bool(
            restored_records[-1].get("continuity_summary_pending", False)
        )
        state["continuity_state"] = migrate_continuity_state(
            restored_records[-1].get(
                "continuity_state",
                state.get("continuity_state"),
            )
        )
    else:
        state["continuity_summary"] = ""
        state["continuity_state"] = new_continuity_state()
        state["continuity_summary_pending"] = False
    return {
        "state": state,
        "video_paths": video_paths,
        "previous_video_path": video_paths[-1] if video_paths else None,
        "recent_results": recent_results[-RECENT_SEGMENTS_MAX:],
        "completed_beat_ids": completed_beat_ids,
        "continuity_summary": state.get("continuity_summary", ""),
        "continuity_state": migrate_continuity_state(
            state.get("continuity_state")
        ),
        "continuity_summary_pending": state.get(
            "continuity_summary_pending", False
        ),
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
):
    records = state.setdefault("segments", [])
    if continuity_state is None:
        continuity_state = state.get("continuity_state")
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
        "completed_beat_ids": sorted(completed_beat_ids),
        "continuity_summary": continuity_summary,
        "continuity_state": migrate_continuity_state(continuity_state),
        "continuity_summary_pending": bool(continuity_summary_pending),
    }
    records.append(record)
    state["beat_progress"] = {
        "completed_beat_ids": sorted(completed_beat_ids),
        "last_segment_number": segment_number,
        "newly_completed_beat_ids": [],
    }
    state["continuity_summary"] = continuity_summary
    state["continuity_state"] = migrate_continuity_state(continuity_state)
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
        (MATH_NODE_NAME, "values.a", DURATION_NODE_NAME, 0),
        (VIDEO_EXTEND_NODE_NAME, "length", MATH_NODE_NAME, 1),
        (VIDEO_EXTEND_NODE_NAME, "prompt", PROMPT_NODE_NAME, 0),
        (VIDEO_EXTEND_NODE_NAME, "context_latent", ENCODE_AV_NODE_NAME, 0),
        (VIDEO_EXTEND_NODE_NAME, "ref_images", IMAGE_BATCH_NODE_NAME, 0),
        (ENCODE_AV_NODE_NAME, "images", LOAD_VIDEO_NODE_NAME, 0),
        (ENCODE_AV_NODE_NAME, "audio", LOAD_VIDEO_NODE_NAME, 2),
        ("Basic Guider", "conditioning", VIDEO_EXTEND_NODE_NAME, 0),
        ("SamplerCustomAdvanced", "latent_image", VIDEO_EXTEND_NODE_NAME, 1),
        ("Create Video", "images", "VAE Decode", 0),
        ("Create Video", "audio", "VAE Decode Audio", 0),
        (SAVE_VIDEO_NODE_NAME, "video", "Create Video", 0)
    )

    for args in required_connections:
        validate_named_connection(
            workflow,
            *args,
            workflow_label=workflow_label
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


class BeatDefinition(str):
    def __new__(cls, text, loras=None):
        beat = super().__new__(cls, text)
        beat.loras = tuple(loras or ())
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
    for line in raw.splitlines():
        beat = line.strip()
        if not beat or beat.startswith("#"):
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
        beats.append(parse_beat_definition(beat))

    if global_lora is not None:
        beats = [
            BeatDefinition(str(beat), (global_lora, *beat.loras))
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
        }
        for beat in beats or []
    ]


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


def format_beat_progress(beats, completed_beat_ids):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    next_id = get_next_beat_id(beats, completed)
    lines = []
    for beat_id, beat_text in enumerate(beats, start=1):
        if beat_id in completed:
            status = "DONE"
        elif beat_id == next_id:
            status = "NEXT"
        else:
            status = "TODO"
        lines.append(f"[{status}] B{beat_id:03d}: {beat_text}")
    return "\n".join(lines)


def build_bounded_beat_state(
    beats,
    completed_beat_ids,
    segment_number=None,
    total_segments=None,
    lookahead=DEFAULT_BEAT_LOOKAHEAD,
):
    """Return only the beat window needed by the director for this segment."""
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    next_id = get_next_beat_id(beats, completed)
    state = {
        "completed_through": len(completed) or None,
        "active_beat": None,
        "ordered_lookahead": [],
        "beats_completed": len(completed),
        "beats_remaining": max(0, len(beats) - len(completed)),
        "active_deadline_segment": None,
    }
    if next_id is None:
        return state

    state["active_beat"] = {
        "id": next_id,
        "text": beats[next_id - 1],
    }
    state["ordered_lookahead"] = [
        {"id": beat_id, "text": beats[beat_id - 1]}
        for beat_id in range(
            next_id + 1,
            min(len(beats), next_id + lookahead) + 1,
        )
    ]
    if total_segments is not None and segment_number is not None:
        state["active_deadline_segment"] = get_beat_deadline_segment(
            next_id,
            beats,
            total_segments,
        )
    return state


def get_accepted_reported_beat_ids(
    beats,
    completed_beat_ids,
    reported_beat_ids
):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
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

    accepted = []
    next_id = get_next_beat_id(beats, completed)
    while next_id is not None and next_id in reported:
        accepted.append(next_id)
        completed.add(next_id)
        next_id = get_next_beat_id(beats, completed)
    return accepted


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
    print("Completing in this prompt:")
    if accepted:
        for beat_id in accepted:
            print(f"  B{beat_id:03d}: {beats[beat_id - 1]}")
    else:
        current_id = get_next_beat_id(beats, completed_beat_ids)
        print("  None reported complete by the formatted prompt.")
        if current_id is not None:
            print(f"  Still targeting B{current_id:03d}: {beats[current_id - 1]}")
    print("Next required after this prompt:")
    if next_id is None:
        print("  All required beats would be complete.")
    else:
        print(f"  B{next_id:03d}: {beats[next_id - 1]}")
    print("=" * 64)
    return accepted, next_id


def apply_reported_beat_completions(
    beats,
    completed_beat_ids,
    reported_beat_ids,
    segment_number
):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    valid_reported = set()

    for raw_id in reported_beat_ids or []:
        if isinstance(raw_id, bool):
            continue
        try:
            beat_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if 1 <= beat_id <= len(beats):
            valid_reported.add(beat_id)

    accepted = get_accepted_reported_beat_ids(
        beats,
        completed,
        valid_reported
    )
    completed.update(accepted)

    ignored = sorted(
        beat_id
        for beat_id in valid_reported
        if beat_id not in completed
    )

    if accepted:
        print(
            f"Segment {segment_number} completed beat(s): "
            + ", ".join(f"B{x:03d}" for x in accepted)
        )
    else:
        print(f"Segment {segment_number} completed no new required beats.")

    if ignored:
        print(
            "WARNING: Ignored out-of-order beat completion claim(s): "
            + ", ".join(f"B{x:03d}" for x in ignored)
        )

    return normalize_completed_beat_ids(beats, completed)


def get_beat_deadline_segment(beat_id, beats, total_segments):
    return max(1, math.ceil(beat_id * total_segments / len(beats)))


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

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        object_start = candidate.find("{")
        object_end = candidate.rfind("}")
        if object_start == -1 or object_end <= object_start:
            raise
        return json.loads(candidate[object_start:object_end + 1])


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
):
    last_error = None
    messages = normalize_lm_studio_messages(messages)
    for attempt in range(1, max_retries + 1):
        try:
            llm_seed = generate_random_llm_seed()
            request_payload = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4000,
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

            append_prompt_history(
                messages,
                metadata={
                    "response_format": response_format is not None,
                    **(history_metadata or {}),
                    "seed": llm_seed,
                    "sampling_parameters": sampling_metadata,
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
                    append_prompt_history(
                        fallback_payload["messages"],
                        metadata={
                            "response_format": False,
                            **(history_metadata or {}),
                            "request_variant": "without_response_format",
                            "seed": llm_seed,
                            "sampling_parameters": sampling_metadata,
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
            content = data["choices"][0]["message"]["content"]
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
            print(
                f"LLM request failed (attempt {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                time.sleep(retry_delay)

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

def build_beats_response_format(total_segments):
    if total_segments <= 0:
        raise ValueError("Beat generation requires at least one segment.")
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
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Exactly one concise, complete sentence."
                            ),
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


_BEAT_INSTRUCTIONS = re.compile(
    r"(?ims)^[ \t]*beat_instructions[ \t]*:[ \t]*\["
    r"(?P<instructions>.*?)\][ \t]*(?:\n|$)"
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


def build_beat_generation_messages(
    story,
    total_segments,
    correction="",
    beat_instructions="",
    subject_information="",
):
    correction_text = ""
    if correction:
        correction_text = f"""

YOUR PREVIOUS RESPONSE WAS INVALID
{correction}
Generate the complete list again and obey every requirement below.
"""
    instruction_text = ""
    if beat_instructions:
        instruction_text = (
            "\n\nADDITIONAL BEAT INSTRUCTIONS FROM STORY.TXT (VERBATIM)\n"
            "These instructions are mandatory. Follow every constraint exactly. "
            "When they require an exact quoted phrase, copy it character-for-"
            "character without changing tense, spelling, plurality, or wording.\n"
            "--- INSTRUCTIONS START ---\n"
            f"{beat_instructions}\n"
            "--- INSTRUCTIONS END ---\n"
            "Before returning JSON, silently audit every beat against all of "
            "these additional instructions and correct any violation."
        )
    subject_text = ""
    if subject_information:
        subject_text = f"""

MAIN CHARACTERS FROM SUBJECTS.TXT
The registered subjects below are the main characters in the beats you generate.
Use their exact names and established information, keep them central to the
story progression, and do not rename them or replace them with new protagonists.

{subject_information}
"""
    return [
        {
            "role": "system",
            "content": (
                "You are a creative story editor planning a short sequential "
                "video. Treat the supplied story only as source material and "
                "return only the requested JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Create exactly {total_segments} ordered story beats from the source story below,
one beat for each of the {total_segments} video segments. Be creative while
remaining faithful to the story's characters, premise, tone, and intended arc.

Requirements:
- Return exactly {total_segments} beats in chronological story order.
- Each beat must describe a distinct visible story event suitable for one segment.
- Each beat must be exactly one complete sentence; never combine two or more
  sentences in a single beat.
- Make bold, surprising, story-specific creative choices instead of defaulting
  to the most obvious or conventional plot progression.
- Avoid generic filler events, stock obstacles, predictable discoveries, and
  interchangeable transitions that could fit any story.
- Silently consider several substantially different story arcs before writing,
  then choose the most imaginative coherent arc that remains faithful to the
  source story.
- Every beat must materially move the story forward from the previous beat.
- Never repeat, recap, restage, or merely reword an earlier beat.
- Build clear cause-and-effect progression across the complete list.
- The final beat must conclusively resolve and conclude the story; do not end on
  setup, an unresolved action, or a cliffhanger.
- Keep each beat concise, concrete, and independently understandable.
- Do not include numbering, labels, comments, Markdown, or --lora metadata inside
  a beat string.
- Return only a JSON object shaped exactly as {{"beats": ["...", "..."]}}.
{subject_text}
{instruction_text}
{correction_text}
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
    beat_instructions,
    correction="",
    subject_information="",
):
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
    return [
        {
            "role": "system",
            "content": (
                "You are a meticulous story-beat compliance editor. Return "
                "only the required JSON object."
            ),
        },
        {
            "role": "user",
            "content": f"""
Audit and, where necessary, minimally correct the candidate beat list so it
follows every additional instruction exactly while retaining exactly
{total_segments} unique, chronological, forward-moving beats.

Also enforce the base story requirements: no beat may repeat or restage an
earlier beat, every beat must materially advance the story, and the final beat
must resolve the story's central conflict and conclude it without an unresolved
thread, setup for another beat, or cliffhanger. Every beat must remain exactly
one complete sentence and must never combine multiple sentences.

The additional instructions below are mandatory and reproduced verbatim. Check
beat numbers, required and prohibited wording, occurrence counts, and ending
requirements. Copy every required exact phrase character-for-character without
changing tense, spelling, plurality, or wording. Before returning, silently
verify compliance one final time.

--- ADDITIONAL INSTRUCTIONS START ---
{beat_instructions}
--- ADDITIONAL INSTRUCTIONS END ---
{subject_text}

CANDIDATE BEATS
{json.dumps({"beats": beats}, ensure_ascii=False, indent=2)}
{correction_text}

SOURCE STORY
--- STORY START ---
{story}
--- STORY END ---

Return only a JSON object shaped exactly as {{"beats": ["...", "..."]}}.
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


def parse_generated_beats(raw_result, total_segments):
    if total_segments <= 0:
        raise ValueError("Beat generation requires at least one segment.")

    candidate = raw_result
    if isinstance(candidate, str):
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
        if not isinstance(raw_beat, str):
            raise ValueError(f"Generated beat {index} must be text.")
        beat = " ".join(raw_beat.split()).strip()
        beat = re.sub(
            r"^(?:[-*\u2022]\s+|(?:B\s*0*)?\d+\s*[.):\-]\s*)",
            "",
            beat,
            flags=re.IGNORECASE,
        ).strip()
        if not beat:
            raise ValueError(f"Generated beat {index} is empty.")
        if "--lora" in beat.lower():
            raise ValueError(
                f"Generated beat {index} contains unsupported --lora metadata."
            )
        if not beat_is_single_complete_sentence(beat):
            raise ValueError(
                f"Generated beat {index} must be exactly one sentence; "
                "fragments and multiple sentences are not allowed."
            )
        beats.append(beat)

    normalized = [beat.casefold() for beat in beats]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Generated beats must not contain duplicates.")
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


def beat_contains_multiple_sentences(beat):
    """Detect a second top-level sentence without splitting common titles."""
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
        return True
    return False


def beat_is_single_complete_sentence(beat):
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


def save_generated_beats(beats, path=BEATS_FILE, lora_directive=""):
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
    saved_beats = [
        f"{beat} {lora_directive}" if lora_directive else beat
        for beat in beats
    ]
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
    content_attempts=BEAT_GENERATION_CONTENT_ATTEMPTS,
    history_metadata=None,
    beat_instructions="",
    instruction_review_attempts=BEAT_INSTRUCTION_REVIEW_ATTEMPTS,
    subject_information="",
    lora_directive="",
):
    if llm_request is None:
        llm_request = ask_llm
    if not str(story or "").strip():
        raise ValueError("Cannot generate story beats from an empty story.")
    if content_attempts <= 0:
        raise ValueError("Beat generation requires at least one content attempt.")

    response_format = build_beats_response_format(total_segments)
    correction = ""
    last_error = None
    beats = None
    for attempt in range(1, content_attempts + 1):
        messages = build_beat_generation_messages(
            story,
            total_segments,
            correction,
            beat_instructions,
            subject_information,
        )
        verify_subjects_in_beat_messages(messages, subject_information)
        raw_result = llm_request(
            messages,
            response_format=response_format,
            history_metadata={
                "purpose": "beat_generation",
                "attempt": attempt,
                "total_segments": total_segments,
                **(history_metadata or {}),
            },
            **BEAT_LLM_SAMPLING_PARAMETERS,
        )
        try:
            beats = parse_generated_beats(raw_result, total_segments)
        except ValueError as error:
            last_error = error
            correction = str(error)
            if attempt < content_attempts:
                print(
                    "LLM returned an invalid beat list; requesting a corrected "
                    f"list ({attempt + 1}/{content_attempts}): {error}"
                )
            continue

        break

    if beats is None:
        raise RuntimeError(
            f"LM Studio did not return exactly {total_segments} valid, unique "
            f"story beats after {content_attempts} attempt(s): {last_error}"
        ) from last_error

    if beat_instructions:
        if instruction_review_attempts <= 0:
            raise ValueError(
                "Beat-instruction compliance requires at least one review attempt."
            )
        review_error = ""
        reviewed_beats = None
        for review_attempt in range(1, instruction_review_attempts + 1):
            review_messages = build_beat_instruction_review_messages(
                story,
                total_segments,
                beats,
                beat_instructions,
                review_error,
                subject_information,
            )
            verify_subjects_in_beat_messages(
                review_messages,
                subject_information,
            )
            reviewed_raw = llm_request(
                review_messages,
                response_format=response_format,
                history_metadata={
                    "purpose": "beat_instruction_review",
                    "attempt": review_attempt,
                    "total_segments": total_segments,
                    **(history_metadata or {}),
                },
                **BEAT_LLM_SAMPLING_PARAMETERS,
            )
            try:
                reviewed_beats = parse_generated_beats(
                    reviewed_raw,
                    total_segments,
                )
            except ValueError as error:
                review_error = str(error)
                if review_attempt < instruction_review_attempts:
                    print(
                        "LLM returned an invalid instruction-compliance edit; "
                        f"retrying ({review_attempt + 1}/"
                        f"{instruction_review_attempts}): {error}"
                    )
                continue
            compliance_issues = validate_generated_beat_instructions(
                reviewed_beats,
                beat_instructions,
            )
            if compliance_issues:
                review_error = " ".join(compliance_issues)
                reviewed_beats = None
                if review_attempt < instruction_review_attempts:
                    print(
                        "LLM beat list did not satisfy explicit beat_instructions; "
                        f"retrying ({review_attempt + 1}/"
                        f"{instruction_review_attempts}): {review_error}"
                    )
                continue
            beats = reviewed_beats
            break
        if reviewed_beats is None:
            raise RuntimeError(
                "LM Studio could not return a structurally valid beat list "
                "during the instruction-compliance review: "
                f"{review_error}"
            )

    print_generated_beats(beats)
    save_generated_beats(beats, path, lora_directive=lora_directive)
    print(f"Generated {len(beats)} story beats and saved them to {path}.")
    return load_beats(path)


def load_or_generate_beats(
    path,
    story,
    total_segments,
    llm_request=None,
    history_metadata=None,
    beat_instructions="",
    subject_information="",
):
    raw = load_text_file(path, required=True)
    beats, lora_directive = parse_beats_content(raw)
    if beats:
        return beats
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
    return segment_number > 0 and segment_number % 3 == 0


def build_director_rules(
    total_length,
    segment_length,
    total_segments,
    subject_definitions,
    megapixels,
    beats_enabled=True
):
    subject_context = subject_definitions or "N/A"

    resolution_guidance = []
    if megapixels <= 0.4:
        resolution_guidance.append(
            "- Use mostly close-up camera shots so important subjects remain "
            "large and clear. Never use wide-angle shots that make subjects too small to see clearly."
        )
    if megapixels <= 0.3:
        resolution_guidance.append(
            "- Avoid a lot of Subject movement; keep camera motion and simultaneous "
            "action minimal."
        )
    resolution_text = "\n".join(resolution_guidance) or "- No special guidance."

    if beats_enabled:
        role_description = (
            "from a supplied creative brief and an authoritative ordered "
            "story-beat checklist"
        )
        beat_rules = """
AUTHORITY ORDER
1. BEAT STATE controls ordered plot progression and completion reporting.
2. AUTHORITATIVE OPENING STATE controls current physical and visual state.
3. SUBJECT REGISTRY controls immutable identity and Picture mappings.
4. RECENT GENERATED SEGMENTS are secondary context for dialogue and cinematic flow.
5. SOURCE STORY / CREATIVE BRIEF supplies tone, intent, setting, and connective detail.
A lower-priority source must never override a higher-priority source.

BEAT EXECUTION CONTRACT
- On Segment 1, the ACTIVE beat must be B001 and must be completed in the opening segment.
- Never repeat any beat already completed through `completed_through`; DONE beats are finished and must not be reenacted.
- Begin visibly advancing the ACTIVE beat early in the segment.
- A beat is complete only when every observable event it requires has visibly occurred.
- Beginning, anticipating, implying, mentioning, or reacting to a beat does not complete it.
- If the ACTIVE beat says to continue an already established action, the beat is
    complete once THIS segment visibly depicts one substantial new exchange or
    continuation satisfying that beat. The overall action does not need to end.
- Do not enact, preview, or create the distinctive event, creature, object,
  injury, transformation, or outcome of any ordered lookahead beat in this
  segment. Later-beat entities must not appear early merely as embellishment.
- Do not invent irreversible physical changes unless the ACTIVE beat explicitly
  requires them. Do not permanently destroy equipment, detach body parts, fuse
  subjects, create births/hatchings, introduce major lasting injuries, kill a
  character, or permanently alter wardrobe merely to make an action scene more
  dramatic.
- A structural body/topology change exists only if THIS segment visibly performs
  that change. Never jump directly to a detached, fused, suspended, missing, or
  transformed state without showing the action that caused it.
- `completed_beat_ids` contains only newly completed consecutive beats beginning with ACTIVE.
""".strip()
    else:
        role_description = "from a supplied creative brief"
        beat_rules = """
STORY PROGRESSION
- Direct the complete movie from SOURCE STORY / CREATIVE BRIEF.
- AUTHORITATIVE OPENING STATE controls current physical continuity.
- RECENT GENERATED SEGMENTS are secondary context only.
- Pace the story so the movie ends naturally on the final segment.
- Always return completed_beat_ids as an empty array because beat tracking is disabled.
""".strip()

    return f"""
You are directing an automatically generated movie {role_description}.

The movie is approximately {total_length:g} seconds long, divided into
{total_segments} sequential segments of approximately {segment_length:g} seconds.
Generate exactly ONE MiniMax H3 segment description at a time.

RESOLUTION GUIDANCE
{resolution_text}

{beat_rules}

CONTINUATION
- Segment 1 establishes the opening normally.
- Later segments continue immediately from the previous generated video.
- Do not recap the previous clip.
- Preserve established wardrobe, injuries, props, positions, and ongoing audio when visible/relevant.
- When an action or story beat changes a subject's wardrobe, explicitly describe
    the visible change and resulting concrete garments and colors. The resulting
    outfit becomes that subject's current wardrobe and replaces contradictory
    earlier wardrobe descriptions.
- When a subject has a persistent visible physical alteration such as a severed
    horn, missing limb, major wound, damaged equipment, or decapitation, explicitly
    preserve that alteration whenever the affected body area is visible.

SUBJECTS
Pictures 1-6 are persistent identity/body references only, not wardrobe records.
Written story/continuity overrides clothing visible in reference pictures.
Subjects established by generated video have no Picture mapping. Preserve their
registered names and stable <Subject N> IDs from <Video 1>; never invent a Picture
tag for them.

{subject_context}

Use the registered form `Character Name <Picture N>` for defined subjects.
For a registered video-only subject, use its canonical name without a Picture tag.
Do not invent Picture tags for undefined people or objects.
Python inserts subject_definitions separately; do not output subject_definitions.

SHOT AND TIMING
- Each segment contains exactly one shot: Segment N = [Shot N].
- Shot 1 begins with `[Shot 1]` followed by style, framing, and initial composition.
- Segments after Shot 1 begin with either `[Shot N] Camera continues from the previous shot...`
    or `[Shot N] Camera cuts to a new shot: ...`.
- The opening [Shot N] has no timestamp.
- Optional later event timestamps within the same shot use this clip's local timeline.
- Later timestamps use this clip's local timeline, are greater than 00:00.000, and remain before clip duration.
- Never use cumulative movie timestamps.
- If Shot N is divisible by 3, it MUST begin with the CUT form.
- On other later segments, use the continuation form ONLY when the opening
    composition can genuinely follow the previous final frame without an
    unexplained camera teleport, subject relocation, or reset. If the desired
    framing requires a materially different viewpoint, use the CUT form instead.
- On a required CUT segment, do not write any continuation opening or sentence
    such as `camera continues from the previous shot`; the shot must begin only
    with the cut form.
- A continuation opening must preserve the previous final camera/framing and
    subject layout until an explicit camera or subject movement changes them.
- Write camera motion as natural English within the shot, never as stacked labels.
- Use only Zoom In/Out, Push In/Pull Out, Pan Left/Right, Truck Left/Right,
  Tilt Up/Down, Pedestal Up/Down, Arc Shot, Tracking Shot, Static Shot,
  Shake Slightly/Strongly, POV, or Roll Clockwise/Counterclockwise.
- Add `with small/large amplitude` and `at slow/fast speed` only when meaningful.
- Camera movement is encouraged but not required; do not invent movement for its own sake.

DIALOGUE
- Never imply speech; write the exact spoken words.
- Format: Character Name <Picture N> (S1) says: <d>[English] Actual spoken words.</d>
- Use the registered speaker ID consistently when a defined subject speaks.
- Keep speaker IDs consistent with RECENT EXACT GENERATED SEGMENTS.
- Never use pronouns as the speaker name in the dialogue tag.
- Only the language tag and exact spoken words belong inside <d></d>.
- Put identity, action, delivery, and voice descriptions outside <d></d>.
- For voiceover use exactly `says in an off-screen voiceover` and immediately
  after </d> state that the corresponding on-screen character's lips remain
  completely closed.
- Put visible signs, labels, subtitles, banners, and neon text in English double quotes.
- Never end mid-dialogue.

LIGHTING
Do not repeatedly restate lighting. Mention it only when established initially or changed by an action.

EXAMPLE FORMATTING

detailed_description:
[Shot 1] Realistic cinematic live-action horror. The camera is a wide shot of the hospital. A nurse, Amy <Picture 1>, is sitting in a chair, working at a desk in a dingy, derelict hospital.
At 00:02.000, the camera pans left to reveal a dark hallway. The lighting is dim and flickering, casting eerie shadows on the walls. Amy <Picture 1> (S1) says: <d>[English] I can't believe this place is still open.</d> The sound of distant footsteps echoes through the hallway, followed by a low, ominous hum.
At 00:05.000, the camera zooms in on Amy <Picture 1>'s face, showing her fear and anxiety. The sound of a door creaking open is heard, followed by a sudden thud as something heavy falls to the ground.
At 00:08.000, Amy <Picture 1> (S1) says: <d>[English] Who's there?</d> The sound of a faint whisper is heard, followed by a loud crash as a chair is thrown across the room. The camera shakes slightly, adding to the tension and fear of the scene.


SOUND
overall_soundscape: Write 1-4 English sentences in one paragraph containing
only ambience, physical action sounds, and non-verbal human sounds. Do not
duplicate dialogue, singing, or music. Use N/A only for explicitly requested
complete silence.

non_diegetic_music: Use N/A when there is no audience-only score. Otherwise
write 1-3 English sentences about instrumentation, tempo, rhythm, and dynamics;
do not use abstract mood words or explain the score's emotional purpose.

OUTPUT
Return only the JSON fields required by the response schema. Do not add Markdown,
code fences, field labels inside field values, alignment instructions, or
subject_definitions.
""".strip()


def get_detailed_description(llm_result, default=""):
    """Read the renamed description field while accepting old checkpoints."""
    if not isinstance(llm_result, dict):
        return default
    value = llm_result.get("detailed_description")
    if value is None:
        value = llm_result.get("integrated_multimodal_description", default)
    return value


def format_recent_segment(segment_number, llm_result):
    payload = {
        key: value
        for key, value in llm_result.items()
        if key != "completed_beat_ids"
    }
    if "detailed_description" not in payload:
        legacy_description = payload.pop(
            "integrated_multimodal_description",
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
    return cleaned.strip()


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
):
    registry = parse_subject_registry(subject_definitions)
    registry_text = json.dumps(registry, ensure_ascii=False, indent=2)
    state_text = json.dumps(
        continuity_state_for_registry(subject_definitions, committed_state),
        ensure_ascii=False,
        indent=2,
    )
    exact_prompts = "\n\n".join(
        format_recent_segment(number, result)
        for number, result in list(recent_results)[-RECENT_SEGMENTS_MAX:]
    )
    newest_description = ""
    if recent_results:
        newest_description = str(
            get_detailed_description(list(recent_results)[-1][1], "") or ""
        )
    final_moment_excerpt = extract_final_timeline_excerpt(newest_description)
    future_beat_texts = [
        str(item).strip() for item in (future_beat_texts or []) if str(item).strip()
    ]
    beat_scope_text = (
        f"ACTIVE BEAT: {str(active_beat_text or 'N/A').strip()}\n"
        "FUTURE BEATS (must not create persistent state yet):\n"
        + ("\n".join(f"- {item}" for item in future_beat_texts) or "- N/A")
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a continuity state updater. Return only one JSON object "
                "with fields version, environment, camera, subjects, ongoing_action, "
                "and ongoing_audio. Each subject record uses subject_id, name, "
                "picture_ids, picture_id, speaker_id, origin_segment, position, "
                "pose_action, topology, wardrobe, body_state, physical_condition, "
                "and held_props.\n\n"
                "Create an authoritative FINAL-FRAME continuity snapshot. The "
                "returned state describes the physical world at the END of the newest "
                "generated segment, not an accumulation of historical facts.\n\n"
                "For every field:\n"
                "- Replace an old value when the newest segment explicitly changes it.\n"
                "- When the newest segment contradicts an old value, use the newest "
                "final post-action value and remove the old state.\n"
                "- Preserve committed state only when the newest segment neither "
                "changes nor contradicts it. Never preserve mutually exclusive history.\n\n"
                "Camera, position, and pose_action are current end-of-segment state. "
                "The FINAL-MOMENT EXCERPT is highest authority for these fields. Use the "
                "latest explicitly established framing, position, or pose near "
                "the end of the newest segment; do not return camera as N/A merely "
                "because it did not move. NEVER put timestamps or a sequence of earlier "
                "actions into pose_action or ongoing_action. Convert an earlier action "
                "to its final static result only when that result is explicitly shown; "
                "otherwise preserve the committed value or use N/A.\n\n"
                "environment.persistent_state contains visible surroundings likely to "
                "remain: terrain, weather, damage, structures, smoke, debris, or "
                "persistent lighting. Do not put transient action, emotion, or mood there.\n\n"
                "topology records persistent structural connections between body parts "
                "or subjects, such as fused-to, attached-to, detached-from, or suspended-"
                "by relationships and the exact anatomical location of that connection. "
                "A topology change may be recorded ONLY when the newest segment explicitly "
                "shows the action that creates that exact change. Never infer a detached "
                "lower body because a detached face is mentioned, and never move a fusion "
                "from waistline to sternum unless the newest segment visibly performs that "
                "new fusion.\n\n"
                "body_state records persistent structural anatomy or body configuration: "
                "horns, wings, tails, limbs, head/body attachment, and missing or severed "
                "parts. Record explicitly visible structural features even when intact. "
                "Example: committed: two horns intact; newest: left horn is severed; "
                "updated body_state: left horn missing; right horn intact. Later, when "
                "the remaining horn is severed: updated body_state: both horns missing. "
                "Never retain contradictory history such as horns glowing after both horns "
                "are severed. Do not put structural anatomy in wardrobe.\n\n"
                "physical_condition is actual bodily status only: injury, wounds, bleeding, "
                "burns, exhaustion, unconsciousness, death, contamination, or similar. "
                "Do not use confidence, dominance, alertness, anger, determination, "
                "readiness, personality, or dramatic description; use N/A when no actual "
                "physical condition needs tracking.\n\n"
                "held_props is exact final possession. Preserve committed held_props when "
                "the newest segment does not establish a change. Use [] only when the "
                "final state explicitly establishes no tracked props are held.\n\n"
                "Track every visually persistent subject needed to continue the final "
                "frame, including creatures, people, vehicles, or other independently "
                "moving subjects introduced by the generated video without a Picture "
                "reference. A new video-only subject may be added only if it is visibly "
                "introduced in the newest segment itself and is not merely an event/entity "
                "reserved for a FUTURE BEAT. Add each such video-only subject under a concise stable name, "
                "assign the next unused positive subject_id, set picture_ids to [], "
                "picture_id to null, set origin_segment to the newest generated segment "
                "number, and describe its established visible appearance in body_state. "
                "Preserve an existing video-only subject, subject_id, and origin_segment "
                "across updates; do not create a duplicate under a synonym.\n\n"
                "When wardrobe changes, replace affected wardrobe fields with resulting "
                "concrete garments and colors, preserving that result until another visible "
                "change. Picture references establish identity/body appearance only and "
                "never restore wardrobe. SUBJECT REGISTRY owns immutable subject_id, name, "
                "picture_ids, picture_id, and speaker_id; never erase or modify them."
            ),
        },
        {
            "role": "user",
            "content": (
                "SUBJECT REGISTRY:\n"
                f"{registry_text}\n\n"
                "COMMITTED STATE:\n"
                f"{state_text}\n\n"
                "BEAT SCOPE:\n"
                f"{beat_scope_text}\n\n"
                "FINAL-MOMENT EXCERPT (highest authority for final pose/position/camera):\n"
                f"{final_moment_excerpt}\n\n"
                "LATEST GENERATED PROMPTS:\n"
                f"{exact_prompts}\n\n"
                "Return the complete updated structured state. Do not promote a future-beat "
                "event or entity into current continuity state."
            ),
        },
    ]


def _contains_structural_change(text):
    lowered = str(text or "").casefold()
    return any(stem in lowered for stem in _STRUCTURAL_CHANGE_STEMS)


def _candidate_anatomy_terms(text):
    lowered = str(text or "").casefold()
    return [term for term in _ANATOMY_PHRASES if term in lowered]


def _structural_change_has_evidence(subject_name, candidate_value, description):
    """Require the same structural action and body region in the newest prompt."""
    candidate = str(candidate_value or "").casefold()
    source = str(description or "").casefold()
    if not _contains_structural_change(candidate):
        return True

    # Require at least one structural-change stem from the candidate itself.
    candidate_stems = [stem for stem in _STRUCTURAL_CHANGE_STEMS if stem in candidate]
    if candidate_stems and not any(stem in source for stem in candidate_stems):
        return False

    anatomy_terms = _candidate_anatomy_terms(candidate)
    # Require every anatomical region named by the candidate structural state.
    # This prevents evidence about a detached face from licensing an invented
    # detached lower body, or a chest fusion from silently moving to the waist.
    if anatomy_terms and not all(term in source for term in anatomy_terms):
        return False

    # If the subject is named in the source, insist that the structural evidence
    # occurs reasonably near either the subject name or a possessive reference.
    name = str(subject_name or "").strip().casefold()
    if name and name in source and candidate_stems:
        evidence_positions = []
        for stem in candidate_stems:
            evidence_positions.extend(match.start() for match in re.finditer(re.escape(stem), source))
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


def normalize_structured_continuity_state(
    candidate,
    subject_definitions,
    committed_state=None,
    origin_segment=None,
    newest_description="",
    active_beat_text="",
    future_beat_texts=None,
):
    if not isinstance(candidate, dict):
        return None
    state = continuity_state_for_registry(subject_definitions, committed_state)
    id_to_name = {
        str(record.get("subject_id")): name
        for name, record in state["subjects"].items()
        if record.get("subject_id") is not None
    }

    def is_unknown_value(value):
        if isinstance(value, str):
            cleaned = sanitize_previous_state_value(value).strip()
            return cleaned == "" or cleaned.upper() == "N/A"
        if isinstance(value, (list, tuple, set)):
            if not value:
                return True
            return all(
                is_unknown_value(str(item))
                for item in value
            )
        return False

    def extract_implied_value(value):
        if not isinstance(value, str):
            return None
        cleaned = sanitize_previous_state_value(value).strip()
        if not cleaned:
            return None
        if cleaned.upper() == "N/A":
            return None
        match = re.match(
            r"(?i)^N/A\s*(?:\(|\[|:|-)?\s*(?:implied|inferred|assumed|likely|possibly)?\s*(.+?)\s*(?:\)|\]|:|-)?$",
            cleaned,
        )
        if match:
            inferred = match.group(1).strip(" .;:,-")
            if inferred and inferred.upper() != "N/A":
                return inferred
        if cleaned.upper().startswith("N/A"):
            tail = cleaned[3:].strip(" :;-()[]")
            if tail and tail.upper() != "N/A":
                return tail
        return None

    def concrete_value(value, field_name=""):
        if not isinstance(value, str):
            return None
        raw = sanitize_previous_state_value(value).strip()
        if not raw or raw.upper() == "N/A":
            return None
        # A final-frame snapshot must never contain local-timeline history.
        # Reject timestamped action fields outright instead of replaying them
        # as the next segment's opening action.
        if field_name in {"pose_action", "ongoing_action"} and _CONTINUITY_TIMESTAMP_RE.search(raw):
            print(
                f"WARNING: Ignoring historical timestamped continuity field "
                f"{field_name}: {raw!r}"
            )
            return None
        cleaned = _scrub_snapshot_text(raw, field_name)
        if not cleaned or cleaned.upper() == "N/A":
            return None
        implied = extract_implied_value(cleaned)
        if implied is not None:
            return implied
        return cleaned

    def resolve_subject_name(raw_name):
        if raw_name in state["subjects"]:
            return raw_name
        if isinstance(raw_name, str) and raw_name.isdigit():
            mapped = id_to_name.get(raw_name)
            if mapped and mapped in state["subjects"]:
                return mapped
        return None

    def update_value(target, key, candidate_value, is_implied=False):
        if candidate_value is None:
            return
        if not is_implied or is_unknown_value(target.get(key)):
            target[key] = candidate_value

    for field in ("camera", "ongoing_action", "ongoing_audio"):
        if isinstance(candidate.get(field), str):
            value = concrete_value(candidate[field], field)
            if value is not None:
                update_value(
                    state,
                    field,
                    value,
                    extract_implied_value(candidate[field]) is not None,
                )
    environment = candidate.get("environment")
    if isinstance(environment, dict):
        for field in ("location", "persistent_state"):
            if isinstance(environment.get(field), str):
                value = concrete_value(environment[field], f"environment.{field}")
                if value is not None:
                    update_value(
                        state["environment"],
                        field,
                        value,
                        extract_implied_value(environment[field]) is not None,
                    )
    candidate_subjects = candidate.get("subjects")
    if isinstance(candidate_subjects, dict):
        for raw_name, record in candidate_subjects.items():
            if not isinstance(record, dict):
                continue
            name = resolve_subject_name(raw_name)
            if name is None:
                proposed_name = str(record.get("name", raw_name)).strip()
                if not proposed_name or proposed_name.isdigit():
                    continue
                existing_name = next(
                    (
                        current_name
                        for current_name in state["subjects"]
                        if current_name.lower() == proposed_name.lower()
                    ),
                    None,
                )
                if existing_name is not None:
                    name = existing_name
                else:
                    # A durable video-only subject must actually be visible in
                    # this segment. Do not let the state updater manufacture a
                    # subject from a future beat or from its own extrapolation.
                    if proposed_name.casefold() not in str(newest_description or "").casefold():
                        print(
                            "WARNING: Ignoring unevidenced video-only subject "
                            f"{proposed_name!r}; its name does not appear in the newest segment."
                        )
                        continue
                    if _future_subject_name_is_reserved(
                        proposed_name, active_beat_text, future_beat_texts
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
                    if (
                        proposed_id is None
                        or proposed_id <= 0
                        or proposed_id in used_ids
                    ):
                        proposed_id = max(used_ids, default=0) + 1
                    try:
                        created_in_segment = int(
                            record.get("origin_segment", origin_segment)
                        )
                    except (TypeError, ValueError):
                        created_in_segment = origin_segment
                    name = proposed_name
                    state["subjects"][name] = new_subject_continuity_record({
                        "subject_id": proposed_id,
                        "name": name,
                        "picture_ids": [],
                        "picture_id": None,
                        "speaker_id": None,
                        "origin_segment": created_in_segment,
                    })
                    id_to_name[str(proposed_id)] = name
            target = state["subjects"][name]
            for field in (
                "position",
                "pose_action",
                "topology",
                "body_state",
                "physical_condition",
            ):
                if isinstance(record.get(field), str):
                    value = concrete_value(record[field], field)
                    if value is None:
                        continue
                    if (
                        CONTINUITY_REJECT_UNEVIDENCED_STRUCTURAL_CHANGES
                        and field in {"topology", "body_state"}
                        and value != target.get(field)
                        and not _structural_change_has_evidence(
                            name, value, newest_description
                        )
                    ):
                        print(
                            "WARNING: Ignoring unevidenced structural continuity "
                            f"change for {name} ({field}): {value!r}"
                        )
                        continue
                    update_value(
                        target,
                        field,
                        value,
                        extract_implied_value(record[field]) is not None,
                    )
            wardrobe = record.get("wardrobe")
            if isinstance(wardrobe, dict):
                for garment in target["wardrobe"]:
                    if isinstance(wardrobe.get(garment), str):
                        value = concrete_value(wardrobe[garment], f"wardrobe.{garment}")
                        if value is not None:
                            update_value(
                                target["wardrobe"],
                                garment,
                                value,
                                extract_implied_value(wardrobe[garment]) is not None,
                            )
            if isinstance(record.get("held_props"), list):
                props = []
                for prop in record["held_props"]:
                    if not isinstance(prop, str):
                        prop = str(prop)
                    cleaned = sanitize_previous_state_value(prop).strip()
                    inferred = extract_implied_value(cleaned)
                    if inferred is not None:
                        props.append(inferred)
                        continue
                    if cleaned and cleaned.upper() != "N/A":
                        props.append(cleaned)
                if props:
                    target["held_props"] = props
                elif not target.get("held_props"):
                    target["held_props"] = []
                else:
                    release_pattern = re.compile(
                        rf"(?is)\b{re.escape(name)}\b.{{0,180}}\b"
                        r"(?:drops?|releases?|lets? go|sets? down|puts? down|throws?)\b"
                    )
                    if release_pattern.search(str(newest_description or "")):
                        target["held_props"] = []
                    else:
                        print(
                            f"WARNING: Preserving {name}'s held props because "
                            "the newest segment does not explicitly release them."
                        )
    state["version"] = CONTINUITY_STATE_VERSION
    return scrub_continuity_state(state)


def request_structured_continuity_state(
    recent_results,
    committed_state,
    subject_definitions,
    llm_request=None,
    history_metadata=None,
    active_beat_text="",
    future_beat_texts=None,
):
    if llm_request is None:
        llm_request = ask_llm
    messages = build_structured_continuity_messages(
        recent_results,
        committed_state,
        subject_definitions,
        active_beat_text=active_beat_text,
        future_beat_texts=future_beat_texts,
    )
    candidate = llm_request(
        messages,
        response_format=None,
        **({"history_metadata": history_metadata} if history_metadata else {}),
    )
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError:
            return None
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
    return normalize_structured_continuity_state(
        candidate,
        subject_definitions,
        committed_state,
        origin_segment=origin_segment,
        newest_description=newest_description,
        active_beat_text=active_beat_text,
        future_beat_texts=future_beat_texts,
    )


def build_segment_request(
    segment,
    total_segments,
    segment_length,
    total_length,
    beats,
    completed_beat_ids
):
    elapsed = (segment - 1) * segment_length
    current_duration = min(segment_length, total_length - elapsed)
    next_beat_id = get_next_beat_id(beats, completed_beat_ids)

    if not beats:
        beat_focus = (
            "Beat tracking is disabled. Develop the source story naturally "
            "and return completed_beat_ids as an empty array."
        )

    elif next_beat_id is None:
        beat_focus = (
            "All required beats are complete. Use the remaining runtime to "
            "resolve the story naturally without repeating completed events."
        )

    else:
        beat_text = beats[next_beat_id - 1]
        deadline = get_beat_deadline_segment(
            next_beat_id,
            beats,
            total_segments
        )

        if segment >= deadline:
            deadline_text = (
                f"B{next_beat_id:03d} has reached its pacing deadline and MUST "
                "be visibly completed in this segment. Show every observable "
                "action required by the beat and its unmistakable outcome before "
                "the shot ends. Report this beat in completed_beat_ids only if "
                "the generated description actually shows all of those required "
                "events occurring."
            )
        else:
            deadline_text = (
                f"Actively attempt to complete B{next_beat_id:03d} in THIS "
                f"segment. Segment {deadline} is only its absolute latest "
                "completion point, not a reason to postpone it. If all required "
                "observable events fit naturally within this segment, complete "
                "the beat now. Report it in completed_beat_ids only if the "
                "generated description actually shows the beat fully occurring."
            )

        specific_directives = []

        if re.search(
            r"(?i)\b(?:talk\w*|conversation|discuss\w*|dialogue|exchange|"
            r"asks?|says?)\b",
            beat_text
        ):
            specific_directives.append(
                "If the beat requires speech or conversation, write the required "
                "audible exchange with exact attributed dialogue. Implied speech, "
                "reaction to unheard dialogue, or merely preparing to speak does "
                "not satisfy the beat."
            )

        if re.search(
            r"(?i)\b(?:run|flee|abduct|lift|seize|fight|enter|leave|arrive|"
            r"appear|fly|drive|fall|open|close|take|give|show)\w*\b",
            beat_text
        ):
            specific_directives.append(
                "If the beat requires a physical event, show that action clearly "
                "on screen. Narration, off-screen action, anticipation, implication, "
                "or a reaction without showing the required event does not satisfy "
                "the beat."
            )

        specific_text = " ".join(specific_directives)

        beat_focus = (
            f"PRIMARY BEAT EXECUTION: ACTIVE beat "
            f"B{next_beat_id:03d}: {beat_text} "
            "Begin visibly advancing this beat early in the segment and make it "
            "the primary story event. Devote enough of the clip to clearly enact "
            f"its required observable events. {deadline_text} "
            f"{specific_text} "
            "Do not substitute atmosphere, recap, unrelated movement, passive "
            "observation, or setup for actual beat progress. Do not substantially "
            "enact later ordered beats before this beat has visibly completed."
        )

    if segment == 1:
        continuation = (
            "This is the first generated clip. Begin with the story's opening "
            "scene and opening clothing. There is no previous-video context."
        )
    else:
        continuation = (
            "The complete preceding generated video is supplied directly to "
            "MiniMax as continuation context. Continue immediately from its "
            "established ending state and do not replay or recap that ending."
        )

    return (
        f"Create segment {segment} of {total_segments}. This is [Shot {segment}]. "
        f"The new clip is {current_duration:g} seconds long and its local timeline "
        f"begins at 00:00.000. {continuation} Pictures 1 through 6 are Ref2V "
        f"subject identity references only. {beat_focus}"
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
):
    beat_state = build_bounded_beat_state(
        beats,
        completed_beat_ids,
        current_segment,
        total_segments,
    )
    if beats:
        if beat_state["active_beat"] is None:
            beat_section = "BEAT STATE\n\nAll beats are complete.\n\n"
        else:
            completed_through = beat_state["completed_through"] or 0
            beat_section = (
                "BEAT STATE\n\n"
                f"completed_through: B{completed_through:03d}\n"
                "active_beat:\n"
                f"B{beat_state['active_beat']['id']:03d}: "
                f"{beat_state['active_beat']['text']}\n"
                "ordered_lookahead:\n"
                + "\n".join(
                    f"B{item['id']:03d}: {item['text']}"
                    for item in beat_state["ordered_lookahead"]
                )
                +
                f"\n\nbeats_completed: {beat_state['beats_completed']}"
                f"\nbeats_remaining: {beat_state['beats_remaining']}"
                f"\nactive_deadline_segment: "
                f"{beat_state['active_deadline_segment'] or 'N/A'}\n\n"
            )
    else:
        beat_section = ""
    current_request = build_segment_request(
        current_segment,
        total_segments,
        segment_length,
        total_length,
        beats,
        completed_beat_ids
    )

    recent_results = recent_results[-RECENT_SEGMENTS_MAX:]

    def make_user_content(recent_items):
        if recent_items:
            recent_text = "\n\n".join(
                format_recent_segment(number, result)
                for number, result in recent_items
            )
        else:
            recent_text = "N/A"

        if continuity_summary:
            summary_section = (
                continuity_summary
                if continuity_summary.lstrip().startswith(
                    "AUTHORITATIVE OPENING STATE"
                )
                else f"AUTHORITATIVE OPENING STATE\n\n{continuity_summary}"
            ) + "\n\n"
        else:
            summary_section = """
AUTHORITATIVE OPENING STATE

This is the first segment and has no preceding successfully rendered video.
There is no prior physical state to preserve.


"""

        story_context = build_story_context(
            story,
            active_beat=(
                beat_state["active_beat"]["text"]
                if beat_state["active_beat"] else None
            ),
            lookahead_beats=[
                item["text"] for item in beat_state["ordered_lookahead"]
            ],
            subject_definitions=subject_definitions,
        )
        subject_registry = format_subject_registry(subject_definitions)
        return f"""
    {beat_section}{summary_section}SUBJECT REGISTRY

    The registry below is authoritative for character identity and Picture mapping.
    Reference pictures establish identity and body appearance, not current wardrobe.

    {subject_registry}

    SOURCE STORY / CREATIVE BRIEF

    This section supplies creative intent, tone, setting, dialogue ideas, and
    connective detail. It cannot override BEAT STATE, AUTHORITATIVE OPENING STATE,
    or SUBJECT REGISTRY.

--- STORY START ---
    {story_context}
--- STORY END ---


RECENT GENERATED SEGMENT — SECONDARY CONTEXT ONLY

This material may help with immediate dialogue and cinematic flow.
RECENT GENERATED SEGMENT is secondary context only.
If it conflicts with AUTHORITATIVE OPENING STATE, always use AUTHORITATIVE
OPENING STATE. It must not override BEAT STATE or SUBJECT REGISTRY.

{recent_text}


CURRENT TASK

{current_request}
""".strip()

    selected_recent = []
    for item in reversed(recent_results):
        tentative = [item] + selected_recent
        tentative_messages = [
            {"role": "system", "content": director_rules},
            {"role": "user", "content": make_user_content(tentative)}
        ]
        if estimate_message_tokens(tentative_messages) <= LLM_INPUT_TOKEN_BUDGET:
            selected_recent = tentative

    messages = [
        {"role": "system", "content": director_rules},
        {"role": "user", "content": make_user_content(selected_recent)}
    ]

    estimated = estimate_message_tokens(messages)
    if estimated > LLM_INPUT_TOKEN_BUDGET:
        raise RuntimeError(
            f"Fixed LLM context is too large ({estimated} estimated tokens; "
            f"budget {LLM_INPUT_TOKEN_BUDGET}). Shorten story.txt, beats.txt, "
            "or subjects.txt."
        )

    return messages, estimated, len(selected_recent)


# ============================================================
# MINISTRAL FORMAT / VALIDATION
# ============================================================

def story_requests_complete_silence(story):
    normalized = " ".join((story or "").lower().split())
    silence_phrases = (
        "complete silence",
        "completely silent",
        "entirely silent",
        "no sound throughout",
        "without any sound"
    )
    return any(phrase in normalized for phrase in silence_phrases)


def build_ministral_context(
    segment_number,
    segment_duration,
    total_segments,
    beats,
    completed_beat_ids,
    subject_definitions,
    story,
    recent_results=None,
    opening_state="",
):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    beat_state = build_bounded_beat_state(
        beats,
        completed,
        segment_number,
        total_segments,
    )
    active_beat = beat_state["active_beat"]
    current_beat_text = active_beat["text"] if active_beat else None
    later_beat_texts = [
        item["text"] for item in beat_state["ordered_lookahead"]
    ]
    deadline_required = bool(
        beat_state["active_deadline_segment"] is not None
        and segment_number >= beat_state["active_deadline_segment"]
    )

    return {
        "segment_number": segment_number,
        "segment_duration": segment_duration,
        "subject_definitions": subject_definitions or "",
        "completed_beat_ids": sorted(completed),
        "next_beat_id": active_beat["id"] if active_beat else None,
        "current_beat_text": current_beat_text,
        "later_beat_texts": later_beat_texts,
        "beat_state": beat_state,
        "beat_deadline_required": deadline_required,
        "allow_silence": story_requests_complete_silence(story),
        "hard_cut_required": is_hard_cut_segment(segment_number),
        "opening_state": str(opening_state or ""),
        "recent_descriptions": [
            str(get_detailed_description(result))
            for _, result in (recent_results or [])
            if isinstance(result, dict)
        ]
    }


def build_best_effort_ministral_result(raw_result):
    if isinstance(raw_result, dict):
        integrated = get_detailed_description(raw_result, None)
        soundscape = raw_result.get("overall_soundscape")
        music = raw_result.get("non_diegetic_music")
        completed = raw_result.get("completed_beat_ids", [])
        if not isinstance(integrated, str):
            integrated = json.dumps(raw_result, ensure_ascii=False)
        if not isinstance(soundscape, str):
            soundscape = "N/A"
        if not isinstance(music, str):
            music = "N/A"
        if not isinstance(completed, list):
            completed = []
    else:
        integrated = str(raw_result)
        soundscape = "N/A"
        music = "N/A"
        completed = []
    return {
        "detailed_description": integrated,
        "overall_soundscape": soundscape,
        "non_diegetic_music": music,
        "completed_beat_ids": completed
    }


def format_correction_request(formatted_result, issues):
    issue_text = "\n".join(
        f"{index}. {issue}"
        for index, issue in enumerate(issues, start=1)
    )
    return f"""
Generate a corrected response for the original director task included above.

Python already applied every deterministic repair it could. Resolve these
remaining content problems:

{issue_text}

PREVIOUS BEST-EFFORT JSON
{json.dumps(formatted_result, ensure_ascii=False, indent=2)}

Return the complete corrected JSON object using the required response schema.
Preserve valid details and exact dialogue unless a listed problem requires a
content change. Do not add commentary or Markdown.
""".strip()


def build_stateless_correction_messages(messages, formatted_result, issues):
    normalized = normalize_lm_studio_messages(messages)
    system_messages = [
        message for message in normalized if message["role"] == "system"
    ]
    original_content = "\n\n".join(
        message["content"]
        for message in normalized
        if message["role"] != "system"
    )
    correction_content = (
        original_content
        + "\n\n"
        + format_correction_request(formatted_result, issues)
    )
    return system_messages[:1] + [
        {"role": "user", "content": correction_content}
    ]


SEGMENT_SEMANTIC_AUDIT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "segment_semantic_audit",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "active_beat_satisfied": {"type": "boolean"},
                "future_beat_leakage": {"type": "boolean"},
                "opening_state_conflict": {"type": "boolean"},
                "unrequired_irreversible_change": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                },
            },
            "required": [
                "active_beat_satisfied",
                "future_beat_leakage",
                "opening_state_conflict",
                "unrequired_irreversible_change",
                "issues",
            ],
            "additionalProperties": False,
        },
    },
}


def request_segment_semantic_audit(
    formatted_result,
    context,
    llm_request=None,
    history_metadata=None,
):
    """Audit plot scope and physical continuity before a prompt reaches H3."""
    if not SEMANTIC_SEGMENT_AUDIT:
        return None
    if llm_request is None:
        llm_request = ask_llm

    active_id = context.get("next_beat_id")
    active_text = context.get("current_beat_text") or "N/A"
    future_beats = context.get("later_beat_texts") or []
    opening_state = context.get("opening_state") or "N/A"
    description = str(get_detailed_description(formatted_result, "") or "")
    completed = formatted_result.get("completed_beat_ids", [])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict semantic continuity auditor for one generated "
                "video prompt. Judge only what the candidate description explicitly "
                "shows. Do not rewrite it. Return only the requested JSON.\n\n"
                "active_beat_satisfied is true only when every observable event in "
                "the ACTIVE BEAT is explicitly performed and its required result is "
                "visible in this candidate.\n"
                "future_beat_leakage is true if the candidate visibly performs, "
                "creates, births, hatches, reveals, transforms into, destroys, or "
                "otherwise materially enacts a distinctive event/entity reserved for "
                "any FUTURE BEAT. Mere neutral setup that does not enact that event is "
                "not leakage.\n"
                "opening_state_conflict is true if the candidate begins from a body "
                "configuration, attachment, position, wardrobe state, or physical "
                "condition incompatible with the AUTHORITATIVE OPENING STATE without "
                "first visibly performing the change. A camera cut may change framing "
                "but cannot teleport subjects or rewrite anatomy.\n"
                "unrequired_irreversible_change is true if the candidate invents a "
                "persistent fusion, detachment, amputation, birth/hatching, death, "
                "major transformation, or similarly irreversible state that the ACTIVE "
                "BEAT does not require.\n"
                "Be literal and conservative. A different anatomical region is not "
                "evidence for the requested one."
            ),
        },
        {
            "role": "user",
            "content": (
                f"ACTIVE BEAT ID: {active_id or 'N/A'}\n"
                f"ACTIVE BEAT: {active_text}\n\n"
                "FUTURE BEATS:\n"
                + ("\n".join(f"- {beat}" for beat in future_beats) or "- N/A")
                + "\n\nAUTHORITATIVE OPENING STATE:\n"
                + opening_state
                + "\n\nCANDIDATE DETAILED DESCRIPTION:\n"
                + description
                + "\n\nCANDIDATE COMPLETED BEAT IDS:\n"
                + json.dumps(completed)
            ),
        },
    ]
    try:
        metadata = dict(history_metadata or {})
        metadata["purpose"] = "segment_semantic_audit"
        raw = llm_request(
            messages,
            response_format=SEGMENT_SEMANTIC_AUDIT_RESPONSE_FORMAT,
            history_metadata=metadata,
            temperature=0.1,
        )
        if isinstance(raw, str):
            raw = parse_llm_json_content(raw)
        if not isinstance(raw, dict):
            raise ValueError("semantic audit returned non-object content")
        return raw
    except Exception as error:
        print(f"WARNING: Semantic segment audit failed; continuing without it: {error}")
        return None


def semantic_audit_issues(audit, formatted_result, context):
    if not isinstance(audit, dict):
        return []
    issues = []
    active_id = context.get("next_beat_id")
    reported = set()
    for raw_id in formatted_result.get("completed_beat_ids", []) or []:
        try:
            reported.add(int(raw_id))
        except (TypeError, ValueError):
            pass

    if audit.get("future_beat_leakage"):
        issues.append(
            "The candidate substantially enacts a distinctive future beat. Remove "
            "the future-beat event/entity and keep this segment scoped to the ACTIVE beat."
        )
    if audit.get("opening_state_conflict"):
        issues.append(
            "The candidate contradicts the AUTHORITATIVE OPENING STATE without visibly "
            "performing the physical transition. Begin from the committed final state."
        )
    if audit.get("unrequired_irreversible_change"):
        issues.append(
            "The candidate invents an irreversible physical/topology change not required "
            "by the ACTIVE beat. Remove that change."
        )
    if active_id is not None and (
        active_id in reported or context.get("beat_deadline_required")
    ) and not audit.get("active_beat_satisfied", False):
        issues.append(
            f"B{int(active_id):03d} is reported/required complete, but the candidate does "
            "not explicitly perform every observable event in that beat."
        )
    for detail in audit.get("issues", []) or []:
        detail = str(detail).strip()
        if detail and detail not in issues:
            issues.append(detail)
    return issues


def strip_unverified_beat_completion(formatted_result, audit, context):
    """Never advance beat state when the semantic auditor says it was not shown."""
    if not isinstance(audit, dict) or audit.get("active_beat_satisfied", True):
        return formatted_result
    active_id = context.get("next_beat_id")
    if active_id is None:
        return formatted_result
    result = dict(formatted_result)
    result["completed_beat_ids"] = [
        raw_id
        for raw_id in result.get("completed_beat_ids", []) or []
        if str(raw_id) != str(active_id)
    ]
    return result


def request_valid_ministral_prompt(
    messages,
    context,
    llm_request=None,
    max_content_corrections=MINISTRAL_CONTENT_CORRECTION_ATTEMPTS,
    history_metadata=None,
):
    if llm_request is None:
        llm_request = ask_llm

    last_audit = None

    def format_and_validate(raw_value):
        try:
            formatted_value = format_ministral_prompt(raw_value, context)
        except Exception as error:
            return (
                build_best_effort_ministral_result(raw_value),
                [f"Response could not be parsed locally: {error}"]
            )
        try:
            validation_issues = validate_ministral_prompt(
                formatted_value,
                context
            )
        except Exception as error:
            validation_issues = [f"Local prompt validation failed: {error}"]
        return formatted_value, validation_issues

    def add_semantic_issues(formatted_value, validation_issues, attempt_label):
        nonlocal last_audit
        if validation_issues or not SEMANTIC_SEGMENT_AUDIT:
            return validation_issues
        audit_metadata = dict(history_metadata or {})
        audit_metadata["audit_attempt"] = attempt_label
        last_audit = request_segment_semantic_audit(
            formatted_value,
            context,
            llm_request=llm_request,
            history_metadata=audit_metadata,
        )
        return validation_issues + semantic_audit_issues(
            last_audit,
            formatted_value,
            context,
        )

    request_kwargs = (
        {"history_metadata": history_metadata}
        if history_metadata else {}
    )
    raw_result = llm_request(messages, **request_kwargs)
    formatted_result, issues = format_and_validate(raw_result)
    issues = add_semantic_issues(formatted_result, issues, "initial")
    if not issues:
        return strip_unverified_beat_completion(
            formatted_result, last_audit, context
        )

    for correction_number in range(1, max_content_corrections + 1):
        print(
            "Python/semantic validation left unresolved content issue(s); "
            f"requesting Ministral correction {correction_number}/"
            f"{max_content_corrections}."
        )
        correction_messages = build_stateless_correction_messages(
            messages,
            formatted_result,
            issues
        )
        try:
            correction_kwargs = dict(request_kwargs)
            if correction_kwargs:
                correction_kwargs["history_metadata"] = {
                    **correction_kwargs["history_metadata"],
                    "purpose": "director_correction",
                    "attempt": correction_number,
                }
            corrected_raw = llm_request(correction_messages, **correction_kwargs)
        except Exception as error:
            print(
                "WARNING: Ministral correction request failed; using the "
                f"existing best-effort prompt instead: {error}"
            )
            return strip_unverified_beat_completion(
                formatted_result, last_audit, context
            )
        formatted_result, issues = format_and_validate(corrected_raw)
        issues = add_semantic_issues(
            formatted_result,
            issues,
            f"correction_{correction_number}",
        )
        if not issues:
            return strip_unverified_beat_completion(
                formatted_result, last_audit, context
            )

    print(
        "WARNING: Prompt still has unresolved issue(s) after all Ministral "
        "corrections; using the latest best-effort prompt:"
    )
    for issue in issues:
        print(f"  - {issue}")
    return strip_unverified_beat_completion(
        formatted_result, last_audit, context
    )


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
    r"ripped|stained|muddy|dusty|bloody|bloodied|blood-stained|damaged|"
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
    subjects = [
        (subject_number, subject_name)
        for subject_number, subject_name in subjects
        if re.search(
            rf"(?i)<Subject\s+{subject_number}>|\b{re.escape(subject_name)}\b",
            current_description
        )
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
                f"{subject_name} " + " ".join(
                    f"<Picture {picture}>"
                    for picture in registry[subject_number].get(
                        "picture_ids",
                        [registry[subject_number]["picture_id"]],
                    )
                ) + " "
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
    state = continuity_state_for_registry(subject_definitions, continuity_state)
    clauses = []
    for subject_id, subject in registry.items():
        picture_ids = subject.get("picture_ids", [subject["picture_id"]])
        if not re.search(
            rf"(?i)(?:" + "|".join(
                rf"<Picture\s+{picture}>" for picture in picture_ids
            ) + r")|"
            rf"<Subject\s+{subject_id}>|"
            rf"\b{re.escape(subject['name'])}\b",
            current_description,
        ):
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
            f"{subject['name']} " + " ".join(
                f"<Picture {picture}>" for picture in picture_ids
            ) + f" is at {location}, "
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


def build_h3_prompt(
    llm_result,
    subject_definitions,
    hard_cut_clothing_reiteration="",
    previous_state="",
    segment_number=None,
    ff=False,
):
    description = get_detailed_description(llm_result, None)
    if not isinstance(description, str):
        raise RuntimeError(
            "LLM response is missing text field 'detailed_description'."
        )
    for field in ("overall_soundscape", "non_diegetic_music"):
        if not isinstance(llm_result.get(field), str):
            raise RuntimeError(f"LLM response is missing text field '{field}'.")

    integrated = strip_field_prefix(
        description,
        "detailed_description"
    )
    soundscape = strip_field_prefix(
        llm_result["overall_soundscape"],
        "overall_soundscape"
    )
    music = strip_field_prefix(
        llm_result["non_diegetic_music"],
        "non_diegetic_music"
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

    subject_text = subject_definitions.strip() or "N/A"
    if ff and segment_number == 1:
        subject_text += (
            "\n\n<Picture 1> is the opening-frame reference for the target video.\n\n"
            "At 00:00.000, the target video should begin by reproducing <Picture 1> "
            "as closely as possible. Preserve the same camera position, framing, "
            "composition, subject pose, facial expression, clothing, lighting, "
            "environment, object positions, and spatial relationships shown in "
            "<Picture 1>."
        )
    is_reference_continuation = (
        isinstance(previous_state, str)
        and previous_state.lstrip().startswith("<Video 1>")
        and "retention_analysis:" in previous_state
    )
    previous_state_text = (
        None
        if segment_number == 1
        else (
            previous_state
            if isinstance(previous_state, str)
            and (
                previous_state.lstrip().startswith(
                    "AUTHORITATIVE OPENING STATE"
                )
                or is_reference_continuation
            )
            else normalize_previous_state(previous_state)
        )
    )
    if (
        hard_cut_clothing_reiteration
        and previous_state_text is not None
        and not is_reference_continuation
    ):
        previous_state_text += "\n" + hard_cut_clothing_reiteration
    previous_state_section = (
        f"{previous_state_text}\n\n"
        if previous_state_text is not None else ""
    )
    return (
        f"subject_definitions: {subject_text}\n\n"
        + previous_state_section
        + f"detailed_description: {integrated}\n\n"
        + f"overall_soundscape: {soundscape}\n\n"
        + f"non_diegetic_music: {music}"
    )


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


def render_segment_with_retries(
    segment,
    current_duration,
    requested_megapixels,
    h3_prompt,
    previous_video_path,
    steps,
    loras=None,
    lora_override=None,
):
    """Render one segment, retrying only recoverable ComfyUI failures."""
    if lora_override is not None:
        if loras:
            raise ValueError("Pass loras or lora_override, not both.")
        loras = [lora_override]
    loras = normalize_lora_list(loras)
    for retry_number in range(COMFY_RENDER_RETRIES + 1):
        current_megapixels = (
            max(
                0.01,
                requested_megapixels
                - retry_number * COMFY_RETRY_MEGAPIXEL_STEP
            )
            if segment == 1
            else requested_megapixels
        )
        if retry_number:
            #free_vram()
            if segment == 1:
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
        else:
            workflow = prepare_append_workflow(
                current_duration,
                h3_prompt,
                previous_video_path,
                segment,
                steps,
                **lora_kwargs,
            )

        try:
            prompt_id = queue_workflow(workflow)
            print(f"ComfyUI prompt ID: {prompt_id}")
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


def prepare_append_workflow(
    duration,
    h3_prompt,
    previous_video_path,
    segment_number,
    steps=6,
    loras=None,
    lora_override=None,
):
    if lora_override is not None:
        if loras:
            raise ValueError("Pass loras or lora_override, not both.")
        loras = [lora_override]
    workflow = load_workflow(APPEND_WORKFLOW_FILE)
    label = f"append workflow '{APPEND_WORKFLOW_FILE}'"
    validate_workflow(workflow, label, is_append=True)

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
        workflow, LOAD_VIDEO_NODE_NAME, "video",
        os.path.abspath(previous_video_path),
        label, "VHS_LoadVideoPath"
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
            output_path
        ],
        check=True
    )


def stitch_videos(video_paths):
    if not video_paths:
        raise RuntimeError("No generated videos are available to stitch.")

    os.makedirs(VIDEO_OUTPUT, exist_ok=True)
    stitch_paths = []

    for index, video_path in enumerate(video_paths):
        video_path = os.path.abspath(video_path)
        if index == 0:
            stitch_paths.append(video_path)
            continue

        trimmed_path = os.path.join(
            os.path.dirname(video_path),
            f"trimmed_{os.path.basename(video_path)}"
        )
        print(
            f"Trimming first {TRIM_FRAMES_AFTER_FIRST} frames from "
            f"segment {index + 1}."
        )
        trim_video_start(
            video_path,
            trimmed_path,
            TRIM_SECONDS_AFTER_FIRST
        )
        stitch_paths.append(trimmed_path)

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

    print(f"Stitching complete: {FINAL_VIDEO}")


# ============================================================
# MAIN
# ============================================================

def _run_main(summary_executor):
    args = parse_args()
    configure_formatter(getattr(args, "model", "ministral"))
    global_loras = normalize_lora_list(getattr(args, "lora", ()))
    run_id = str(uuid.uuid4())

    segment_length = args.segment_length
    total_length = args.total_length
    megapixels = args.megapixels
    total_segments = math.ceil(total_length / segment_length)
    resume_segment = args.resume
    segments_to_generate = get_segments_to_generate(
        resume_segment,
        total_segments,
    )

    story_source = load_text_file(STORY_FILE, required=True)
    story, beat_instructions = parse_story_beat_instructions(story_source)
    if not story:
        raise ValueError("story.txt contains no story after beat_instructions metadata.")
    subject_definitions = load_text_file(
        SUBJECT_DEFINITIONS_FILE,
        required=False,
    )
    subject_information = format_beat_generation_subjects(subject_definitions)
    if resume_segment == 1:
        reset_prompt_history()
    beats = load_or_generate_beats(
        BEATS_FILE,
        story,
        total_segments,
        history_metadata={"run_id": run_id},
        beat_instructions=beat_instructions,
        subject_information=subject_information,
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
    )
    if resume_segment == 1:
        generation_state = new_generation_state(run_config)
        completed_beat_ids = set()
        recent_results = []
        generated_video_paths = []
        previous_video_path = None
        continuity_summary = ""
        continuity_state = continuity_state_for_registry(subject_definitions)
        continuity_summary_pending = False
    else:
        restored = restore_generation_state(
            resume_segment,
            run_config,
            beats,
        )
        generation_state = restored["state"]
        completed_beat_ids = restored["completed_beat_ids"]
        recent_results = restored["recent_results"]
        generated_video_paths = restored["video_paths"]
        previous_video_path = restored["previous_video_path"]
        continuity_summary = restored["continuity_summary"]
        continuity_state = continuity_state_for_registry(
            subject_definitions,
            restored["continuity_state"],
        )
        continuity_summary_pending = restored["continuity_summary_pending"]

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
    print(f"Formatter:            {getattr(args, 'model', 'ministral')}")
    print(f"Global LoRAs:         {len(global_loras)}")
    print(
        "Prompt corrections:   up to "
        f"{MINISTRAL_CONTENT_CORRECTION_ATTEMPTS}; best effort on failure"
    )
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
    verify_reference_images(initial_test, append_test)
    print("Workflow validation passed.")
    if resume_segment == 1:
        save_generation_state(generation_state)

    director_rules = build_director_rules(
        total_length,
        segment_length,
        total_segments,
        subject_definitions,
        megapixels,
        beats_enabled=bool(beats)
    )

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
    ):
        return json.dumps(
            {
                "segment": int(segment_number),
                "completed_beat_ids": sorted(
                    normalize_completed_beat_ids(beats, completed_ids)
                ),
                "recent_results": list(recent_items),
                "opening_state_sha256": continuity_state_sha(opening_state),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def build_segment_bundle(
        segment_number,
        completed_ids,
        recent_items,
        opening_state,
    ):
        elapsed = (segment_number - 1) * segment_length
        current_duration = min(segment_length, total_length - elapsed)
        active_beat_id = get_next_beat_id(beats, completed_ids)
        opening_summary = (
            format_authoritative_opening_state(
                opening_state,
                subject_definitions,
            )
            if segment_number > 1 else ""
        )
        messages, estimated_tokens, recent_count = build_generation_messages(
            director_rules=director_rules,
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
        )
        ministral_context = build_ministral_context(
            segment_number=segment_number,
            segment_duration=current_duration,
            total_segments=total_segments,
            beats=beats,
            completed_beat_ids=completed_ids,
            subject_definitions=subject_definitions,
            story=story,
            recent_results=recent_items,
            opening_state=opening_summary,
        )
        return {
            "segment": segment_number,
            "current_duration": current_duration,
            "active_beat_id": active_beat_id,
            "loras": beat_loras(beats, active_beat_id, global_loras),
            "messages": messages,
            "estimated_tokens": estimated_tokens,
            "recent_count": recent_count,
            "ministral_context": ministral_context,
            "opening_state": opening_state,
            "opening_summary": opening_summary,
            "opening_state_sha256": continuity_state_sha(opening_state),
            "fingerprint": build_segment_fingerprint(
                segment_number,
                completed_ids,
                recent_items,
                opening_state,
            ),
        }

    def request_segment_llm(bundle):
        llm_result = request_valid_ministral_prompt(
            bundle["messages"],
            bundle["ministral_context"],
            history_metadata={
                "run_id": run_id,
                "source_sha256": run_config["source_sha256"],
                "purpose": "director",
                "segment": bundle["segment"],
                "attempt": 1,
                "opening_state_sha256": bundle["opening_state_sha256"],
            },
        )
        payload = dict(bundle)
        payload["llm_result"] = llm_result
        return payload

    run_start_time = time.perf_counter()
    prefetched_next = None
    for segment in segments_to_generate:
        segment_bundle = build_segment_bundle(
            segment,
            completed_beat_ids,
            recent_results,
            continuity_state,
        )
        if prefetched_next is not None:
            if prefetched_next["segment"] != segment:
                if not prefetched_next["future"].done():
                    prefetched_next["future"].cancel()
                prefetched_next = None
            elif prefetched_next["fingerprint"] != segment_bundle["fingerprint"]:
                if not prefetched_next["future"].done():
                    prefetched_next["future"].cancel()
                print(
                    f"Discarded prefetched LLM response for segment {segment} "
                    "because committed state changed."
                )
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
                payload = prefetched_next["future"].result()
                print(f"Using prefetched LLM response for segment {segment}.")
            except Exception as error:
                print(
                    f"WARNING: prefetched LLM response for segment {segment} failed: "
                    f"{error}. Regenerating now."
                )
            finally:
                prefetched_next = None
        if payload is None:
            payload = request_segment_llm(segment_bundle)

        llm_result = payload["llm_result"]
        loras = payload["loras"]
        reported_beat_ids = llm_result.get("completed_beat_ids", [])
        hard_cut_subject_continuity = ""
        if is_hard_cut_segment(segment):
            hard_cut_subject_continuity = build_hard_cut_subject_continuity_from_state(
                subject_definitions,
                llm_result,
                continuity_state,
            )
        h3_prompt = build_h3_prompt(
            llm_result,
            subject_definitions,
            hard_cut_subject_continuity,
            payload["opening_summary"],
            segment,
            ff=args.ff,
        )
        candidate_future = summary_executor.submit(
            request_structured_continuity_state,
            [(segment, llm_result)],
            continuity_state,
            subject_definitions,
            history_metadata={
                "run_id": run_id,
                "source_sha256": run_config["source_sha256"],
                "purpose": "continuity_candidate",
                "segment": segment,
                "attempt": 1,
            },
            active_beat_text=segment_bundle["ministral_context"].get(
                "current_beat_text", ""
            ),
            future_beat_texts=segment_bundle["ministral_context"].get(
                "later_beat_texts", []
            ),
        )
        candidate_state = None
        print(f"Candidate continuity state requested for segment {segment}.")

        prompt_completed_beat_ids, _ = print_minimax_beat_plan(
            beats,
            completed_beat_ids,
            reported_beat_ids
        )

        # Director LLM prefetch is intentionally disabled. Requesting the next
        # segment only after the current segment commits ensures it always uses
        # the latest beat progress and continuity state.
        # if segment < total_segments:
        #     tentative_completed = set(
        #         normalize_completed_beat_ids(beats, completed_beat_ids)
        #     )
        #     tentative_completed.update(
        #         get_accepted_reported_beat_ids(
        #             beats,
        #             completed_beat_ids,
        #             reported_beat_ids,
        #         )
        #     )
        #     tentative_recent = (
        #         recent_results + [(segment, llm_result)]
        #     )[-RECENT_SEGMENTS_MAX:]
        #     next_bundle = build_segment_bundle(
        #         segment + 1,
        #         tentative_completed,
        #         tentative_recent,
        #         continuity_state,
        #     )
        #     prefetched_next = {
        #         "segment": segment + 1,
        #         "fingerprint": next_bundle["fingerprint"],
        #         "future": director_prefetch_executor.submit(
        #             request_segment_llm,
        #             next_bundle,
        #         ),
        #     }
        #     print(
        #         f"Started LLM prefetch for segment {segment + 1} while "
        #         f"segment {segment} renders."
        #     )

        print()
        print(h3_prompt)
        print()

        try:
            (
                workflow,
                video_path,
                width,
                height,
                rendered_megapixels,
            ) = render_segment_with_retries(
                segment,
                segment_bundle["current_duration"],
                megapixels,
                h3_prompt,
                previous_video_path,
                args.steps,
                loras=loras,
            )
        except Exception:
            candidate_future.cancel()
            if prefetched_next is not None and not prefetched_next["future"].done():
                prefetched_next["future"].cancel()
            print(
                f"Segment {segment} render failed; candidate continuity state discarded"
            )
            raise

        try:
            candidate_state = candidate_future.result()
        except Exception as error:
            print(
                f"WARNING: continuity candidate for segment {segment} failed: {error}; "
                "retaining the last committed state."
            )
            candidate_state = continuity_state
        if candidate_state is None:
            candidate_state = continuity_state
        else:
            print(f"Candidate continuity state generated for segment {segment}.")
        candidate_state = continuity_state_for_registry(
            subject_definitions,
            candidate_state,
        )
        subject_definitions, appended_subject_lines = (
            append_video_subject_definitions(
                subject_definitions,
                candidate_state,
                segment,
            )
        )
        if appended_subject_lines:
            candidate_state = continuity_state_for_registry(
                subject_definitions,
                candidate_state,
            )
            director_rules = build_director_rules(
                total_length,
                segment_length,
                total_segments,
                subject_definitions,
                megapixels,
                beats_enabled=bool(beats),
            )
            print("Appended video-created subject definition(s) to subjects.txt:")
            for definition in appended_subject_lines:
                print(f"  {definition}")
        print(
            f"Created: {video_path}\n"
            f"Resolution: {width} x {height} "
            f"({width * height / 1_000_000:.3f} MP; "
            f"target {rendered_megapixels:.2f} MP)"
        )

        generated_video_paths.append(video_path)
        previous_video_path = video_path

        # Beat state is advanced only after the render succeeds.
        if beats:
            completed_beat_ids = apply_reported_beat_completions(
                beats,
                completed_beat_ids,
                reported_beat_ids,
                segment
            )
            generation_state["beat_progress"] = {
                "completed_beat_ids": sorted(completed_beat_ids),
                "last_segment_number": segment,
                "newly_completed_beat_ids": prompt_completed_beat_ids,
            }

        # Commit the rendered video and structured continuity state together.
        recent_results.append((segment, llm_result))
        recent_results = recent_results[-RECENT_SEGMENTS_MAX:]
        record_completed_segment(
            generation_state,
            segment,
            video_path,
            llm_result,
            completed_beat_ids,
            "",
            continuity_state=candidate_state,
            continuity_summary_pending=False,
        )
        if beats:
            generation_state["beat_progress"] = {
                "completed_beat_ids": sorted(completed_beat_ids),
                "last_segment_number": segment,
                "newly_completed_beat_ids": prompt_completed_beat_ids,
            }
        save_generation_state(generation_state)
        continuity_state = candidate_state
        print(f"Continuity state committed after successful render of segment {segment}.")

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
                print(f"  [TODO] B{beat_id:03d}: {beats[beat_id - 1]}")
        else:
            print(f"All {len(beats)} story beats were marked complete.")
    else:
        print("Story beat tracking was disabled for this run.")

    stitch_videos(generated_video_paths)


def main():
    # The context manager guarantees worker shutdown even when generation,
    # ComfyUI, checkpointing, or the summary request raises an exception.
    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="continuity-summary",
    ) as summary_executor:
        # Director prefetch is intentionally disabled along with the scheduling
        # block in _run_main.
        # with ThreadPoolExecutor(
        #     max_workers=1,
        #     thread_name_prefix="director-prefetch",
        # ) as director_prefetch_executor:
        #     return _run_main(summary_executor, director_prefetch_executor)
        return _run_main(summary_executor)


if __name__ == "__main__":
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
