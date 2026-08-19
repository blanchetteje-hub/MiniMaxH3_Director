import argparse
import hashlib
import json
import math
import os
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
BEAT_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "beat_progress.txt")
GENERATION_STATE_FILE = os.path.join(SCRIPT_DIR, "generation_state.json")
FINAL_VIDEO = os.path.join(VIDEO_OUTPUT, "final.mp4")

FRAME_RATE = 24
TRIM_FRAMES_AFTER_FIRST = 2
TRIM_SECONDS_AFTER_FIRST = TRIM_FRAMES_AFTER_FIRST / FRAME_RATE
BASE_SEED = 1

COMFY_QUEUE_RETRIES = 10
COMFY_QUEUE_RETRY_DELAY = 10
COMFY_HISTORY_MAX_ERRORS = 30
COMFY_HISTORY_RETRY_DELAY = 10

LLM_INPUT_TOKEN_BUDGET = 14000
CHARS_PER_TOKEN_ESTIMATE = 3.5
RECENT_SEGMENTS_MAX = 2
MINISTRAL_CONTENT_CORRECTION_ATTEMPTS = 2
SUMMARY_CONTENT_ATTEMPTS = 2

# These titles are intentionally used instead of numeric ComfyUI node IDs.
DURATION_NODE_NAME = "Float (duration)"
PROMPT_NODE_NAME = "Prompt"
NOISE_NODE_NAME = "RandomNoise"
SAVE_VIDEO_NODE_NAME = "Save Video"
RESOLUTION_NODE_NAME = "Resolution Selector"
IMAGE_BATCH_NODE_NAME = "Image Batch Multi"
MATH_NODE_NAME = "Math Expression"
VIDEO_EXTEND_NODE_NAME = "MiniMax H3 Video Extend (Backported)"
ENCODE_AV_NODE_NAME = "MiniMax H3 Encode AV (Backported)"
LOAD_VIDEO_NODE_NAME = "Load Video (Path) 🎥🅥🅗🅢"
REFERENCE_IMAGE_NODE_NAMES = tuple(
    f"Reference Image {image_number}"
    for image_number in range(1, 7)
)


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

    if arguments is None:
        arguments = sys.argv[1:]

    args = parser.parse_args(normalize_command_line(arguments))

    if args.segment_length <= 0:
        parser.error("segment_length must be greater than 0.")
    if args.total_length <= 0:
        parser.error("total_length must be greater than 0.")
    if args.megapixels <= 0:
        parser.error("megapixels must be greater than 0.")
    if args.resume <= 0:
        parser.error("--resume must be a one-based segment number.")

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


