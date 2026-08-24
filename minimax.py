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
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

from ministral_formatter import (
    format_ministral_prompt,
    normalize_summary_subject_references,
    validate_ministral_prompt,
)


# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LM_STUDIO_URL = os.environ.get(
    "MINIMAX_LM_STUDIO_URL",
    "http://192.168.0.203:1234"
).rstrip("/")
LM_STUDIO_MODEL = os.environ.get(
    "MINIMAX_LM_STUDIO_MODEL",
    "ministral-3-14b-instruct-2512-absolute-heresy.i1-q5_k_m_gguf"
).strip()
COMFY_URL = os.environ.get(
    "MINIMAX_COMFY_URL",
    "http://127.0.0.1:8188"
).rstrip("/")

if os.name == "nt":
    DEFAULT_COMFY_OUTPUT = r"H:\images\output"
else:
    DEFAULT_COMFY_OUTPUT = os.path.expanduser("~/ComfyUI/output")

COMFY_OUTPUT = os.path.abspath(
    os.path.expandvars(
        os.path.expanduser(
            os.environ.get("MINIMAX_COMFYUI_OUTPUT", DEFAULT_COMFY_OUTPUT)
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

FRAME_RATE = 24
TRIM_FRAMES_AFTER_FIRST = 2
TRIM_SECONDS_AFTER_FIRST = TRIM_FRAMES_AFTER_FIRST / FRAME_RATE
MAX_COMFY_SEED = (2 ** 63) - 1

COMFY_QUEUE_RETRIES = 10
COMFY_QUEUE_RETRY_DELAY = 10
COMFY_HISTORY_MAX_ERRORS = 30
COMFY_HISTORY_RETRY_DELAY = 10
COMFY_RENDER_TIMEOUT = 15 * 60
COMFY_RENDER_RETRIES = 10
COMFY_RETRY_MEGAPIXEL_STEP = 0.02
CONTINUITY_STATE_VERSION = 1

LLM_INPUT_TOKEN_BUDGET = 14000
CHARS_PER_TOKEN_ESTIMATE = 3.5
STORY_CONTEXT_MAX_CHARS = 12000
DEFAULT_BEAT_LOOKAHEAD = 8
RECENT_SEGMENTS_MAX = 2
MINISTRAL_CONTENT_CORRECTION_ATTEMPTS = 1
SUMMARY_CONTENT_ATTEMPTS = 2

# These titles are intentionally used instead of numeric ComfyUI node IDs.
DURATION_NODE_NAME = "Float (duration)"
PROMPT_NODE_NAME = "Prompt"
NOISE_NODE_NAME = "RandomNoise"
SAVE_VIDEO_NODE_NAME = "Save Video"
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
                "integrated_multimodal_description": {"type": "string"},
                "overall_soundscape": {"type": "string"},
                "non_diegetic_music": {"type": "string"},
                "completed_beat_ids": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1}
                }
            },
            "required": [
                "integrated_multimodal_description",
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


def build_run_config(
    segment_length,
    total_length,
    megapixels,
    total_segments,
    story="",
    beats=None,
    subject_definitions="",
):
    source_payload = json.dumps(
        {
            "story": story,
            "beats": list(beats or []),
            "subject_definitions": subject_definitions,
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
        match = re.match(
            r"(?i)^\s*<Subject\s+(?P<subject>\d+)>\s+is\s+"
            r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*?)\s*,\s+",
            line,
        )
        if match is None:
            continue
        subject_id = int(match.group("subject"))
        name = match.group("name").strip()
        picture_ids = [
            int(value) for value in re.findall(r"(?i)<Picture\s+(\d+)>", line)
        ]
        if not picture_ids:
            continue
        picture_ids = list(dict.fromkeys(picture_ids))
        speaker_id = (
            f"S{speaker}"
            if (speaker := next(iter(re.findall(r"(?i)\(S(\d+)\)", line)), None))
            else None
        )
        if subject_id in registry:
            raise ValueError(f"Duplicate subject ID: {subject_id}")
        if any(item["name"].lower() == name.lower() for item in registry.values()):
            raise ValueError(f"Duplicate subject name: {name}")
        if speaker_id and any(
            item.get("speaker_id") == speaker_id for item in registry.values()
        ):
            raise ValueError(f"Duplicate speaker ID: {speaker_id}")
        registry[subject_id] = {
            "name": name,
            "picture_ids": picture_ids,
            "picture_id": picture_ids[0],
            "speaker_id": speaker_id,
        }
    #if len(registry) != len(raw_lines):
    #    raise ValueError(
    #        "Every subject definition must declare one <Subject N> and "
    #        "one <Picture N> mapping."
    #    )
    return registry


def new_subject_continuity_record(subject):
    return {
        "subject_id": subject.get("subject_id"),
        "picture_ids": list(subject.get("picture_ids", [subject["picture_id"]])),
        "picture_id": subject["picture_id"],
        "speaker_id": subject.get("speaker_id"),
        "position": "N/A",
        "pose_action": "N/A",
        "wardrobe": {
            "upper": "N/A",
            "lower": "N/A",
            "footwear": "N/A",
            "other": "N/A",
        },
        "body_state": "N/A",
        "physical_condition": "N/A",
        "held_props": [],
    }


def continuity_state_for_registry(subject_definitions, state=None):
    """Return structured state with registry identities and independent fields."""
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
                name = next(
                    (
                        subject["name"]
                        for subject_id_key, subject in registry.items()
                        if subject_id_key == subject_id
                    ),
                    name,
                )
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
            "Expected one definition per line in this format: "
            "<Subject 1> is Mark, a 40-year-old man referenced in "
            "<Picture 1>. Optional speaker mapping: (S1)."
        )
    subjects = {}
    for subject_id, subject in registry.items():
        existing = current.get("subjects", {}).get(subject["name"], {})
        record = new_subject_continuity_record({
            **subject,
            "subject_id": subject_id,
        })
        if isinstance(existing, dict):
            for field in (
                "position",
                "pose_action",
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
        subjects[subject["name"]] = record
    current["subjects"] = subjects
    return current


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
        migrated["subjects"] = normalized_subjects
    return migrated


def format_authoritative_opening_state(state, subject_definitions=""):
    """Render the committed structured state for the next director request."""
    state = continuity_state_for_registry(subject_definitions, state)
    lines = [
        "AUTHORITATIVE OPENING STATE",
        "",
        "This is the final observable state of the preceding successfully "
        "rendered video and therefore the physical starting state of this segment.",
        "Preserve every listed condition until an action in THIS segment visibly changes it.",
        "",
        "environment:",
        f"- location: {state['environment']['location']}",
        f"- persistent_state: {state['environment']['persistent_state']}",
        f"camera: {state['camera']}",
        "subjects:",
    ]
    registry = parse_subject_registry(subject_definitions)
    if not registry:
        registry = {
            int(record.get("subject_id", index)): {
                "name": name,
                "picture_id": record.get("picture_id"),
                "speaker_id": record.get("speaker_id"),
            }
            for index, (name, record) in enumerate(
                state.get("subjects", {}).items(),
                start=1,
            )
            if isinstance(record, dict) and record.get("picture_id") is not None
        }
    if not registry:
        raise RuntimeError(
            "Cannot render AUTHORITATIVE OPENING STATE: no subject registry "
            "was available."
        )
    for subject_id, subject in registry.items():
        record = state["subjects"][subject["name"]]
        lines.extend([
            f"- {subject['name']} " + " ".join(
                f"<Picture {picture}>"
                for picture in subject.get(
                    "picture_ids",
                    [subject["picture_id"]],
                )
            ),
            f"  position: {record['position']}",
            f"  pose_action: {record['pose_action']}",
            f"  wardrobe_upper: {record['wardrobe']['upper']}",
            f"  wardrobe_lower: {record['wardrobe']['lower']}",
            f"  wardrobe_footwear: {record['wardrobe']['footwear']}",
            f"  wardrobe_other: {record['wardrobe']['other']}",
            f"  body_state: {record['body_state']}",
            f"  physical_condition: {record['physical_condition']}",
            f"  held_props: {json.dumps(record['held_props'], ensure_ascii=False)}",
        ])
    lines.extend([
        f"ongoing_action: {state['ongoing_action']}",
        f"ongoing_audio: {state['ongoing_audio']}",
    ])
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
            f"  speaker_id: {speaker}"
        )
    return "\n".join(lines)


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

# ============================================================
# BEATS
# ============================================================

def load_beats(path):
    raw = load_text_file(path, required=True)
    beats = []
    for line in raw.splitlines():
        beat = line.strip()
        if beat and not beat.startswith("#"):
            beats.append(beat)

    return beats


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
    with open(path, "w", encoding="utf-8"):
        pass


def ask_llm(
    messages,
    max_retries=5,
    retry_delay=5,
    response_format=RESPONSE_FORMAT,
    history_metadata=None,
):
    last_error = None
    messages = normalize_lm_studio_messages(messages)
    for attempt in range(1, max_retries + 1):
        try:
            request_payload = {
                "model": LM_STUDIO_MODEL,
                "messages": messages,
                "temperature": 0.35,
                "max_tokens": 4000
            }
            if response_format is not None:
                request_payload["response_format"] = response_format

            append_prompt_history(
                messages,
                metadata={
                    "model": LM_STUDIO_MODEL,
                    "response_format": response_format is not None,
                    **(history_metadata or {}),
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
                            "model": LM_STUDIO_MODEL,
                            "response_format": False,
                            **(history_metadata or {}),
                            "request_variant": "without_response_format",
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
- Do not substantially enact ordered lookahead beats before the ACTIVE beat completes.
- Do not invent irreversible physical changes unless the ACTIVE beat requires
  them. Do not sever or remove body parts, permanently destroy equipment,
  introduce major lasting injuries, kill a character, or permanently alter
  wardrobe merely to make an action scene more dramatic.
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

{subject_context}

Use the registered form `Character Name <Picture N>` for defined subjects.
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
- On every later segment that is not divisible by 3, it MUST begin with the
    continuation form; do not choose a cut naturally on those segments.
- On a required CUT segment, do not write any continuation opening or sentence
    such as `camera continues from the previous shot`; the shot must begin only
    with the cut form.
- Otherwise continue or cut naturally.
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

integrated_multimodal_description:
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


def format_recent_segment(segment_number, llm_result):
    payload = {
        key: value
        for key, value in llm_result.items()
        if key != "completed_beat_ids"
    }
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


def build_structured_continuity_messages(
    recent_results,
    committed_state,
    subject_definitions,
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
    return [
        {
            "role": "system",
            "content": (
                "You are a continuity state updater. Return only one JSON object "
                "with fields version, environment, camera, subjects, ongoing_action, "
                "and ongoing_audio.\n\n"
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
                "Use the latest explicitly established framing, position, or pose near "
                "the end of the newest segment; do not return camera as N/A merely "
                "because it did not move.\n\n"
                "environment.persistent_state contains visible surroundings likely to "
                "remain: terrain, weather, damage, structures, smoke, debris, or "
                "persistent lighting. Do not put transient action, emotion, or mood there.\n\n"
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
                "LATEST GENERATED PROMPTS:\n"
                f"{exact_prompts}\n\n"
                "Return the complete updated structured state."
            ),
        },
    ]


def normalize_structured_continuity_state(
    candidate,
    subject_definitions,
    committed_state=None,
):
    if not isinstance(candidate, dict):
        return None
    state = continuity_state_for_registry(subject_definitions, committed_state)
    registry = parse_subject_registry(subject_definitions)
    id_to_name = {
        str(subject_id): subject["name"]
        for subject_id, subject in registry.items()
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

    def concrete_value(value):
        if not isinstance(value, str):
            return None
        cleaned = sanitize_previous_state_value(value)
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
            value = concrete_value(candidate[field])
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
                value = concrete_value(environment[field])
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
            name = resolve_subject_name(raw_name)
            if name is None or not isinstance(record, dict):
                continue
            target = state["subjects"][name]
            for field in (
                "position",
                "pose_action",
                "body_state",
                "physical_condition",
            ):
                if isinstance(record.get(field), str):
                    value = concrete_value(record[field])
                    if value is not None:
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
                        value = concrete_value(wardrobe[garment])
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
                target["held_props"] = props
    state["version"] = CONTINUITY_STATE_VERSION
    return state


def request_structured_continuity_state(
    recent_results,
    committed_state,
    subject_definitions,
    llm_request=None,
    history_metadata=None,
):
    if llm_request is None:
        llm_request = ask_llm
    messages = build_structured_continuity_messages(
        recent_results,
        committed_state,
        subject_definitions,
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
    return normalize_structured_continuity_state(
        candidate,
        subject_definitions,
        committed_state,
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
    recent_results=None
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
        "recent_descriptions": [
            str(result.get("integrated_multimodal_description", ""))
            for _, result in (recent_results or [])
            if isinstance(result, dict)
        ]
    }


def build_best_effort_ministral_result(raw_result):
    if isinstance(raw_result, dict):
        integrated = raw_result.get("integrated_multimodal_description")
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
        "integrated_multimodal_description": integrated,
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


def request_valid_ministral_prompt(
    messages,
    context,
    llm_request=None,
    max_content_corrections=MINISTRAL_CONTENT_CORRECTION_ATTEMPTS,
    history_metadata=None,
):
    if llm_request is None:
        llm_request = ask_llm

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

    request_kwargs = (
        {"history_metadata": history_metadata}
        if history_metadata else {}
    )
    raw_result = llm_request(messages, **request_kwargs)
    formatted_result, issues = format_and_validate(raw_result)
    if not issues:
        return formatted_result

    for correction_number in range(1, max_content_corrections + 1):
        print(
            "Python formatting left unresolved content issue(s); "
            f"requesting Ministral correction {correction_number}/"
            f"{max_content_corrections}."
        )
        # Use a fresh stateless system/user request. This is accepted by
        # Ministral's strict Jinja template and cannot contain adjacent users.
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
            return formatted_result
        formatted_result, issues = format_and_validate(corrected_raw)
        if not issues:
            return formatted_result

    print(
        "WARNING: Prompt still has unresolved issue(s) after all Ministral "
        "corrections; using the latest best-effort prompt:"
    )
    for issue in issues:
        print(f"  - {issue}")
    return formatted_result


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
        subject_definitions or ""
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

    current_description = (
        current_result.get("integrated_multimodal_description", "")
        if isinstance(current_result, dict) else ""
    )
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
        record.get("llm_result", {}).get(
            "integrated_multimodal_description", ""
        )
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
    current_description = (
        current_result.get("integrated_multimodal_description", "")
        if isinstance(current_result, dict) else ""
    )
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
    required = (
        "integrated_multimodal_description",
        "overall_soundscape",
        "non_diegetic_music"
    )
    for field in required:
        if not isinstance(llm_result.get(field), str):
            raise RuntimeError(f"LLM response is missing text field '{field}'.")

    integrated = strip_field_prefix(
        llm_result["integrated_multimodal_description"],
        "integrated_multimodal_description"
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
    previous_state_text = (
        None
        if segment_number == 1
        else (
            previous_state
            if isinstance(previous_state, str)
            and previous_state.lstrip().startswith("AUTHORITATIVE OPENING STATE")
            else normalize_previous_state(previous_state)
        )
    )
    if hard_cut_clothing_reiteration and previous_state_text is not None:
        previous_state_text += "\n" + hard_cut_clothing_reiteration
    previous_state_section = (
        f"{previous_state_text}\n\n"
        if previous_state_text is not None else ""
    )
    return (
        f"subject_definitions: {subject_text}\n\n"
        + previous_state_section
        + f"integrated_multimodal_description: {integrated}\n\n"
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
):
    """Render one segment, retrying only recoverable ComfyUI failures."""
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

        if segment == 1:
            workflow = prepare_initial_workflow(
                current_duration,
                current_megapixels,
                h3_prompt,
                segment,
                steps,
            )
        else:
            workflow = prepare_append_workflow(
                current_duration,
                h3_prompt,
                previous_video_path,
                segment,
                steps,
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
):
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
    return workflow


def prepare_append_workflow(
    duration,
    h3_prompt,
    previous_video_path,
    segment_number,
    steps=6,
):
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
    validate_runtime_environment()
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

    story = load_text_file(STORY_FILE, required=True)
    beats = load_beats(BEATS_FILE)
    subject_definitions = load_text_file(
        SUBJECT_DEFINITIONS_FILE,
        required=False
    )

    run_config = build_run_config(
        segment_length,
        total_length,
        megapixels,
        total_segments,
        story,
        beats,
        subject_definitions,
    )
    if resume_segment == 1:
        reset_prompt_history()
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

    run_start_time = time.perf_counter()
    for segment in segments_to_generate:
        elapsed = (segment - 1) * segment_length
        current_duration = min(segment_length, total_length - elapsed)

        print()
        print("=" * 64)
        print(
            f"SEGMENT {segment}/{total_segments} "
            f"({current_duration:g} seconds)"
        )
        print("=" * 64)

        messages, estimated_tokens, recent_count = build_generation_messages(
            director_rules=director_rules,
            story=story,
            beats=beats,
            completed_beat_ids=completed_beat_ids,
            recent_results=recent_results,
            current_segment=segment,
            total_segments=total_segments,
            segment_length=segment_length,
            total_length=total_length,
            continuity_summary=(
                format_authoritative_opening_state(
                    continuity_state,
                    subject_definitions,
                )
                if segment > 1 else ""
            ),
            subject_definitions=subject_definitions,
        )
        print(
            f"Estimated LLM input context: "
            f"{estimated_tokens}/{LLM_INPUT_TOKEN_BUDGET} tokens "
            f"(recent exact segments: {recent_count})"
        )

        ministral_context = build_ministral_context(
            segment_number=segment,
            segment_duration=current_duration,
            total_segments=total_segments,
            beats=beats,
            completed_beat_ids=completed_beat_ids,
            subject_definitions=subject_definitions,
            story=story,
            recent_results=recent_results
        )
        llm_result = request_valid_ministral_prompt(
            messages,
            ministral_context,
            history_metadata={
                "run_id": run_id,
                "source_sha256": run_config["source_sha256"],
                "purpose": "director",
                "segment": segment,
                "attempt": 1,
                "opening_state_sha256": hashlib.sha256(
                    json.dumps(
                        continuity_state,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            },
        )
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
            (
                format_authoritative_opening_state(
                    continuity_state,
                    subject_definitions,
                )
                if segment > 1 else ""
            ),
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
        )
        candidate_state = None
        print(f"Candidate continuity state requested for segment {segment}.")

        prompt_completed_beat_ids, _ = print_minimax_beat_plan(
            beats,
            completed_beat_ids,
            reported_beat_ids
        )
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
                current_duration,
                megapixels,
                h3_prompt,
                previous_video_path,
                args.steps,
            )
        except Exception:
            candidate_future.cancel()
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
