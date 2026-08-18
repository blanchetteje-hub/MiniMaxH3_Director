import argparse
import glob
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests


# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def configured_path(environment_name, default_path):
    """Return an absolute, expanded path from an environment setting."""

    configured_value = os.environ.get(environment_name, default_path)
    expanded_value = os.path.expandvars(
        os.path.expanduser(configured_value)
    )
    return os.path.abspath(expanded_value)


# URLs and filesystem locations can be customized without editing Python.
# Windows keeps the original project defaults, while Linux defaults to a
# conventional ~/ComfyUI installation.
LM_STUDIO_URL = os.environ.get(
    "MINIMAX_LM_STUDIO_URL",
    "http://192.168.0.203:1234"
).rstrip("/")
COMFY_URL = os.environ.get(
    "MINIMAX_COMFY_URL",
    "http://127.0.0.1:8188"
).rstrip("/")

if os.name == "nt":
    DEFAULT_COMFY_ROOT = r"C:\ComfyUI_windows_portable\ComfyUI"
else:
    DEFAULT_COMFY_ROOT = os.path.join("~", "ComfyUI")

COMFY_ROOT = configured_path(
    "MINIMAX_COMFYUI_ROOT",
    DEFAULT_COMFY_ROOT
)

if os.name == "nt":
    # Preserve the original project's separate Windows output drive.
    DEFAULT_COMFY_OUTPUT = r"H:\images\output"
else:
    DEFAULT_COMFY_OUTPUT = os.path.join(COMFY_ROOT, "output")

COMFY_OUTPUT = configured_path(
    "MINIMAX_COMFYUI_OUTPUT",
    DEFAULT_COMFY_OUTPUT
)
VIDEO_OUTPUT = configured_path(
    "MINIMAX_VIDEO_OUTPUT",
    os.path.join(COMFY_OUTPUT, "video")
)

# Project inputs are resolved beside this script, so launching it from a
# different working directory behaves identically on Windows and Linux.
INITIAL_WORKFLOW_FILE = os.path.join(
    SCRIPT_DIR,
    "Minimax_auto_API.json"
)
APPEND_WORKFLOW_FILE = os.path.join(
    SCRIPT_DIR,
    "Minimax_auto_append_API.json"
)
STORY_FILE = os.path.join(SCRIPT_DIR, "story.txt")
BEATS_FILE = os.path.join(SCRIPT_DIR, "beats.txt")
SUBJECT_DEFINITIONS_FILE = os.path.join(
    SCRIPT_DIR,
    "subjects.txt"
)

STITCH_LIST = os.path.join(VIDEO_OUTPUT, "list.txt")
FINAL_VIDEO = os.path.join(VIDEO_OUTPUT, "final.mp4")

FRAME_RATE = 24
TRIM_FRAMES_AFTER_FIRST = 2
TRIM_SECONDS_AFTER_FIRST = TRIM_FRAMES_AFTER_FIRST / FRAME_RATE

BASE_SEED = 1

PROMPT_DIR = os.path.join(SCRIPT_DIR, "prompts")
STATE_FILE = os.path.join(SCRIPT_DIR, "generation_state.json")
CONTINUITY_MEMORY_FILE = os.path.join(SCRIPT_DIR, "continuity_memory.txt")
BEAT_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "beat_progress.txt")

COMFY_QUEUE_RETRIES = 10
COMFY_QUEUE_RETRY_DELAY = 10
COMFY_HISTORY_MAX_ERRORS = 30
COMFY_HISTORY_RETRY_DELAY = 10

# LM Studio has a ~21K-token context window in this setup.
# Keep input comfortably below that so there is room for the model's output.
LLM_INPUT_TOKEN_BUDGET = 14000
CHARS_PER_TOKEN_ESTIMATE = 3.5
TOKEN_RECAP_SIZE = 4000

# Long-run context management:
# - full source story remains available on every director call
# - a compact rolling continuity summary carries long-term state
# - only the newest few exact segment prompts are included verbatim
RECENT_SEGMENTS_MAX = 2
CONTINUITY_SUMMARY_MAX_CHARS = 1800
SUMMARY_REBUILD_BATCH_SIZE = 2

# ComfyUI workflow nodes are resolved by their exported display names. Node
# IDs are regenerated when a workflow is edited or re-exported, while these
# names remain readable and stable.
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

# ComfyUI stores nested model selections with the host operating system's path
# separator. Normalizing these fields lets one exported workflow work on both
# Windows (backslashes) and Linux (forward slashes).
WORKFLOW_PATH_INPUT_NAMES = {
    "clip_name",
    "image",
    "lora_name",
    "unet_name",
    "vae_name"
}

# ============================================================
# ARGUMENTS
# ============================================================

def normalize_command_line(arguments):
    """Accept numeric arguments separated by spaces, commas, or both."""

    normalized = []

    for argument in arguments:
        # This program has no free-form positional text, so comma splitting is
        # unambiguous. Accept ``5, 10, .2`` and ``5,10,.2`` as well as the
        # conventional ``5 10 .2`` form.
        pieces = argument.split(",")
        normalized.extend(piece.strip() for piece in pieces if piece.strip())

    return normalized


def parse_args(arguments=None):
    """Parse and validate the command-line settings for one generation run."""

    parser = argparse.ArgumentParser(
        description="Generate a complete video story using LM Studio + ComfyUI."
    )

    parser.add_argument(
        "segment_length",
        type=float,
        help="Length of each generated segment in seconds."
    )

    parser.add_argument(
        "total_length",
        type=float,
        help="Desired total story length in seconds."
    )

    parser.add_argument(
        "megapixels",
        type=float,
        help="Megapixels for the initial generated video."
    )

    parser.add_argument(
        "--resume",
        type=int,
        default=1,
        help=(
            "Resume generation at this segment number. "
            "Example: --resume 13"
        )
    )

    if arguments is None:
        arguments = sys.argv[1:]

    args = parser.parse_args(
        normalize_command_line(arguments)
    )

    if args.segment_length <= 0:
        parser.error("segment_length must be greater than 0.")

    if args.total_length <= 0:
        parser.error("total_length must be greater than 0.")

    if args.megapixels <= 0:
        parser.error("megapixels must be greater than 0.")

    if args.resume < 1:
        parser.error("--resume must be 1 or greater.")

    return args

# ============================================================
# LM STUDIO STRUCTURED OUTPUT
# ============================================================

# Rather than letting the LLM construct the complete prompt format,
# Python constructs it.
#
# This prevents the model from accidentally dumping rule headings,
# instructions, etc. into the actual MiniMax prompt.

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "video_segment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "integrated_multimodal_description": {
                    "type": "string"
                },
                "overall_soundscape": {
                    "type": "string"
                },
                "non_diegetic_music": {
                    "type": "string"
                },
                "completed_beat_ids": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 1
                    }
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


SUMMARY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "continuity_memory",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "continuity_summary": {
                    "type": "string"
                }
            },
            "required": [
                "continuity_summary"
            ],
            "additionalProperties": False
        }
    }
}


# ============================================================
# FILE HELPERS
# ============================================================

def validate_runtime_environment():
    """Fail early when required local tools or output paths are unavailable."""

    missing_tools = [
        tool_name
        for tool_name in ("ffmpeg", "ffprobe")
        if shutil.which(tool_name) is None
    ]

    if missing_tools:
        raise RuntimeError(
            "Required command-line tool(s) not found on PATH: "
            + ", ".join(missing_tools)
            + ". Install FFmpeg, open a new terminal, and try again."
        )

    if not os.path.isdir(COMFY_OUTPUT):
        raise FileNotFoundError(
            f"ComfyUI output folder not found: {COMFY_OUTPUT}\n"
            "Set MINIMAX_COMFYUI_OUTPUT to the output folder used by your "
            "ComfyUI installation."
        )


def normalize_workflow_paths(workflow):
    """Use the current operating system's separator in ComfyUI file inputs."""

    for node in workflow.values():
        if not isinstance(node, dict):
            continue

        inputs = node.get("inputs")

        if not isinstance(inputs, dict):
            continue

        for input_name in WORKFLOW_PATH_INPUT_NAMES:
            input_value = inputs.get(input_name)

            if isinstance(input_value, str):
                inputs[input_name] = input_value.replace(
                    "\\",
                    os.sep
                ).replace(
                    "/",
                    os.sep
                )

def trim_video_start(input_path, output_path, trim_seconds):
    """
    Trim the beginning of a video by a precise amount.
    Re-encodes to keep frame-accurate trimming and preserve A/V sync.
    """

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
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
    except FileNotFoundError as e:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg and make sure 'ffmpeg' "
            "is available on PATH before stitching videos."
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"FFmpeg could not trim video '{input_path}'. "
            f"The command exited with code {e.returncode}."
        ) from e
    except OSError as e:
        raise RuntimeError(
            f"Could not start FFmpeg to trim '{input_path}': {e}"
        ) from e

def load_text_file(path, required=True):
    """Read a UTF-8 text input, optionally returning empty text if absent."""

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        if required:
            raise FileNotFoundError(
                f"Required text file not found: {os.path.abspath(path)}"
            ) from None

        return ""
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not read text file '{os.path.abspath(path)}': {e}"
        ) from e


def load_workflow(path):
    """Load a ComfyUI API workflow and verify its top-level JSON shape."""

    try:
        with open(path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Workflow file not found: {os.path.abspath(path)}"
        ) from None
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Workflow '{os.path.abspath(path)}' is not valid JSON "
            f"(line {e.lineno}, column {e.colno}): {e.msg}"
        ) from e
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not read workflow '{os.path.abspath(path)}': {e}"
        ) from e

    if not isinstance(workflow, dict):
        raise RuntimeError(
            f"Workflow '{os.path.abspath(path)}' must contain a JSON "
            "object at its top level."
        )

    normalize_workflow_paths(workflow)

    return workflow


def find_workflow_node(
    workflow,
    node_name,
    workflow_label="workflow",
    expected_class_type=None
):
    """Return ``(node_id, node)`` for one uniquely named ComfyUI node."""

    if not isinstance(workflow, dict):
        raise RuntimeError(
            f"The {workflow_label} is not a valid ComfyUI workflow object."
        )

    matches = []

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue

        metadata = node.get("_meta", {})

        if not isinstance(metadata, dict):
            continue

        if metadata.get("title") == node_name:
            matches.append((node_id, node))

    if not matches:
        raise RuntimeError(
            f"The {workflow_label} is missing the ComfyUI node named "
            f"'{node_name}'. Open the workflow in ComfyUI, confirm that "
            "node's title, and export the API workflow again."
        )

    if len(matches) > 1:
        raise RuntimeError(
            f"The {workflow_label} contains {len(matches)} nodes named "
            f"'{node_name}'. Give the required node a unique title in "
            "ComfyUI and export the API workflow again."
        )

    node_id, node = matches[0]

    if (
        expected_class_type is not None
        and node.get("class_type") != expected_class_type
    ):
        raise RuntimeError(
            f"ComfyUI node '{node_name}' in the {workflow_label} has type "
            f"'{node.get('class_type')}', but '{expected_class_type}' is "
            "required."
        )

    inputs = node.get("inputs")

    if not isinstance(inputs, dict):
        raise RuntimeError(
            f"ComfyUI node '{node_name}' in the {workflow_label} does not "
            "contain a valid inputs object."
        )

    return node_id, node