def new_generation_state(run_config):
    return {
        "version": 1,
        "config": dict(run_config),
        "segments": [],
        "continuity_summary": "",
        "continuity_summary_pending": False,
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
    if state.get("config") != run_config:
        raise RuntimeError(
            "Resume settings or source inputs do not match "
            "generation_state.json. Use the same segment length, total "
            "length, megapixel value, story, beats, and subject definitions "
            "as the original run."
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
        state["continuity_summary"] = restored_records[-1].get(
            "continuity_summary",
            state.get("continuity_summary", ""),
        )
        state["continuity_summary_pending"] = bool(
            restored_records[-1].get("continuity_summary_pending", False)
        )
    else:
        state["continuity_summary"] = ""
        state["continuity_summary_pending"] = False
    return {
        "state": state,
        "video_paths": video_paths,
        "previous_video_path": video_paths[-1] if video_paths else None,
        "recent_results": recent_results[-RECENT_SEGMENTS_MAX:],
        "completed_beat_ids": completed_beat_ids,
        "continuity_summary": state.get("continuity_summary", ""),
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
    continuity_summary_pending=False,
):
    records = state.setdefault("segments", [])
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
        "continuity_summary_pending": bool(continuity_summary_pending),
    }
    records.append(record)
    state["continuity_summary"] = continuity_summary
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

    for name in REFERENCE_IMAGE_NODE_NAMES:
        find_workflow_node(workflow, name, workflow_label, "LoadImage")

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

    for index, expected_source_title in enumerate(
        REFERENCE_IMAGE_NODE_NAMES,
        start=1
    ):
        validate_named_connection(
            workflow,
            IMAGE_BATCH_NODE_NAME,
            f"image_{index}",
            expected_source_title,
            0,
            workflow_label
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


def save_beat_progress(beats, completed_beat_ids):
    completed = normalize_completed_beat_ids(beats, completed_beat_ids)
    next_id = get_next_beat_id(beats, completed)
    if next_id is None:
        next_text = "All required beats are complete."
    else:
        next_text = f"B{next_id:03d}: {beats[next_id - 1]}"

    content = (
        f"Completed beats: {len(completed)}/{len(beats)}\n"
        f"Next required beat: {next_text}\n\n"
        f"{format_beat_progress(beats, completed)}\n"
    )
    with open(BEAT_PROGRESS_FILE, "w", encoding="utf-8") as f:
        f.write(content)


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

    accepted = []
    next_id = get_next_beat_id(beats, completed)

    while next_id is not None and next_id in valid_reported:
        completed.add(next_id)
        accepted.append(next_id)
        next_id = get_next_beat_id(beats, completed)

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


def ask_llm(
    messages,
    max_retries=5,
    retry_delay=5,
    response_format=RESPONSE_FORMAT
):
    last_error = None
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
    return sum(
        estimate_text_tokens(message.get("content", "")) + 12
        for message in messages
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
    if megapixels < 0.6:
        resolution_guidance.append(
            "- Prefer closer framing; keep important subjects large and clear."
        )
    if megapixels < 0.5:
        resolution_guidance.append(
            "- Keep camera motion and simultaneous action relatively simple."
        )
    resolution_text = "\n".join(resolution_guidance) or "- No special guidance."

    if beats_enabled:
        role_description = (
            "from a supplied creative brief and an authoritative ordered "
            "story-beat checklist"
        )
        beat_rules = """
STORY PROGRESSION
- The AUTHORITATIVE STORY BEAT CHECKLIST controls plot order.
- [DONE] beats already happened. NEVER repeat them.
- [NEXT] is the immediate required beat.
- [TODO] beats must happen later, in listed order.
- Do not skip NEXT to reach a later beat.
- A beat may span several segments, but CURRENT TASK gives its pacing deadline.
- SOURCE STORY / CREATIVE BRIEF provides tone, setting, dialogue, connective action, and details.
- RECENT EXACT GENERATED SEGMENTS are authoritative for immediate continuity.
- Pace all unfinished beats so the movie ends naturally on the final segment.

BEAT COMPLETION REPORTING
- completed_beat_ids contains ONLY beats fully completed by THIS segment.
- B003 is reported as integer 3.
- If no beat fully completes, return [].
- Do not mark a beat complete merely because it begins.
- Multiple completed beats must be consecutive beginning with NEXT.
- Do not mention beat IDs inside the scene description.
""".strip()
    else:
        role_description = "from a supplied creative brief"
        beat_rules = """
STORY PROGRESSION
- Direct the complete movie from SOURCE STORY / CREATIVE BRIEF.
- RECENT EXACT GENERATED SEGMENTS are authoritative for immediate continuity.
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

SUBJECTS
Pictures 1-6 are persistent identity/body references only, not wardrobe records.
Written story/continuity overrides clothing visible in reference pictures.

{subject_context}

When a defined subject appears, identify the first mention as `<Subject N> Name`.
Do not invent Subject or Picture tags for undefined people or objects.
Python inserts subject_definitions separately; do not output subject_definitions.

SHOT AND TIMING
- Each segment contains exactly one shot: Segment N = [Shot N].
- integrated_multimodal_description MUST begin with one of:
  `[Shot N] Camera continues from the previous shot...`
  `[Shot N] Camera cuts to a new shot: ...`
- Shot 1 should explicitly establish its initial framing because there is no previous shot.
- The opening [Shot N] has no timestamp.
- Later timestamps use this clip's local timeline, are greater than 00:00.000, and remain before clip duration.
- Never use cumulative movie timestamps.
- If Shot N is divisible by 3, it MUST begin with the CUT form.
- Otherwise continue or cut naturally.
- Write camera motion as natural English within the shot, never as stacked labels.
- Use only Zoom In/Out, Push In/Pull Out, Pan Left/Right, Truck Left/Right,
  Tilt Up/Down, Pedestal Up/Down, Arc Shot, Tracking Shot, Static Shot,
  Shake Slightly/Strongly, POV, or Roll Clockwise/Counterclockwise.
- Add `with small/large amplitude` and `at slow/fast speed` only when meaningful.

DIALOGUE
- Never imply speech; write the exact spoken words.
- Format: Character Name (S1) says: <d>[English] Actual spoken words.</d>
- Defined Subject N should consistently use S(N) when speaking whenever practical.
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
    return (
        f"--- EXACT RECENT SEGMENT {segment_number} ---\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + f"\n--- END SEGMENT {segment_number} ---"
    )


def build_summary_messages(recent_results):
    """Build a stateless continuity-summary conversation for two results."""
    recent_pair = list(recent_results)[-RECENT_SEGMENTS_MAX:]
    if len(recent_pair) != RECENT_SEGMENTS_MAX:
        raise ValueError("A continuity summary requires exactly two segments.")

    exact_prompts = "\n\n".join(
        format_recent_segment(number, result)
        for number, result in recent_pair
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a movie continuity summarizer. Summarize only the two "
                "generated prompts supplied by the user. Return exactly five "
                "plain-text bullet points, each beginning with '- '. Include "
                "only concrete continuity facts useful to the next shot, such "
                "as subject appearance, clothing, location, positions, actions, "
                "props, injuries, dialogue facts, and ongoing sound. Do not add "
                "a heading, invent details, or give directing advice."
            )
        },
        {
            "role": "user",
            "content": (
                "Write the five-bullet continuity summary for these two exact "
                f"generated prompts:\n\n{exact_prompts}"
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


def request_five_bullet_summary(
    recent_results,
    llm_request=None,
    content_attempts=SUMMARY_CONTENT_ATTEMPTS
):
    """Summarize two results in an LLM thread separate from generation."""
    if llm_request is None:
        llm_request = ask_llm
    base_messages = build_summary_messages(recent_results)
    for attempt in range(1, content_attempts + 1):
        messages = list(base_messages)
        if attempt > 1:
            messages.append({
                "role": "user",
                "content": (
                    "The prior response was not exactly five bullet lines. "
                    "Return the requested summary with exactly five non-empty "
                    "lines, each beginning with '- ', and no other text."
                )
            })
        summary = llm_request(messages, response_format=None)
        normalized = normalize_five_bullet_summary(summary)
        if normalized is not None:
            return normalized

    raise RuntimeError(
        "LM Studio did not return an exact five-bullet continuity summary "
        f"after {content_attempts} attempts."
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
            "All required beats are complete. Use remaining runtime to resolve "
            "the ending naturally without repeating completed events."
        )
    else:
        deadline = get_beat_deadline_segment(
            next_beat_id,
            beats,
            total_segments
        )
        if segment >= deadline:
            deadline_text = (
                f"B{next_beat_id:03d} has reached its pacing deadline and MUST "
                "be visibly completed in this segment."
            )
        else:
            deadline_text = (
                f"B{next_beat_id:03d} should be fully completed no later than "
                f"segment {deadline}."
            )
        beat_focus = (
            f"NEXT beat: B{next_beat_id:03d}: {beats[next_beat_id - 1]} "
            f"{deadline_text} Do not substantially enact later TODO beats first."
        )

    if segment == 1:
        continuation = (
            "This is the first generated clip. Begin with the story's OPENING "
            "SCENE and OPENING CLOTHING. There is no previous-video context."
        )
    else:
        continuation = (
            "The complete preceding generated video is supplied directly to "
            "MiniMax as continuation context. Continue immediately from it and "
            "do not recap its ending."
        )

    return (
        f"Create segment {segment} of {total_segments}. This is [Shot {segment}]. "
        f"The new clip is {current_duration:g} seconds long and its local timeline "
        f"begins at 00:00.000. {continuation} Pictures 1 through 6 remain subject "
        f"references only. {beat_focus}"
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
    continuity_summary=None
):
    if beats:
        beat_section = f"""
AUTHORITATIVE STORY BEAT CHECKLIST

[DONE] beats already happened and must not be repeated.
[NEXT] is the immediate required beat.
[TODO] beats must happen later in listed order.

{format_beat_progress(beats, completed_beat_ids)}


"""
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
            summary_section = f"""
CONTINUITY SUMMARY OF THE PREVIOUS TWO GENERATED SEGMENTS

{continuity_summary}


"""
        else:
            summary_section = ""

        return f"""
{beat_section}{summary_section}SOURCE STORY / CREATIVE BRIEF

--- STORY START ---
{story}
--- STORY END ---


RECENT EXACT GENERATED SEGMENT DESCRIPTIONS

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
    next_beat_id = get_next_beat_id(beats, completed)
    if not beats:
        current_beat_text = None
        later_beat_texts = []
        deadline_required = False
    elif next_beat_id is None:
        current_beat_text = None
        later_beat_texts = []
        deadline_required = False
    else:
        current_beat_text = beats[next_beat_id - 1]
        later_beat_texts = beats[next_beat_id:]
        deadline = get_beat_deadline_segment(
            next_beat_id,
            beats,
            total_segments
        )
        deadline_required = segment_number >= deadline

    return {
        "segment_number": segment_number,
        "segment_duration": segment_duration,
        "subject_definitions": subject_definitions or "",
        "completed_beat_ids": sorted(completed),
        "next_beat_id": next_beat_id,
        "current_beat_text": current_beat_text,
        "later_beat_texts": later_beat_texts,
        "beat_deadline_required": deadline_required,
        "allow_silence": story_requests_complete_silence(story),
        "hard_cut_required": is_hard_cut_segment(segment_number),
        "recent_descriptions": [
            str(result.get("integrated_multimodal_description", ""))
            for _, result in (recent_results or [])
            if isinstance(result, dict)
        ]
    }


def format_correction_request(formatted_result, issues):
    issue_text = "\n".join(
        f"{index}. {issue}"
        for index, issue in enumerate(issues, start=1)
    )
    return f"""
CONTENT CORRECTION REQUIRED

Python already applied every safe deterministic formatting repair. Regenerate
the complete JSON response because the remaining problems cannot be fixed
without changing or inventing scene content.

UNRESOLVED VIOLATIONS
{issue_text}

LOCALLY FORMATTED PRIOR RESPONSE
{json.dumps(formatted_result, ensure_ascii=False, indent=2)}

Return the entire corrected JSON object using the required response schema.
Preserve valid details and exact dialogue wording unless a listed violation
explicitly requires new content. Do not merely change completed_beat_ids; the
scene description itself must visibly satisfy the current beat.
""".strip()


def request_valid_ministral_prompt(
    messages,
    context,
    llm_request=None,
    max_content_corrections=MINISTRAL_CONTENT_CORRECTION_ATTEMPTS
):
    if llm_request is None:
        llm_request = ask_llm

    last_issues = []
    request_messages = messages
    for correction_number in range(max_content_corrections + 1):
        raw_result = llm_request(request_messages)
        try:
            formatted_result = format_ministral_prompt(raw_result, context)
        except (TypeError, ValueError) as error:
            formatted_result = {"unparsed_response": str(raw_result)}
            last_issues = [f"Response could not be parsed locally: {error}"]
        else:
            last_issues = validate_ministral_prompt(formatted_result, context)
        if not last_issues:
            return formatted_result

        if correction_number >= max_content_corrections:
            break

        print(
            "Python formatting left unresolved content issue(s); "
            f"requesting Ministral correction {correction_number + 1}/"
            f"{max_content_corrections}."
        )
        request_messages = messages + [{
            "role": "user",
            "content": format_correction_request(formatted_result, last_issues)
        }]

    details = "\n".join(f"- {issue}" for issue in last_issues)
    raise RuntimeError(
        "Ministral prompt remained invalid after Python formatting and "
        f"{max_content_corrections} content correction request(s):\n{details}"
    )


# ============================================================
# H3 PROMPT
# ============================================================

def strip_field_prefix(value, field_name):
    value = value.strip()
    prefix = f"{field_name}:"
    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix):].lstrip()
    return value


def build_h3_prompt(llm_result, subject_definitions):
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

    subject_text = subject_definitions.strip() or "N/A"
    return (
        f"subject_definitions: {subject_text}\n\n"
        f"integrated_multimodal_description: {integrated}\n\n"
        f"overall_soundscape: {soundscape}\n\n"
        f"non_diegetic_music: {music}"
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


def queue_workflow(
    workflow,
    max_retries=COMFY_QUEUE_RETRIES,
    retry_delay=COMFY_QUEUE_RETRY_DELAY
):
    last_error = None
    client_id = str(uuid.uuid4())

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
            print(
                f"ComfyUI queue failed (attempt {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                time.sleep(retry_delay)

    raise RuntimeError("ComfyUI queue failed repeatedly.") from last_error


def wait_for_completion(
    prompt_id,
    max_consecutive_errors=COMFY_HISTORY_MAX_ERRORS,
    retry_delay=COMFY_HISTORY_RETRY_DELAY
):
    consecutive_errors = 0

    while True:
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
                        raise RuntimeError(
                            "ComfyUI execution failed:\n"
                            + json.dumps(status, indent=2)
                        )
                    return result

            time.sleep(2)
        except RuntimeError:
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


def prepare_initial_workflow(duration, megapixels, h3_prompt, segment_number):
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
        workflow, NOISE_NODE_NAME, "noise_seed",
        BASE_SEED + segment_number - 1,
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


def prepare_append_workflow(duration, h3_prompt, previous_video_path, segment_number):
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
        BASE_SEED + segment_number - 1,
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
        generation_state = new_generation_state(run_config)
        completed_beat_ids = set()
        recent_results = []
        generated_video_paths = []
        previous_video_path = None
        continuity_summary = ""
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
        continuity_summary_pending = restored["continuity_summary_pending"]

    if beats:
        save_beat_progress(beats, completed_beat_ids)

    print()
    print("=" * 64)
    print("H3 AUTOMATED DIRECTOR - SIMPLIFIED")
    print("=" * 64)
    print(f"Segment length:       {segment_length:g} seconds")
    print(f"Total story length:   {total_length:g} seconds")
    print(f"Total segments:       {total_segments}")
    print(f"Starting segment:     {resume_segment}")
    print(f"Initial megapixels:   {megapixels:g}")
    if beats:
        print(f"Story beats:          {len(beats)}")
        print(f"Beat progress file:   {BEAT_PROGRESS_FILE}")
        print("Persistent state:     generation_state.json + beat_progress.txt")
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
    if continuity_summary_pending:
        if len(recent_results) != RECENT_SEGMENTS_MAX:
            raise RuntimeError(
                "Cannot rebuild the pending continuity summary without the "
                "last two saved prompt results."
            )
        print("Rebuilding the pending five-bullet continuity summary...")
        continuity_summary = summary_executor.submit(
            request_five_bullet_summary,
            recent_results,
        ).result()
        last_record = generation_state["segments"][-1]
        last_record["continuity_summary"] = continuity_summary
        last_record["continuity_summary_pending"] = False
        generation_state["continuity_summary"] = continuity_summary
        generation_state["continuity_summary_pending"] = False
        continuity_summary_pending = False
        save_generation_state(generation_state)

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
            continuity_summary=continuity_summary,
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
            ministral_context
        )
        summary_future = None
        summary_pair = (recent_results + [(segment, llm_result)])[-2:]
        if len(summary_pair) == RECENT_SEGMENTS_MAX:
            print(
                "Starting a separate five-bullet continuity-summary thread "
                "while ComfyUI renders..."
            )
            summary_future = summary_executor.submit(
                request_five_bullet_summary,
                summary_pair,
            )
        reported_beat_ids = llm_result.get("completed_beat_ids", [])
        h3_prompt = build_h3_prompt(llm_result, subject_definitions)

        print()
        print(h3_prompt)
        print()

        if segment == 1:
            workflow = prepare_initial_workflow(
                current_duration,
                megapixels,
                h3_prompt,
                segment
            )
        else:
            workflow = prepare_append_workflow(
                current_duration,
                h3_prompt,
                previous_video_path,
                segment
            )

        prompt_id = queue_workflow(workflow)
        print(f"ComfyUI prompt ID: {prompt_id}")
        comfy_result = wait_for_completion(prompt_id)
        video_path = get_video_path(comfy_result, workflow)
        width, height = get_video_resolution(video_path)
        print(
            f"Created: {video_path}\n"
            f"Resolution: {width} x {height} "
            f"({width * height / 1_000_000:.3f} MP)"
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
            save_beat_progress(beats, completed_beat_ids)

        # Checkpoint the rendered video before waiting for the separate summary
        # so a summary failure never requires rendering this segment again.
        recent_results.append((segment, llm_result))
        recent_results = recent_results[-RECENT_SEGMENTS_MAX:]
        checkpoint_record = record_completed_segment(
            generation_state,
            segment,
            video_path,
            llm_result,
            completed_beat_ids,
            continuity_summary,
            continuity_summary_pending=summary_future is not None,
        )
        save_generation_state(generation_state)

        if summary_future is not None:
            if not summary_future.done():
                print(
                    "ComfyUI finished before the continuity summary; "
                    "waiting for LM Studio..."
                )
            try:
                continuity_summary = summary_future.result()
            except Exception as e:
                raise RuntimeError(
                    f"Continuity summary failed after segment {segment}: {e}"
                ) from e
            checkpoint_record["continuity_summary"] = continuity_summary
            checkpoint_record["continuity_summary_pending"] = False
            generation_state["continuity_summary"] = continuity_summary
            generation_state["continuity_summary_pending"] = False
            save_generation_state(generation_state)
            print("Five-bullet continuity summary updated.")

        elapsed_seconds = time.perf_counter() - run_start_time
        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)
        print(f"Cumulative runtime: {hours:02d}:{minutes:02d}:{seconds:02d}")

        if segment % 5 == 0:
            free_vram()

    free_vram()

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