def set_node_input(
    workflow,
    node_name,
    input_name,
    value,
    workflow_label,
    expected_class_type=None
):
    """Set a named input on a uniquely named ComfyUI node."""

    _, node = find_workflow_node(
        workflow,
        node_name,
        workflow_label=workflow_label,
        expected_class_type=expected_class_type
    )

    if input_name not in node["inputs"]:
        raise RuntimeError(
            f"ComfyUI node '{node_name}' in the {workflow_label} is missing "
            f"its '{input_name}' input. Export the API workflow again after "
            "checking the node configuration."
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
    """Verify one workflow link using readable node titles, never node IDs."""

    source_id, _ = find_workflow_node(
        workflow,
        source_name,
        workflow_label=workflow_label
    )
    _, destination_node = find_workflow_node(
        workflow,
        destination_name,
        workflow_label=workflow_label
    )

    connection = destination_node["inputs"].get(input_name)

    if (
        not isinstance(connection, list)
        or len(connection) != 2
        or str(connection[0]) != str(source_id)
        or connection[1] != output_index
    ):
        raise RuntimeError(
            f"'{input_name}' on ComfyUI node '{destination_name}' in the "
            f"{workflow_label} must connect to output {output_index} of "
            f"the node named '{source_name}'."
        )


def validate_workflow(workflow, workflow_label, is_append=False):
    """Validate the named nodes and connections used by the automation."""

    required_nodes = (
        (DURATION_NODE_NAME, "PrimitiveFloat"),
        (PROMPT_NODE_NAME, "DPRandomGenerator"),
        (NOISE_NODE_NAME, "RandomNoise"),
        (SAVE_VIDEO_NODE_NAME, "SaveVideo")
    )

    for node_name, class_type in required_nodes:
        find_workflow_node(
            workflow,
            node_name,
            workflow_label=workflow_label,
            expected_class_type=class_type
        )

    for node_name in REFERENCE_IMAGE_NODE_NAMES:
        find_workflow_node(
            workflow,
            node_name,
            workflow_label=workflow_label,
            expected_class_type="LoadImage"
        )

    if not is_append:
        find_workflow_node(
            workflow,
            RESOLUTION_NODE_NAME,
            workflow_label=workflow_label,
            expected_class_type="ResolutionSelector"
        )
        return

    _, image_batch_node = find_workflow_node(
        workflow,
        IMAGE_BATCH_NODE_NAME,
        workflow_label=workflow_label,
        expected_class_type="ImageBatchMulti"
    )

    find_workflow_node(
        workflow,
        LOAD_VIDEO_NODE_NAME,
        workflow_label=workflow_label,
        expected_class_type="VHS_LoadVideoPath"
    )

    # Validate the critical append chain by title. This catches silently
    # disconnected duration, prompt, source-video, conditioning, latent, and
    # output nodes even when ComfyUI regenerates every numeric node ID.
    required_append_connections = (
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

    for (
        destination_name,
        input_name,
        source_name,
        output_index
    ) in required_append_connections:
        validate_named_connection(
            workflow=workflow,
            destination_name=destination_name,
            input_name=input_name,
            source_name=source_name,
            output_index=output_index,
            workflow_label=workflow_label
        )

    # Confirm that each named image is connected to the matching batch slot,
    # so neither a node ID nor the workflow's JSON order is assumed.
    for input_name, expected_source_title in zip(
        (
            "image_1",
            "image_2",
            "image_3",
            "image_4",
            "image_5",
            "image_6"
        ),
        REFERENCE_IMAGE_NODE_NAMES
    ):
        connection = image_batch_node["inputs"].get(input_name)

        if (
            not isinstance(connection, list)
            or len(connection) != 2
            or connection[1] != 0
        ):
            raise RuntimeError(
                f"ComfyUI node '{IMAGE_BATCH_NODE_NAME}' in the "
                f"{workflow_label} has an invalid '{input_name}' connection. "
                "Connect it to output 0 of a Load Image node."
            )

        source_node = workflow.get(str(connection[0]))

        if not isinstance(source_node, dict):
            raise RuntimeError(
                f"ComfyUI node '{IMAGE_BATCH_NODE_NAME}' in the "
                f"{workflow_label} references a missing source for "
                f"'{input_name}'."
            )

        source_metadata = source_node.get("_meta", {})
        source_title = (
            source_metadata.get("title")
            if isinstance(source_metadata, dict)
            else None
        )

        if (
            source_title != expected_source_title
            or source_node.get("class_type") != "LoadImage"
        ):
            raise RuntimeError(
                f"'{input_name}' on ComfyUI node '{IMAGE_BATCH_NODE_NAME}' "
                f"in the {workflow_label} must come from a node named "
                f"'{expected_source_title}'."
            )


def load_beats(path):
    """
    Load the author's ordered story-beat checklist.

    Each non-empty, non-comment line is one required beat. Python assigns
    stable IDs B001, B002, ... in file order. The original line text is
    preserved exactly after surrounding whitespace is removed.
    """

    raw = load_text_file(
        path,
        required=True
    )

    beats = []

    for line in raw.splitlines():
        beat = line.strip()

        if not beat or beat.startswith("#"):
            continue

        beats.append(beat)

    if not beats:
        raise ValueError(
            f"'{path}' does not contain any story beats. "
            "Put one required beat on each non-empty line."
        )

    return beats


def get_beats_signature(beats):
    """
    Fingerprint the exact ordered checklist so resume state is never silently
    reused after beats.txt has changed.
    """

    canonical = "\n".join(beats)

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def normalize_completed_beat_ids(beats, completed_beat_ids):
    """
    Story beats are strictly ordered. Only a contiguous prefix can be DONE.
    If stale/corrupt state contains B001, B002, B004, B004 is discarded.
    """

    valid = set()

    for beat_id in completed_beat_ids or []:
        try:
            beat_id = int(beat_id)
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
    """Return the next required one-based beat ID, or ``None`` if finished."""

    completed = normalize_completed_beat_ids(
        beats,
        completed_beat_ids
    )

    next_id = len(completed) + 1

    if next_id > len(beats):
        return None

    return next_id


def format_beat_progress(beats, completed_beat_ids):
    """
    Build the authoritative checklist shown to the director every segment.
    """

    completed = normalize_completed_beat_ids(
        beats,
        completed_beat_ids
    )

    next_id = get_next_beat_id(
        beats,
        completed
    )

    lines = []

    for beat_id, beat_text in enumerate(
        beats,
        start=1
    ):
        if beat_id in completed:
            status = "DONE"
        elif beat_id == next_id:
            status = "NEXT"
        else:
            status = "TODO"

        lines.append(
            f"[{status}] B{beat_id:03d}: {beat_text}"
        )

    return "\n".join(lines)


def save_beat_progress(
    beats,
    completed_beat_ids,
    path=BEAT_PROGRESS_FILE
):
    """
    Save a human-readable copy of the exact checklist and current status.
    """

    completed = normalize_completed_beat_ids(
        beats,
        completed_beat_ids
    )

    next_id = get_next_beat_id(
        beats,
        completed
    )

    if next_id is None:
        next_text = "All required beats are complete."
    else:
        next_text = (
            f"B{next_id:03d}: "
            f"{beats[next_id - 1]}"
        )

    content = (
        f"Completed beats: {len(completed)}/{len(beats)}\n"
        f"Next required beat: {next_text}\n\n"
        f"{format_beat_progress(beats, completed)}\n"
    )

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not save beat progress to '{os.path.abspath(path)}': {e}"
        ) from e


def save_continuity_memory(
    continuity_summary,
    through_segment,
    path=CONTINUITY_MEMORY_FILE,
    echo=False
):
    """
    Save the compact visual/state memory in a readable text file.
    """

    summary = continuity_summary.strip()

    if not summary:
        summary = "(No compact continuity memory yet.)"

    content = (
        f"Continuity memory through segment {through_segment}\n"
        f"{'=' * 48}\n\n"
        f"{summary}\n"
    )

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not save continuity memory to "
            f"'{os.path.abspath(path)}': {e}"
        ) from e

    if echo:
        print()
        print("######## CONTINUITY MEMORY ########")
        print()
        print(content.rstrip())
        print()
        print("###### END CONTINUITY MEMORY ######")
        print()


def print_beat_progress_summary(
    beats,
    completed_beat_ids
):
    """Print a concise progress line showing the next unfinished story beat."""

    completed = normalize_completed_beat_ids(
        beats,
        completed_beat_ids
    )

    next_id = get_next_beat_id(
        beats,
        completed
    )

    if next_id is None:
        print(
            f"Story beats complete: "
            f"{len(completed)}/{len(beats)}."
        )
    else:
        print(
            f"Story beats complete: "
            f"{len(completed)}/{len(beats)}. "
            f"Next: B{next_id:03d} - "
            f"{beats[next_id - 1]}"
        )


def apply_reported_beat_completions(
    beats,
    completed_beat_ids,
    reported_beat_ids,
    segment_number,
    verbose=True
):
    """
    Advance the authoritative checklist from the director's report.

    The director may complete multiple beats in one segment, but Python only
    accepts a contiguous run beginning with the current NEXT beat. This makes
    it impossible for the LLM to silently skip required beats.
    """

    completed = normalize_completed_beat_ids(
        beats,
        completed_beat_ids
    )

    already_completed = set(completed)
    valid_reported = set()
    invalid_reported = []

    for raw_id in reported_beat_ids or []:
        if isinstance(raw_id, bool):
            invalid_reported.append(raw_id)
            continue

        try:
            beat_id = int(raw_id)
        except (TypeError, ValueError):
            invalid_reported.append(raw_id)
            continue

        if 1 <= beat_id <= len(beats):
            valid_reported.add(beat_id)
        else:
            invalid_reported.append(raw_id)

    accepted = []

    next_id = get_next_beat_id(
        beats,
        completed
    )

    while (
        next_id is not None
        and next_id in valid_reported
    ):
        completed.add(next_id)
        accepted.append(next_id)

        next_id = get_next_beat_id(
            beats,
            completed
        )

    ignored_out_of_order = sorted(
        beat_id
        for beat_id in valid_reported
        if beat_id not in already_completed
        and beat_id not in accepted
    )

    if verbose:
        if accepted:
            print(
                f"Segment {segment_number} completed beat(s): "
                + ", ".join(
                    f"B{beat_id:03d}"
                    for beat_id in accepted
                )
            )

            for beat_id in accepted:
                print(
                    f"  [DONE] B{beat_id:03d}: "
                    f"{beats[beat_id - 1]}"
                )
        else:
            print(
                f"Segment {segment_number} did not complete "
                f"the current required beat."
            )

        if ignored_out_of_order:
            print(
                "WARNING: Ignored out-of-order beat completion "
                "claim(s): "
                + ", ".join(
                    f"B{beat_id:03d}"
                    for beat_id in ignored_out_of_order
                )
            )

        if invalid_reported:
            print(
                "WARNING: Ignored invalid beat ID value(s): "
                + ", ".join(
                    repr(value)
                    for value in invalid_reported
                )
            )

    return normalize_completed_beat_ids(
        beats,
        completed
    )


def rebuild_completed_beat_ids(
    beats,
    last_completed_segment
):
    """
    Reconstruct beat progress from saved per-segment structured LLM results.
    This is used when a compatible checkpoint does not contain beat state.
    """

    completed = set()

    for segment_number in range(
        1,
        last_completed_segment + 1
    ):
        try:
            llm_result = load_saved_llm_result(
                segment_number
            )
        except (FileNotFoundError, RuntimeError, json.JSONDecodeError):
            continue

        completed = apply_reported_beat_completions(
            beats=beats,
            completed_beat_ids=completed,
            reported_beat_ids=llm_result.get(
                "completed_beat_ids",
                []
            ),
            segment_number=segment_number,
            verbose=False
        )

    return completed


# ============================================================
# LM STUDIO
# ============================================================

def ask_llm(messages, max_retries=5, retry_delay=5):
    """Request one structured segment description from LM Studio with retries."""

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{LM_STUDIO_URL}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": 0.35,
                    "max_tokens": 4000,
                    "response_format": RESPONSE_FORMAT
                },
                timeout=600
            )

            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            return json.loads(content)

        except (
            requests.RequestException,
            KeyError,
            IndexError,
            json.JSONDecodeError,
            TypeError,
            ValueError
        ) as e:
            last_error = e

            print(
                f"LLM request failed "
                f"(attempt {attempt}/{max_retries}): {e}"
            )

            if attempt < max_retries:
                print(
                    f"Retrying in {retry_delay} seconds..."
                )
                time.sleep(retry_delay)

    raise RuntimeError(
        f"LM Studio failed after {max_retries} attempts."
    ) from last_error


def ask_summary_llm(
    messages,
    max_retries=10,
    retry_delay=2
):
    """
    Small LM Studio call used only for continuity memory.

    Only visible assistant content is accepted as continuity memory.
    reasoning_content is diagnostic-only and is NEVER stored.

    Later retries allow a little more generation room in case a reasoning
    model spends most of its initial token budget before producing its
    visible final answer.
    """

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            # Start reasonably small, but give later retries more room if the
            # model burns tokens on hidden reasoning before producing content.
            summary_max_tokens = min(
                TOKEN_RECAP_SIZE + ((attempt - 1) * 500),
                4000
            )

            response = requests.post(
                f"{LM_STUDIO_URL}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": summary_max_tokens
                },
                timeout=600
            )

            response.raise_for_status()

            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]

            content = (
                message.get("content")
                or ""
            ).strip()

            # Never use reasoning_content as continuity memory. Some reasoning
            # models expose their scratch work here while leaving visible
            # content empty; saving that would poison future context.
            reasoning_content = (
                message.get("reasoning_content")
                or ""
            ).strip()

            if not content:
                finish_reason = choice.get("finish_reason")
                usage = data.get("usage", {})
                completion_tokens = usage.get(
                    "completion_tokens",
                    "unknown"
                )

                print(
                    "Continuity summary returned no visible content. "
                    f"reasoning_content characters={len(reasoning_content)}, "
                    f"finish_reason={finish_reason!r}, "
                    f"completion_tokens={completion_tokens}, "
                    f"max_tokens={summary_max_tokens}."
                )

                raise ValueError(
                    "LM Studio returned an empty visible continuity summary."
                )

            # Keep the actual stored memory small regardless of how much the
            # model generated.
            if len(content) > CONTINUITY_SUMMARY_MAX_CHARS:
                clipped = content[
                    :CONTINUITY_SUMMARY_MAX_CHARS
                ]

                last_newline = clipped.rfind("\n")

                if (
                    last_newline
                    > CONTINUITY_SUMMARY_MAX_CHARS // 2
                ):
                    clipped = clipped[:last_newline]

                content = clipped.rstrip()

            return content

        except (
            requests.RequestException,
            KeyError,
            IndexError,
            ValueError,
            TypeError,
            AttributeError,
            json.JSONDecodeError
        ) as e:
            last_error = e

            print(
                f"Continuity-summary request failed "
                f"(attempt {attempt}/{max_retries}): {e}"
            )

            if attempt < max_retries:
                print(
                    f"Retrying continuity summary in "
                    f"{retry_delay} seconds..."
                )

                time.sleep(retry_delay)

    raise RuntimeError(
        f"LM Studio continuity-summary request failed after "
        f"{max_retries} attempts."
    ) from last_error

def estimate_text_tokens(text):
    """
    Conservative token estimate that does not require a model-specific
    tokenizer. Used only to keep requests safely below the configured
    context window.
    """

    if not text:
        return 0

    return math.ceil(
        len(text) / CHARS_PER_TOKEN_ESTIMATE
    )


def estimate_message_tokens(messages):
    """Estimate total tokens for chat content plus per-message overhead."""

    # Add a little overhead per chat message for role / envelope tokens.
    return sum(
        estimate_text_tokens(message.get("content", "")) + 12
        for message in messages
    )


def update_continuity_summary(
    previous_summary,
    completed_segments
):
    """
    Merge one or more older completed segment descriptions into compact
    long-term visual/state memory.

    Plot progression is tracked separately by beats.txt and is intentionally
    not duplicated here.
    """

    if not completed_segments:
        return previous_summary

    segment_text_parts = []

    for segment_number, llm_result in completed_segments:
        continuity_payload = {
            key: value
            for key, value in llm_result.items()
            if key != "completed_beat_ids"
        }

        segment_text_parts.append(
            f"--- COMPLETED SEGMENT {segment_number} ---\n"
            + json.dumps(
                continuity_payload,
                ensure_ascii=False,
                indent=2
            )
        )

    segment_text = "\n\n".join(
        segment_text_parts
    )

    if previous_summary:
        previous_text = previous_summary
    else:
        previous_text = (
            "No older continuity state has been stored yet."
        )

    summary_messages = [
        {
            "role": "system",
            "content": (
                "You maintain compact visual/state continuity memory for a "
                "sequential AI-video director. Plot progression is tracked "
                "separately by an authoritative story-beat checklist. Do not "
                "duplicate that checklist here. Keep only persistent facts "
                "needed to make later clips visually and physically continuous. "
                "Do not invent events and do not describe future plot."
            )
        },
        {
            "role": "user",
            "content": f"""
PREVIOUS CONTINUITY MEMORY

{previous_text}

NEWLY COMPLETED OLDER SEGMENT DESCRIPTIONS

{segment_text}

Rewrite the continuity memory as VERY SHORT bullet points.

HARD LIMIT:
- Maximum 12 bullets.
- Maximum 18 words per bullet.
- Maximum {CONTINUITY_SUMMARY_MAX_CHARS} characters total.
- Do not write paragraphs.
- Do not explain anything.
- Omit anything that no longer matters.

Keep ONLY persistent continuity information a future segment might need:
- current location and important environment state
- relevant characters' current positions and physical conditions
- persistent injuries, clothing changes, dirt/blood/damage
- important carried objects or props
- speaker IDs and established voice facts
- unresolved immediate physical actions/interactions
- ongoing audio only if it must continue
- permanent visual or physical state changes

Do NOT track which plot beats are complete or still pending.
Do NOT preserve ordinary camera staging, completed dialogue, temporary
expressions, or resolved details.
Do not describe future story events.
Do not include general MiniMax instructions.\nReturn ONLY the final continuity bullet list. Do not output analysis, reasoning,\na thinking process, or commentary about these instructions.\n"""
        }
    ]

    return ask_summary_llm(
        summary_messages
    )


# ============================================================
# PROMPT CONSTRUCTION
# ============================================================

def strip_field_prefix(value, field_name):
    """
    Structured output should normally return only the field contents,
    but this protects against a model returning the label anyway.
    """

    value = value.strip()

    prefix = f"{field_name}:"

    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix):].lstrip()

    return value


def build_h3_prompt(llm_result, subject_definitions):
    """
    Construct the final MiniMax H3 prompt ourselves.

    Final format:

    subject_definitions: ...

    integrated_multimodal_description: ...

    overall_soundscape: ...

    non_diegetic_music: ...
    """

    required_fields = (
        "integrated_multimodal_description",
        "overall_soundscape",
        "non_diegetic_music"
    )

    if not isinstance(llm_result, dict):
        raise RuntimeError(
            "LM Studio returned an invalid director response; expected a "
            "JSON object."
        )

    invalid_fields = [
        field_name
        for field_name in required_fields
        if not isinstance(llm_result.get(field_name), str)
    ]

    if invalid_fields:
        raise RuntimeError(
            "LM Studio's director response is missing required text field(s): "
            + ", ".join(invalid_fields)
        )

    integrated = strip_field_prefix(
        llm_result["integrated_multimodal_description"],
        "integrated_multimodal_description"
    )

    soundscape = strip_field_prefix(
        llm_result["overall_soundscape"],
        "overall_soundscape"
    ) + "\nAll language is in English"

    music = strip_field_prefix(
        llm_result["non_diegetic_music"],
        "non_diegetic_music"
    )

    subject_text = subject_definitions.strip()

    if not subject_text:
        subject_text = "N/A"

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
    """Ask ComfyUI to release models and VRAM without aborting a good run."""

    try:
        requests.post(
            f"{COMFY_URL}/free",
            json={
                "unload_models": True,
                "free_memory": True
            },
            timeout=60
        ).raise_for_status()
    except requests.RequestException as e:
        print(
            "WARNING: ComfyUI could not release VRAM. Generation can "
            f"continue, but memory usage may remain high: {e}"
        )


def queue_workflow(
    workflow,
    max_retries=COMFY_QUEUE_RETRIES,
    retry_delay=COMFY_QUEUE_RETRY_DELAY
):
    """
    Queue a ComfyUI workflow.

    Retries transient connection/time-out/server errors. Validation errors
    such as HTTP 400 are not retried because retrying the same invalid
    workflow will not fix it.

    Note: if the POST reaches ComfyUI but the response itself is lost,
    a retry can theoretically queue a duplicate job. That is uncommon,
    but unavoidable without a server-side idempotency mechanism.
    """

    last_error = None
    client_id = str(uuid.uuid4())

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{COMFY_URL}/prompt",
                json={
                    "prompt": workflow,
                    "client_id": client_id
                },
                timeout=60
            )

            # 4xx means the submitted workflow itself was rejected.
            if 400 <= response.status_code < 500:
                raise RuntimeError(
                    f"ComfyUI rejected workflow with HTTP "
                    f"{response.status_code}:\n{response.text}"
                )

            response.raise_for_status()

            data = response.json()

            if "prompt_id" not in data:
                raise RuntimeError(
                    "ComfyUI response did not contain prompt_id:\n"
                    + json.dumps(data, indent=2)
                )

            return data["prompt_id"]

        except RuntimeError:
            raise

        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.RequestException,
            ValueError
        ) as e:
            last_error = e

            print(
                f"ComfyUI queue request failed "
                f"(attempt {attempt}/{max_retries}): {e}"
            )

            if attempt < max_retries:
                print(
                    f"Retrying ComfyUI queue request in "
                    f"{retry_delay} seconds..."
                )
                time.sleep(retry_delay)

    raise RuntimeError(
        f"ComfyUI queue request failed after "
        f"{max_retries} attempts."
    ) from last_error


def wait_for_completion(
    prompt_id,
    max_consecutive_errors=COMFY_HISTORY_MAX_ERRORS,
    retry_delay=COMFY_HISTORY_RETRY_DELAY
):
    """
    Poll ComfyUI until the queued generation finishes.

    Temporary HTTP/connection/time-out failures are retried. A generation
    that ComfyUI explicitly reports as failed is still treated as a real
    failure so the run can later be resumed from that segment.
    """

    consecutive_errors = 0

    while True:
        try:
            history_response = requests.get(
                f"{COMFY_URL}/history/{prompt_id}",
                timeout=60
            )

            history_response.raise_for_status()
            history = history_response.json()

            # A successful poll means communication is healthy again.
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
            requests.Timeout,
            requests.ConnectionError,
            requests.RequestException,
            ValueError
        ) as e:
            consecutive_errors += 1

            print(
                f"ComfyUI history check failed "
                f"({consecutive_errors}/{max_consecutive_errors}): {e}"
            )

            if consecutive_errors >= max_consecutive_errors:
                raise RuntimeError(
                    "Lost communication with ComfyUI after "
                    f"{max_consecutive_errors} consecutive failures."
                ) from e

            print(
                f"Retrying history check in {retry_delay} seconds..."
            )
            time.sleep(retry_delay)

def get_video_path(result, workflow):
    """Resolve the named Save Video node output to an existing local file."""

    if not isinstance(result, dict):
        raise RuntimeError(
            "ComfyUI returned an invalid completion result; expected a "
            "JSON object."
        )

    save_node_id, _ = find_workflow_node(
        workflow,
        SAVE_VIDEO_NODE_NAME,
        workflow_label="queued workflow",
        expected_class_type="SaveVideo"
    )

    try:
        video = result["outputs"][save_node_id]["images"][0]
        filename = video["filename"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            f"ComfyUI completed the job, but no video was reported by "
            f"the node named '{SAVE_VIDEO_NODE_NAME}':\n"
            + json.dumps(result.get("outputs", {}), indent=2)
        ) from e

    if not isinstance(video, dict):
        raise RuntimeError(
            f"The node named '{SAVE_VIDEO_NODE_NAME}' returned an invalid "
            "video record."
        )

    subfolder = video.get("subfolder", "")

    path = os.path.join(
        COMFY_OUTPUT,
        subfolder,
        filename
    )

    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"ComfyUI reported a video output, "
            f"but the file does not exist:\n{path}"
        )

    return path


def get_video_resolution(video_path):
    """Return a video's width and height using FFprobe."""

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                video_path
            ],
            capture_output=True,
            text=True,
            check=True
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "FFprobe was not found. Install FFmpeg and make sure 'ffprobe' "
            "is available on PATH."
        ) from e
    except subprocess.CalledProcessError as e:
        details = (e.stderr or "").strip() or "No error details were returned."
        raise RuntimeError(
            f"FFprobe could not inspect '{video_path}' "
            f"(exit code {e.returncode}): {details}"
        ) from e
    except OSError as e:
        raise RuntimeError(
            f"Could not start FFprobe for '{video_path}': {e}"
        ) from e

    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as e:
        raise RuntimeError(
            f"FFprobe returned no usable video resolution for "
            f"'{video_path}'."
        ) from e

    return width, height


# ============================================================
# INITIAL RESOLUTION
# ============================================================

def set_initial_megapixels(workflow, megapixels):
    """
    Set the megapixel input on the initial workflow's ResolutionSelector.

    Append generations do NOT call this function.
    """

    set_node_input(
        workflow,
        RESOLUTION_NODE_NAME,
        "megapixels",
        megapixels,
        workflow_label="initial workflow",
        expected_class_type="ResolutionSelector"
    )

    print(
        f"Initial megapixels requested: {megapixels:g} MP "
        f"(ComfyUI node '{RESOLUTION_NODE_NAME}')"
    )

# ============================================================
# WORKFLOW PREPARATION
# ============================================================

def prepare_initial_workflow(
    duration,
    megapixels,
    h3_prompt,
    segment_number
):
    """
    Segment 1:
    Minimax_auto_API.json
    """

    workflow = load_workflow(
        INITIAL_WORKFLOW_FILE
    )

    workflow_label = f"initial workflow '{INITIAL_WORKFLOW_FILE}'"
    validate_workflow(
        workflow,
        workflow_label=workflow_label,
        is_append=False
    )

    # Duration
    set_node_input(
        workflow,
        DURATION_NODE_NAME,
        "value",
        duration,
        workflow_label=workflow_label,
        expected_class_type="PrimitiveFloat"
    )

    # Prompt
    set_node_input(
        workflow,
        PROMPT_NODE_NAME,
        "text",
        h3_prompt,
        workflow_label=workflow_label,
        expected_class_type="DPRandomGenerator"
    )
    set_node_input(
        workflow,
        NOISE_NODE_NAME,
        "noise_seed",
        BASE_SEED + segment_number - 1,
        workflow_label=workflow_label,
        expected_class_type="RandomNoise"
    )

    # Initial resolution
    set_initial_megapixels(
        workflow,
        megapixels
    )

    # Output name
    set_node_input(
        workflow,
        SAVE_VIDEO_NODE_NAME,
        "filename_prefix",
        f"video/segment_{segment_number:04d}",
        workflow_label=workflow_label,
        expected_class_type="SaveVideo"
    )

    return workflow


def prepare_append_workflow(
    duration,
    h3_prompt,
    previous_video_path,
    segment_number
):
    """
    Segment 2+:
    Minimax_auto_append_API.json

    The immediately preceding generated MP4 is passed directly
    into the VHS Load Video (Path) node.
    """

    workflow = load_workflow(
        APPEND_WORKFLOW_FILE
    )

    workflow_label = f"append workflow '{APPEND_WORKFLOW_FILE}'"
    validate_workflow(
        workflow,
        workflow_label=workflow_label,
        is_append=True
    )

    # Duration
    set_node_input(
        workflow,
        DURATION_NODE_NAME,
        "value",
        duration,
        workflow_label=workflow_label,
        expected_class_type="PrimitiveFloat"
    )

    # Prompt
    set_node_input(
        workflow,
        PROMPT_NODE_NAME,
        "text",
        h3_prompt,
        workflow_label=workflow_label,
        expected_class_type="DPRandomGenerator"
    )

    # Previous video
    previous_video_path = os.path.abspath(
        previous_video_path
    )

    if not os.path.exists(previous_video_path):
        raise FileNotFoundError(
            f"Previous video does not exist:\n"
            f"{previous_video_path}"
        )

    set_node_input(
        workflow,
        LOAD_VIDEO_NODE_NAME,
        "video",
        previous_video_path,
        workflow_label=workflow_label,
        expected_class_type="VHS_LoadVideoPath"
    )

    # Output name
    set_node_input(
        workflow,
        SAVE_VIDEO_NODE_NAME,
        "filename_prefix",
        f"video/segment_{segment_number:04d}",
        workflow_label=workflow_label,
        expected_class_type="SaveVideo"
    )
    set_node_input(
        workflow,
        NOISE_NODE_NAME,
        "noise_seed",
        BASE_SEED + segment_number - 1,
        workflow_label=workflow_label,
        expected_class_type="RandomNoise"
    )

    return workflow


# ============================================================
# STITCHING
# ============================================================

def stitch_videos(video_paths):
    """
    Rewrite list.txt with generated videos in exact generation order,
    trimming the first 2 frames from every segment after the first,
    then invoke FFmpeg directly on Windows, Linux, or macOS.

    Segment 1 is left untouched.
    Segments 2+ are trimmed copies written beside their source files.
    ``stitch.bat`` remains available as an optional Windows convenience, but
    the Python program does not depend on it.
    """

    if not video_paths:
        raise RuntimeError(
            "No generated video files were available to stitch."
        )

    try:
        os.makedirs(VIDEO_OUTPUT, exist_ok=True)
    except OSError as e:
        raise RuntimeError(
            f"Could not create the video output folder "
            f"'{VIDEO_OUTPUT}': {e}"
        ) from e

    final_paths_for_stitch = []

    for i, video_path in enumerate(video_paths):
        absolute_path = os.path.abspath(video_path)

        if not os.path.exists(absolute_path):
            raise FileNotFoundError(
                f"Generated video is missing before stitching:\n"
                f"{absolute_path}"
            )

        # First segment stays untouched.
        if i == 0:
            final_paths_for_stitch.append(absolute_path)
            continue

        source_dir = os.path.dirname(absolute_path)
        source_name = os.path.basename(absolute_path)

        trimmed_name = f"trimmed_{source_name}"
        trimmed_path = os.path.join(
            source_dir,
            trimmed_name
        )

        print(
            f"Trimming first {TRIM_FRAMES_AFTER_FIRST} frames "
            f"from segment {i + 1}: {absolute_path}"
        )

        trim_video_start(
            input_path=absolute_path,
            output_path=trimmed_path,
            trim_seconds=TRIM_SECONDS_AFTER_FIRST
        )

        final_paths_for_stitch.append(trimmed_path)

    try:
        with open(STITCH_LIST, "w", encoding="utf-8") as f:
            for video_path in final_paths_for_stitch:
                ffmpeg_path = os.path.abspath(video_path).replace("\\", "/")
                ffmpeg_path = ffmpeg_path.replace("'", "'\\''")
                f.write(f"file '{ffmpeg_path}'\n")
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not write the FFmpeg stitch list '{STITCH_LIST}': {e}"
        ) from e

    print()
    print("=" * 64)
    print("STITCHING GENERATED SEGMENTS")
    print("=" * 64)
    print(f"List file:  {STITCH_LIST}")
    print(f"Final video: {FINAL_VIDEO}")
    print(f"Segments:   {len(final_paths_for_stitch)}")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", STITCH_LIST,
                "-c", "copy",
                FINAL_VIDEO
            ],
            cwd=VIDEO_OUTPUT,
            check=True
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg and make sure 'ffmpeg' "
            "is available on PATH before stitching videos."
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"FFmpeg could not stitch the generated videos (exit code "
            f"{e.returncode}). Check the generated list '{STITCH_LIST}'."
        ) from e
    except OSError as e:
        raise RuntimeError(
            f"Could not start FFmpeg to stitch the generated videos: {e}"
        ) from e

    print(f"Stitching complete: {FINAL_VIDEO}")


# ============================================================
# RESUME / STATE
# ============================================================

def get_prompt_text_path(segment_number):
    """Return the readable prompt-log path for a segment."""

    return os.path.join(
        PROMPT_DIR,
        f"segment_{segment_number:04d}.txt"
    )


def get_prompt_json_path(segment_number):
    """Return the structured LLM-result log path for a segment."""

    return os.path.join(
        PROMPT_DIR,
        f"segment_{segment_number:04d}.json"
    )


def save_prompt(segment_number, prompt):
    """Save the final human-readable MiniMax prompt for resume and review."""

    path = get_prompt_text_path(segment_number)

    try:
        os.makedirs(PROMPT_DIR, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(prompt)
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not save the prompt for segment {segment_number} to "
            f"'{path}': {e}"
        ) from e


def save_llm_result(segment_number, llm_result):
    """Save the raw structured director response used to resume safely."""

    path = get_prompt_json_path(segment_number)

    try:
        os.makedirs(PROMPT_DIR, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                llm_result,
                f,
                ensure_ascii=False,
                indent=2
            )
    except (OSError, TypeError, ValueError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not save the director response for segment "
            f"{segment_number} to '{path}': {e}"
        ) from e


def parse_saved_h3_prompt(prompt):
    """
    Recover the three LLM response fields from an older saved .txt prompt.

    New runs also save the raw structured LLM response as JSON, but this
    fallback lets resume work with prompts created before that JSON logging
    existed.
    """

    integrated_marker = "integrated_multimodal_description:"
    sound_marker = "overall_soundscape:"
    music_marker = "non_diegetic_music:"

    try:
        integrated_start = (
            prompt.index(integrated_marker)
            + len(integrated_marker)
        )

        sound_start = prompt.index(
            sound_marker,
            integrated_start
        )

        music_start = prompt.index(
            music_marker,
            sound_start
        )

    except ValueError as e:
        raise RuntimeError(
            "Could not parse a saved H3 prompt. "
            "Expected integrated_multimodal_description, "
            "overall_soundscape, and non_diegetic_music fields."
        ) from e

    return {
        "integrated_multimodal_description": (
            prompt[integrated_start:sound_start].strip()
        ),
        "overall_soundscape": (
            prompt[
                sound_start + len(sound_marker):music_start
            ].strip()
        ),
        "non_diegetic_music": (
            prompt[
                music_start + len(music_marker):
            ].strip()
        ),
        "completed_beat_ids": []
    }


def load_saved_llm_result(segment_number):
    """Load a segment's JSON result, falling back to its readable prompt."""

    json_path = get_prompt_json_path(segment_number)

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                result = json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Saved director response '{json_path}' is invalid JSON "
                f"(line {e.lineno}, column {e.colno}): {e.msg}"
            ) from e
        except (OSError, UnicodeError) as e:
            raise RuntimeError(
                f"Could not read saved director response '{json_path}': {e}"
            ) from e

        if not isinstance(result, dict):
            raise RuntimeError(
                f"Saved director response '{json_path}' must contain a "
                "JSON object."
            )

        return result

    text_path = get_prompt_text_path(segment_number)

    if not os.path.exists(text_path):
        raise FileNotFoundError(
            f"Missing saved prompt for segment {segment_number}:\n"
            f"{text_path}"
        )

    try:
        with open(text_path, "r", encoding="utf-8") as f:
            return parse_saved_h3_prompt(f.read())
    except (OSError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not read saved prompt '{text_path}': {e}"
        ) from e


def find_latest_video_for_prefix(prefix_number):
    """
    Find the newest untrimmed ComfyUI output whose filename begins with
    segment_XXXX for the supplied prefix number.
    """

    pattern = os.path.join(
        COMFY_OUTPUT,
        "**",
        f"segment_{prefix_number:04d}*.mp4"
    )

    try:
        matches = glob.glob(
            pattern,
            recursive=True
        )

        matches = [
            os.path.abspath(path)
            for path in matches
            if not os.path.basename(path).startswith("trimmed_")
        ]
    except OSError as e:
        raise RuntimeError(
            f"Could not search ComfyUI output folder '{COMFY_OUTPUT}' for "
            f"segment {prefix_number}: {e}"
        ) from e

    if not matches:
        return None

    try:
        return max(
            matches,
            key=os.path.getmtime
        )
    except OSError as e:
        raise RuntimeError(
            f"Could not inspect recovered video files for segment "
            f"{prefix_number}: {e}"
        ) from e


def bootstrap_existing_video_paths(last_completed_segment):
    """
    Recover video paths for a run created before generation_state.json existed.

    The uploaded script had an off-by-one output-name bug: logical segment 1
    was saved with a segment_0002 prefix, segment 2 with segment_0003, etc.
    This function tests both the correct naming scheme and that legacy +1
    scheme, then chooses the more recent complete set.
    """

    if last_completed_segment < 1:
        return []

    candidate_sets = []

    for label, offset in (
        ("normal", 0),
        ("legacy +1 filename offset", 1)
    ):
        paths = []
        complete = True

        for segment_number in range(
            1,
            last_completed_segment + 1
        ):
            path = find_latest_video_for_prefix(
                segment_number + offset
            )

            if path is None:
                complete = False
                break

            paths.append(path)

        if complete:
            # Prefer the candidate whose OLDEST member is newest.
            # This avoids mixing a stale segment_0001 from an older run with
            # otherwise-current files when the interrupted run used the
            # legacy +1 naming bug.
            try:
                score = min(
                    os.path.getmtime(path)
                    for path in paths
                )
            except OSError as e:
                raise RuntimeError(
                    "Could not inspect timestamps while rebuilding the "
                    f"completed video list: {e}"
                ) from e

            candidate_sets.append(
                (score, label, paths)
            )

    if not candidate_sets:
        raise FileNotFoundError(
            "Could not reconstruct the previously completed video set. "
            "Neither normal segment filenames nor the older +1 filename "
            "scheme contained every required completed segment."
        )

    candidate_sets.sort(
        key=lambda item: item[0],
        reverse=True
    )

    _, label, paths = candidate_sets[0]

    print(
        f"Recovered existing videos using: {label}"
    )

    return paths


def state_matches_run(
    state,
    segment_length,
    total_length,
    megapixels,
    total_segments
):
    """Return whether checkpoint settings describe the requested run."""

    def close_enough(a, b):
        """Compare persisted numeric settings without trusting their types."""

        try:
            return math.isclose(
                float(a),
                float(b),
                rel_tol=1e-9,
                abs_tol=1e-9
            )
        except (TypeError, ValueError):
            return False

    return (
        close_enough(
            state.get("segment_length"),
            segment_length
        )
        and close_enough(
            state.get("total_length"),
            total_length
        )
        and close_enough(
            state.get("megapixels"),
            megapixels
        )
        and state.get("total_segments") == total_segments
    )


def save_generation_state(
    video_paths,
    segment_length,
    total_length,
    megapixels,
    total_segments,
    continuity_summary="",
    continuity_summary_segment=0,
    completed_beat_ids=None,
    beats_signature=""
):
    """Atomically checkpoint generated videos, continuity, and beat progress."""

    normalized_beat_ids = set()

    for beat_id in completed_beat_ids or []:
        if isinstance(beat_id, bool):
            continue

        try:
            normalized_beat_ids.add(int(beat_id))
        except (TypeError, ValueError):
            continue

    completed_beat_ids = sorted(normalized_beat_ids)

    state = {
        "segment_length": segment_length,
        "total_length": total_length,
        "megapixels": megapixels,
        "total_segments": total_segments,
        "completed_segments": len(video_paths),
        "video_paths": [
            os.path.abspath(path)
            for path in video_paths
        ],
        "continuity_summary": continuity_summary,
        "continuity_summary_segment": continuity_summary_segment,
        "completed_beat_ids": completed_beat_ids,
        "beats_signature": beats_signature
    }

    temp_path = STATE_FILE + ".tmp"

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(
                state,
                f,
                indent=2,
                ensure_ascii=False
            )

        os.replace(
            temp_path,
            STATE_FILE
        )
    except (OSError, TypeError, ValueError, UnicodeError) as e:
        raise RuntimeError(
            f"Could not save generation checkpoint '{STATE_FILE}': {e}"
        ) from e


def rebuild_continuity_summary(last_completed_segment):
    """
    Rebuild rolling memory from saved prompt JSON/text files.

    This is mainly for old interrupted runs whose generation_state.json
    predates continuity-memory support, or for deliberately resuming from
    an earlier segment than the stored summary covers.
    """

    if last_completed_segment < 1:
        return ""

    print(
        "Rebuilding compact continuity memory from saved segment prompts..."
    )

    summary = ""

    batch_start = 1

    while batch_start <= last_completed_segment:
        batch_end = min(
            batch_start + SUMMARY_REBUILD_BATCH_SIZE - 1,
            last_completed_segment
        )

        batch = []

        for segment_number in range(
            batch_start,
            batch_end + 1
        ):
            batch.append(
                (
                    segment_number,
                    load_saved_llm_result(segment_number)
                )
            )

        summary = update_continuity_summary(
            summary,
            batch
        )

        print(
            f"Continuity memory rebuilt through "
            f"segment {batch_end}."
        )

        batch_start = batch_end + 1

    return summary


def load_resume_context(
    resume_segment,
    segment_length,
    total_length,
    megapixels,
    total_segments,
    beats,
    beats_signature
):
    """
    Restore already-generated video paths, compact continuity memory, and
    authoritative story-beat progress.

    Continuity memory is rebuilt when its stored segment marker does not match
    the requested resume point. Beat progress is also rebuilt when resuming
    earlier than the checkpoint so future beat state never leaks backward.
    """

    last_completed_segment = resume_segment - 1

    if last_completed_segment == 0:
        return [], "", set()

    state = None
    paths = None
    state_matches = False

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Generation checkpoint '{STATE_FILE}' is invalid JSON "
                f"(line {e.lineno}, column {e.colno}): {e.msg}. Restore a "
                "valid checkpoint or start a new run."
            ) from e
        except (OSError, UnicodeError) as e:
            raise RuntimeError(
                f"Could not read generation checkpoint '{STATE_FILE}': {e}"
            ) from e

        if not isinstance(state, dict):
            raise RuntimeError(
                f"Generation checkpoint '{STATE_FILE}' must contain a "
                "JSON object."
            )

        state_matches = state_matches_run(
            state,
            segment_length,
            total_length,
            megapixels,
            total_segments
        )

        if state_matches:
            candidate_paths = state.get(
                "video_paths",
                []
            )

            if len(candidate_paths) >= last_completed_segment:
                candidate_paths = candidate_paths[
                    :last_completed_segment
                ]

                missing = [
                    path
                    for path in candidate_paths
                    if not os.path.exists(path)
                ]

                if not missing:
                    paths = [
                        os.path.abspath(path)
                        for path in candidate_paths
                    ]

                    print(
                        f"Loaded {len(paths)} completed segment(s) "
                        f"from {STATE_FILE}."
                    )
                else:
                    print(
                        "Generation state exists, but one or more saved "
                        "video paths are missing. Falling back to filename "
                        "recovery."
                    )
        else:
            print(
                "Existing generation_state.json belongs to a different "
                "run. Falling back to filename recovery."
            )

    if paths is None:
        paths = bootstrap_existing_video_paths(
            last_completed_segment
        )

    # Long-term memory intentionally trails the exact-history window.
    expected_summary_segment = max(
        0,
        last_completed_segment - RECENT_SEGMENTS_MAX
    )

    continuity_summary = ""
    summary_is_valid = False

    if state is not None and state_matches:
        saved_summary = state.get(
            "continuity_summary",
            ""
        )

        saved_summary_segment = state.get(
            "continuity_summary_segment",
            0
        )

        if saved_summary_segment == expected_summary_segment:
            # An empty summary is valid while every completed segment still
            # fits inside the exact-history window.
            if saved_summary or expected_summary_segment == 0:
                continuity_summary = saved_summary
                summary_is_valid = True

                print(
                    f"Loaded continuity memory through "
                    f"segment {saved_summary_segment}."
                )

    if not summary_is_valid:
        if expected_summary_segment > 0:
            continuity_summary = rebuild_continuity_summary(
                expected_summary_segment
            )
        else:
            continuity_summary = ""

    # Beat progress is authoritative and tied to the exact beats.txt content.
    completed_beat_ids = set()
    beat_state_loaded = False

    if state is not None and state_matches:
        saved_signature = state.get(
            "beats_signature",
            ""
        )

        if saved_signature and saved_signature != beats_signature:
            raise RuntimeError(
                "beats.txt has changed since this checkpoint was created. "
                "Resuming with a different ordered beat list could repeat or "
                "skip story events. Restore the original beats.txt or start "
                "a new run."
            )

        if (
            saved_signature == beats_signature
            and state.get("completed_segments") == last_completed_segment
        ):
            completed_beat_ids = normalize_completed_beat_ids(
                beats,
                state.get(
                    "completed_beat_ids",
                    []
                )
            )
            beat_state_loaded = True

            print(
                f"Loaded story-beat progress: "
                f"{len(completed_beat_ids)}/{len(beats)} complete."
            )

    if not beat_state_loaded:
        completed_beat_ids = rebuild_completed_beat_ids(
            beats,
            last_completed_segment
        )

        print(
            f"Rebuilt story-beat progress through segment "
            f"{last_completed_segment}: "
            f"{len(completed_beat_ids)}/{len(beats)} complete."
        )

    save_generation_state(
        video_paths=paths,
        segment_length=segment_length,
        total_length=total_length,
        megapixels=megapixels,
        total_segments=total_segments,
        continuity_summary=continuity_summary,
        continuity_summary_segment=expected_summary_segment,
        completed_beat_ids=completed_beat_ids,
        beats_signature=beats_signature
    )

    return (
        paths,
        continuity_summary,
        completed_beat_ids
    )


def build_segment_request(
    segment,
    total_segments,
    segment_length,
    total_length,
    beats,
    completed_beat_ids
):
    """Build the segment-specific timing and ordered-beat instructions."""

    elapsed = (
        segment - 1
    ) * segment_length

    remaining = (
        total_length - elapsed
    )

    current_duration = min(
        segment_length,
        remaining
    )

    segments_remaining_after_current = (
        total_segments - segment
    )

    completed = normalize_completed_beat_ids(
        beats,
        completed_beat_ids
    )

    next_beat_id = get_next_beat_id(
        beats,
        completed
    )

    unfinished_beats = len(beats) - len(completed)

    if next_beat_id is None:
        beat_focus = (
            "All required story beats are already complete. "
            "Use remaining runtime only to continue or resolve the ending "
            "naturally without repeating completed beats."
        )
    else:
        beat_focus = (
            f"The authoritative NEXT required beat is "
            f"B{next_beat_id:03d}: {beats[next_beat_id - 1]} "
            f"There are {unfinished_beats} unfinished beat(s). "
            "Do not skip this beat or substantially enact later TODO beats "
            "before it is complete. A beat may span multiple segments."
        )

    if segment == 1:
        return (
            f"Create segment 1 of {total_segments}. "
            f"This segment is [Shot 1]. "
            f"The integrated_multimodal_description MUST begin with "
            f"[Shot 1]. "
            f"The CURRENT generated video is "
            f"{current_duration:g} seconds long. "
            f"Its local timeline begins at 00:00.000. "
            f"Then this MUST BE FOLLOWED BY what is defined in the "
            f"OPENING CLOTHING of the STORY. "
            f"For THIS FIRST SEGMENT ONLY, there is no preceding "
            f"video context. "
            f"Pictures 1 through 6 are subject references only. "
            f"Start with the OPENING SCENE of the STORY. "
            f"{beat_focus} "
            f"Pace the required beats naturally so the movie concludes "
            f"during segment {total_segments}."
        )

    return (
        f"Create segment {segment} of {total_segments}. "
        f"This segment is [Shot {segment}]. "
        f"The integrated_multimodal_description MUST begin with "
        f"[Shot {segment}]. "
        f"The CURRENT newly generated extension is "
        f"{current_duration:g} seconds long. "
        f"Its local timeline begins again at 00:00.000. "
        f"The complete preceding generated video, including "
        f"its visual and audio state, will be supplied directly "
        f"to MiniMax as continuation context. "
        f"Continue immediately from that prior video. "
        f"Do not recap the previous ending. "
        f"Pictures 1 through 6 remain persistent subject "
        f"references only. "
        f"{beat_focus} "
        f"There will be {segments_remaining_after_current} "
        f"segment(s) remaining after this one. "
        f"Pace the unfinished beats naturally so the movie concludes "
        f"during segment {total_segments}."
    )


def format_recent_segment(
    segment_number,
    llm_result
):
    """Format one saved director result for bounded recent-history context."""

    recent_payload = {
        key: value
        for key, value in llm_result.items()
        if key != "completed_beat_ids"
    }

    return (
        f"--- EXACT RECENT SEGMENT {segment_number} ---\n"
        + json.dumps(
            recent_payload,
            ensure_ascii=False,
            indent=2
        )
        + f"\n--- END SEGMENT {segment_number} ---"
    )


def load_recent_segment_results(
    current_segment,
    max_segments=RECENT_SEGMENTS_MAX
):
    """Load the newest exact segment results used for immediate continuity."""

    first_segment = max(
        1,
        current_segment - max_segments
    )

    results = []

    for segment_number in range(
        first_segment,
        current_segment
    ):
        results.append(
            (
                segment_number,
                load_saved_llm_result(segment_number)
            )
        )

    return results


def build_generation_messages(
    director_rules,
    story,
    beats,
    completed_beat_ids,
    continuity_summary,
    current_segment,
    total_segments,
    segment_length,
    total_length
):
    """
    Build a FRESH bounded request for every segment.

    Story progression is anchored by the author's beats.txt checklist.
    Long-term visual/state history is represented by continuity_summary, while
    only a few recent exact segment prompts are carried verbatim.
    """

    current_request = build_segment_request(
        segment=current_segment,
        total_segments=total_segments,
        segment_length=segment_length,
        total_length=total_length,
        beats=beats,
        completed_beat_ids=completed_beat_ids
    )

    if current_segment > 1 and continuity_summary:
        memory_text = continuity_summary
    else:
        memory_text = (
            "No older compact continuity memory exists yet."
        )

    beat_progress_text = format_beat_progress(
        beats,
        completed_beat_ids
    )

    recent_results = load_recent_segment_results(
        current_segment
    )

    selected_recent = []

    def make_user_content(recent_items):
        """Assemble the director's current story, memory, and task context."""

        if recent_items:
            recent_text = "\n\n".join(
                format_recent_segment(
                    segment_number,
                    llm_result
                )
                for segment_number, llm_result in recent_items
            )
        else:
            recent_text = "N/A"

        return f"""
AUTHORITATIVE STORY BEAT CHECKLIST

The checklist below controls plot progression.
[DONE] beats already happened: NEVER repeat them.
[NEXT] is the immediate required story beat.
[TODO] beats must still happen later, in listed order.
Do not skip over NEXT. A beat may take more than one segment to complete.

{beat_progress_text}


SOURCE STORY / CREATIVE BRIEF

--- STORY START ---

{story}

--- STORY END ---


ROLLING VISUAL/STATE CONTINUITY MEMORY THROUGH SEGMENT {max(0, current_segment - RECENT_SEGMENTS_MAX - 1)}

{memory_text}


RECENT EXACT GENERATED SEGMENT DESCRIPTIONS

{recent_text}


CURRENT TASK

{current_request}
"""

    # Add newest exact segments first, preserving chronological order in the
    # final prompt. Stop before the configured input budget is exceeded.
    for item in reversed(recent_results):
        tentative_recent = [
            item
        ] + selected_recent

        tentative_messages = [
            {
                "role": "system",
                "content": director_rules
            },
            {
                "role": "user",
                "content": make_user_content(
                    tentative_recent
                )
            }
        ]

        if (
            estimate_message_tokens(tentative_messages)
            <= LLM_INPUT_TOKEN_BUDGET
        ):
            selected_recent = tentative_recent

    messages = [
        {
            "role": "system",
            "content": director_rules
        },
        {
            "role": "user",
            "content": make_user_content(
                selected_recent
            )
        }
    ]

    estimated_tokens = estimate_message_tokens(
        messages
    )

    if estimated_tokens > LLM_INPUT_TOKEN_BUDGET:
        base_without_recent = [
            {
                "role": "system",
                "content": director_rules
            },
            {
                "role": "user",
                "content": make_user_content([])
            }
        ]

        base_tokens = estimate_message_tokens(
            base_without_recent
        )

        raise RuntimeError(
            "The fixed LLM context is too large even after dropping all "
            "recent exact segment history. "
            f"Estimated input: {base_tokens} tokens; configured safe "
            f"budget: {LLM_INPUT_TOKEN_BUDGET}. "
            "The beats checklist, source story, and/or director rules must "
            "be shortened, or the LM Studio context window must be increased."
        )

    return (
        messages,
        estimated_tokens,
        len(selected_recent)
    )


# ============================================================
# DIRECTOR SYSTEM PROMPT
# ============================================================

def build_director_rules(
    total_length,
    segment_length,
    total_segments,
    subject_definitions,
    beat_spacing
):
    """Build the stable system prompt that governs every director request."""

    if subject_definitions:
        subject_context = subject_definitions
    else:
        subject_context = "N/A"

    return f"""
You are directing an automatically generated movie from a supplied creative brief
and an authoritative ordered story-beat checklist.

The movie is approximately {total_length:g} seconds long, divided into
{total_segments} sequential segments of approximately {segment_length:g} seconds.

Generate exactly ONE MiniMax H3 segment description at a time.

STORY PROGRESSION

- The AUTHORITATIVE STORY BEAT CHECKLIST controls what has happened and what must happen next.
- [DONE] beats have already happened. NEVER repeat or recreate them.
- [NEXT] is the immediate required plot beat. Continue working on it until it is actually completed.
- [TODO] beats are future required events. Keep them in the listed order.
- Do not skip a NEXT beat to reach a later TODO beat.
- A beat may span multiple video segments. Do not mark it complete merely because it has started.
- The SOURCE STORY / CREATIVE BRIEF supplies characters, setting, dialogue, tone, details, and connective material.
- If the creative brief conflicts with the ordered checklist, the checklist controls plot order.
- RECENT EXACT GENERATED SEGMENTS are authoritative for immediate continuity.
- ROLLING VISUAL/STATE CONTINUITY MEMORY contains older persistent physical state.
- CURRENT TASK specifies the segment/shot to create now.
- Pace the unfinished beats so the movie concludes naturally during the final segment.
- DO NOT rush beats. Try to space beats out at one beat completion every: {beat_spacing} segments."


BEAT COMPLETION REPORTING

The JSON output includes completed_beat_ids.

- completed_beat_ids reports ONLY checklist beats fully completed by THIS newly described segment.
- Use the numeric ID from B001/B002/etc. Example: B003 is integer 3.
- If no beat becomes fully complete during this segment, return [].
- Never report a beat merely because it is mentioned, approached, started, implied, or planned.
- Never report an already-[DONE] beat.
- If multiple beats finish in one segment, they must be consecutive starting from [NEXT].
- Never report a later TODO beat while an earlier required beat remains unfinished.
- completed_beat_ids is metadata for Python only. Do not mention beat IDs or checklist status inside the MiniMax scene description.


CONTINUATION

Segment 1 begins normally.
ONLY Segment 1 (Shot 1) will describe the overall lighting and mood.
Segment 1 (Shot 1) will always describe the opening and the clothing specified in the STORY.
For later segments, MiniMax receives the complete preceding video as
visual/audio context.

Describe only the new continuation. Do not recap the previous clip.


SUBJECTS

Pictures 1-6 are persistent appearance references only.

{subject_context}

When a defined subject appears, use their name and corresponding <Picture N>.
Preserve persistent clothing, injuries, damage, props, and appearance changes.

Do not output subject_definitions; Python inserts them.

Do not reference <Picture #> or <Subject #> unless defined here.


SHOT AND TIMING

Each segment contains exactly one shot.

Segment N = [Shot N].

integrated_multimodal_description MUST begin with:

'[Shot N] Camera continues from the previous shot...' OR '[Shot N] Camera cuts to a new shot: ...'

The opening [Shot N] has no timestamp.

All later timestamps:
- use the current clip's local timeline
- must be greater than 00:00.000
- must occur before the supplied clip duration
- must leave enough time for the described action/dialogue

Never use cumulative movie timestamps.

If Shot N is divisible by 3, begin with a hard camera cut. Example: [Shot 3], [Shot 6], [Shot 9], etc., use a CUT camera shot.

Otherwise maintain or change the camera naturally.

Use camera movement liberally such as: pan, tracking, tilt, zoom, arc/orbit.

Follow explicit camera instructions in the source story if supplied.

CAMERA DECLARATION

Immediately after every opening [Shot N], explicitly state the camera setup.

Use exactly one of these two forms:

1. CONTINUATION:
[Shot N] Camera continues from the previous shot, maintaining the established framing/angle/movement. ...

2. CUT:
[Shot N] Camera cuts to a new shot: [briefly describe framing, angle, and position]. ...

Do not begin describing character action until the camera setup has been declared.

Never leave the camera transition implied.

Regardless if the camera cuts to a new shot, still follow the continuation of the last segment.

DIALOGUE

Never describe speech generically with phrases such as "they talk", "she speaks",
or "he responds". If someone speaks, write the exact dialogue.

Use exact dialogue. Format:
Character Name (S1) says: <d>[English] Actual spoken words.</d>

Keep speaker IDs consistent.
Only spoken words belong inside <d>.
Never end mid-dialogue.

LIGHTING

Never describe lighting unless described by an action, such as opening curtains, turning on a lamp, etc.
Example: 'She opened the curtains and the lighting in the room brightened'.

SOUND

overall_soundscape:
1-4 concise sentences of ambience and physical sounds.
Do not duplicate dialogue or music.

non_diegetic_music:
Prefer N/A unless background music materially benefits the scene.

Preserve ongoing audio continuity between clips.


OUTPUT

Return only the JSON fields required by the response schema.
"""


# ============================================================
# MAIN
# ============================================================

def main():
    """Run validation, generation, checkpointing, and final video stitching."""

    args = parse_args()

    # Check inexpensive local prerequisites before requesting an LLM response
    # or starting a potentially long ComfyUI render.
    validate_runtime_environment()

    segment_length = args.segment_length
    total_length = args.total_length
    megapixels = args.megapixels
    resume_segment = args.resume

    total_segments = math.ceil(
        total_length / segment_length
    )

    if resume_segment > total_segments:
        segment_word = "segment" if total_segments == 1 else "segments"
        raise ValueError(
            f"Cannot resume at segment {resume_segment}; "
            f"this run contains only {total_segments} {segment_word}."
        )

    # --------------------------------------------------------
    # LOAD INPUT FILES
    # --------------------------------------------------------

    story = load_text_file(
        STORY_FILE,
        required=True
    )

    beats = load_beats(
        BEATS_FILE
    )

    beat_spacing = math.floor(total_segments / len(beats))

    beats_signature = get_beats_signature(
        beats
    )

    print()
    print("=" * 64)
    print("H3 AUTOMATED DIRECTOR")
    print("=" * 64)
    print(f"Segment length:       {segment_length:g} seconds")
    print(f"Total story length:   {total_length:g} seconds")
    print(f"Total segments:       {total_segments}")
    print(f"Initial megapixels:   {megapixels:g}")
    print(f"Resume segment:       {resume_segment}")
    print(f"Initial workflow:     {INITIAL_WORKFLOW_FILE}")
    print(f"Append workflow:      {APPEND_WORKFLOW_FILE}")
    print(f"Beat Spacing:         {beat_spacing}")
    print("=" * 64)

    print(
        f"Loaded {len(beats)} required story beat(s) "
        f"from '{BEATS_FILE}'."
    )

    subject_definitions = load_text_file(
        SUBJECT_DEFINITIONS_FILE,
        required=False
    )

    if subject_definitions:
        print(
            f"Loaded subject definitions from "
            f"'{SUBJECT_DEFINITIONS_FILE}'."
        )
    else:
        print(
            f"No subject definitions found in "
            f"'{SUBJECT_DEFINITIONS_FILE}'."
        )

    # --------------------------------------------------------
    # VALIDATE WORKFLOW FILES
    # --------------------------------------------------------

    initial_test = load_workflow(
        INITIAL_WORKFLOW_FILE
    )

    append_test = load_workflow(
        APPEND_WORKFLOW_FILE
    )

    validate_workflow(
        initial_test,
        workflow_label=f"initial workflow '{INITIAL_WORKFLOW_FILE}'",
        is_append=False
    )
    validate_workflow(
        append_test,
        workflow_label=f"append workflow '{APPEND_WORKFLOW_FILE}'",
        is_append=True
    )

    del initial_test
    del append_test

    print("Workflow validation passed.")

    # --------------------------------------------------------
    # DIRECTOR SYSTEM PROMPT
    # --------------------------------------------------------

    director_rules = build_director_rules(
        total_length=total_length,
        segment_length=segment_length,
        total_segments=total_segments,
        subject_definitions=subject_definitions,
        beat_spacing=beat_spacing
    )

    # --------------------------------------------------------
    # START NEW RUN OR RESTORE RESUME STATE
    # --------------------------------------------------------

    if resume_segment == 1:
        generated_video_paths = []
        previous_video_path = None
        continuity_summary = ""
        continuity_summary_segment = 0
        completed_beat_ids = set()

        # Starting a new run intentionally resets persistent run state.
        for reset_path in (
            STATE_FILE,
            CONTINUITY_MEMORY_FILE,
            BEAT_PROGRESS_FILE
        ):
            if os.path.exists(reset_path):
                try:
                    os.remove(reset_path)
                except OSError as e:
                    raise RuntimeError(
                        f"Could not reset previous run state "
                        f"'{reset_path}': {e}"
                    ) from e

    else:
        print()
        print("=" * 64)
        print(f"RESUMING AT SEGMENT {resume_segment}")
        print("=" * 64)

        (
            generated_video_paths,
            continuity_summary,
            completed_beat_ids
        ) = load_resume_context(
            resume_segment=resume_segment,
            segment_length=segment_length,
            total_length=total_length,
            megapixels=megapixels,
            total_segments=total_segments,
            beats=beats,
            beats_signature=beats_signature
        )

        previous_video_path = generated_video_paths[-1]
        continuity_summary_segment = max(
            0,
            (resume_segment - 1) - RECENT_SEGMENTS_MAX
        )

        print(
            f"Restored {resume_segment - 1} completed segment(s)."
        )
        print(
            f"Previous continuation video: "
            f"{previous_video_path}"
        )
        print(
            f"Continuity memory characters: "
            f"{len(continuity_summary)}"
        )

    save_beat_progress(
        beats,
        completed_beat_ids
    )

    save_continuity_memory(
        continuity_summary,
        continuity_summary_segment,
        echo=bool(continuity_summary)
    )

    print_beat_progress_summary(
        beats,
        completed_beat_ids
    )

    print(
        f"Readable beat checklist: {BEAT_PROGRESS_FILE}"
    )
    print(
        f"Readable continuity memory: {CONTINUITY_MEMORY_FILE}"
    )

    # --------------------------------------------------------
    # GENERATION LOOP
    # --------------------------------------------------------

    segment = resume_segment
    run_start_time = time.perf_counter()

    # One background worker is enough because continuity updates are strictly
    # ordered: each new compact memory depends on the previous one. The worker
    # lets the LM Studio continuity call run while ComfyUI renders the current
    # segment instead of serializing those two expensive operations.
    continuity_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="continuity"
    )

    while segment <= total_segments:
        continuity_future = None
        continuity_target_segment = None
        elapsed = (
            segment - 1
        ) * segment_length

        remaining = (
            total_length - elapsed
        )

        current_duration = min(
            segment_length,
            remaining
        )

        print()
        print("=" * 64)
        print(
            f"SEGMENT {segment}/{total_segments} "
            f"({current_duration:g} seconds)"
        )
        print("=" * 64)

        # ----------------------------------------------------
        # LLM
        # ----------------------------------------------------

        print()
        print("Requesting segment description from LM Studio...")

        (
            messages,
            estimated_context_tokens,
            recent_segments_included
        ) = build_generation_messages(
            director_rules=director_rules,
            story=story,
            beats=beats,
            completed_beat_ids=completed_beat_ids,
            continuity_summary=continuity_summary,
            current_segment=segment,
            total_segments=total_segments,
            segment_length=segment_length,
            total_length=total_length
        )

        print(
            f"Estimated LLM input context: "
            f"{estimated_context_tokens}/{LLM_INPUT_TOKEN_BUDGET} tokens "
            f"(recent exact segments included: "
            f"{recent_segments_included})"
        )

        llm_result = ask_llm(
            messages
        )

        reported_beat_ids = llm_result.get(
            "completed_beat_ids",
            []
        )

        print(
            "Director-reported beat completions for this segment: "
            + (
                ", ".join(
                    f"B{int(beat_id):03d}"
                    for beat_id in reported_beat_ids
                    if isinstance(beat_id, int)
                    and not isinstance(beat_id, bool)
                )
                if reported_beat_ids
                else "none"
            )
        )

        h3_prompt = build_h3_prompt(
            llm_result,
            subject_definitions
        )

        save_prompt(
            segment,
            h3_prompt
        )

        save_llm_result(
            segment,
            llm_result
        )

        print()
        print(h3_prompt)
        print()

        # ----------------------------------------------------
        # PREPARE CORRECT COMFY WORKFLOW
        # ----------------------------------------------------

        if segment == 1:
            print(
                f"Using initial workflow: "
                f"{INITIAL_WORKFLOW_FILE}"
            )

            workflow = prepare_initial_workflow(
                duration=current_duration,
                megapixels=megapixels,
                h3_prompt=h3_prompt,
                segment_number=segment
            )

        else:
            if previous_video_path is None:
                raise RuntimeError(
                    "No previous video is available for append generation."
                )

            print(
                f"Using append workflow: "
                f"{APPEND_WORKFLOW_FILE}"
            )

            print(
                f"Previous video input: "
                f"{previous_video_path}"
            )

            workflow = prepare_append_workflow(
                duration=current_duration,
                h3_prompt=h3_prompt,
                previous_video_path=previous_video_path,
                segment_number=segment
            )

        # ----------------------------------------------------
        # COMFY GENERATION
        # ----------------------------------------------------

        print("Queuing ComfyUI workflow...")

        prompt_id = queue_workflow(
            workflow
        )

        print(
            f"ComfyUI prompt ID: {prompt_id}"
        )

        # Start the continuity-memory fold as soon as ComfyUI is rendering.
        # The segment being folded is already older than the exact-history
        # window, so its saved LLM result is available before this render.
        # This safely overlaps the LM Studio summary call with GPU generation.
        segment_to_summarize = segment - RECENT_SEGMENTS_MAX

        if segment_to_summarize >= 1:
            print(
                f"Starting background continuity update with segment "
                f"{segment_to_summarize} while ComfyUI renders..."
            )

            old_llm_result = load_saved_llm_result(
                segment_to_summarize
            )

            continuity_target_segment = segment_to_summarize
            continuity_future = continuity_executor.submit(
                update_continuity_summary,
                continuity_summary,
                [
                    (
                        segment_to_summarize,
                        old_llm_result
                    )
                ]
            )
        else:
            print(
                "Continuity memory update not needed yet; "
                "all completed segments remain in exact history."
            )

        comfy_result = wait_for_completion(
            prompt_id
        )

        video_path = get_video_path(
            comfy_result,
            workflow
        )

        print(
            f"Created: {video_path}"
        )

        width, height = get_video_resolution(
            video_path
        )

        actual_megapixels = (
            width * height / 1_000_000
        )

        print(
            f"Actual video resolution: "
            f"{width} x {height} pixels "
            f"({actual_megapixels:.3f} MP)"
        )

        # Only checkpoint a segment AFTER ComfyUI successfully produced it.
        generated_video_paths.append(
            video_path
        )

        previous_video_path = video_path

        # Beat progress advances only after ComfyUI successfully creates the
        # segment. Python enforces strict checklist order and refuses skips.
        completed_beat_ids = apply_reported_beat_completions(
            beats=beats,
            completed_beat_ids=completed_beat_ids,
            reported_beat_ids=reported_beat_ids,
            segment_number=segment,
            verbose=True
        )

        save_beat_progress(
            beats,
            completed_beat_ids
        )

        print_beat_progress_summary(
            beats,
            completed_beat_ids
        )

        # First checkpoint the completed MP4 immediately. If the separate
        # continuity-summary call fails, resume can rebuild that summary from
        # the already-saved per-segment prompt instead of regenerating video.
        # The saved summary marker reflects only the older segments that have
        # actually been folded into compact memory.
        save_generation_state(
            video_paths=generated_video_paths,
            segment_length=segment_length,
            total_length=total_length,
            megapixels=megapixels,
            total_segments=total_segments,
            continuity_summary=continuity_summary,
            continuity_summary_segment=continuity_summary_segment,
            completed_beat_ids=completed_beat_ids,
            beats_signature=beats_signature
        )

        # Print out elapsed time

        elapsed_seconds = time.perf_counter() - run_start_time

        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)

        print(
            f"Cumulative runtime: "
            f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        )

        # Collect the background continuity update only after ComfyUI has
        # finished. In the usual case the LLM summary is already complete, so
        # this adds little or no wall-clock time. We still wait here before the
        # next director request because that request must see the newest memory.
        if continuity_future is not None:
            if not continuity_future.done():
                print(
                    "ComfyUI finished before the continuity update; "
                    "waiting for background continuity memory..."
                )
            else:
                print(
                    "Background continuity update finished during "
                    "ComfyUI rendering."
                )

            try:
                continuity_summary = continuity_future.result()
            except Exception as e:
                raise RuntimeError(
                    f"The background continuity update for segment "
                    f"{continuity_target_segment} failed: {e}"
                ) from e
            continuity_summary_segment = continuity_target_segment

            print(
                f"Continuity memory updated through segment "
                f"{continuity_summary_segment} "
                f"({len(continuity_summary)} characters)."
            )

            save_continuity_memory(
                continuity_summary,
                continuity_summary_segment,
                echo=True
            )

        save_generation_state(
            video_paths=generated_video_paths,
            segment_length=segment_length,
            total_length=total_length,
            megapixels=megapixels,
            total_segments=total_segments,
            continuity_summary=continuity_summary,
            continuity_summary_segment=continuity_summary_segment,
            completed_beat_ids=completed_beat_ids,
            beats_signature=beats_signature
        )

        # free up VRAM every 5 segments
        if segment % 5 == 0:
            free_vram()

        # ----------------------------------------------------
        # FINISHED?
        # ----------------------------------------------------
        
        if segment >= total_segments:
            free_vram()

            print()
            print("=" * 64)
            print("TARGET RUNTIME COMPLETE")
            print("=" * 64)
            print(
                f"Last generated output: "
                f"{previous_video_path}"
            )

            remaining_beat_ids = [
                beat_id
                for beat_id in range(
                    1,
                    len(beats) + 1
                )
                if beat_id not in completed_beat_ids
            ]

            if remaining_beat_ids:
                print()
                print(
                    "WARNING: Target runtime ended with unfinished "
                    "required story beats:"
                )

                for beat_id in remaining_beat_ids:
                    print(
                        f"  [TODO] B{beat_id:03d}: "
                        f"{beats[beat_id - 1]}"
                    )
            else:
                print(
                    f"All {len(beats)} required story beats "
                    f"were marked complete."
                )

            stitch_videos(
                generated_video_paths
            )

            break

        # ----------------------------------------------------
        # NEXT SEGMENT
        # ----------------------------------------------------

        segment += 1

    continuity_executor.shutdown(wait=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "\nGeneration cancelled by the user. Completed segments remain "
            "available for resume.",
            file=sys.stderr
        )
        raise SystemExit(130) from None
    except Exception as e:
        # Keep the default console output approachable. Developers can opt in
        # to the original traceback while diagnosing an unexpected problem.
        error_text = str(e).strip() or (
            f"{type(e).__name__} occurred without additional details."
        )

        print("\n" + "=" * 64, file=sys.stderr)
        print("MINIMAX VIDEO GENERATION STOPPED", file=sys.stderr)
        print("=" * 64, file=sys.stderr)
        print(f"Error: {error_text}", file=sys.stderr)
        print(
            "Any completed segments and checkpoints were left in place. "
            "Fix the issue above, then use --resume with the next segment.",
            file=sys.stderr
        )

        if os.environ.get("MINIMAX_DEBUG"):
            raise

        print(
            "For a full technical traceback, set MINIMAX_DEBUG=1 and run "
            "the same command again.",
            file=sys.stderr
        )
        raise SystemExit(1) from None
