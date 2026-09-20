"""Small, deterministic prompt-variant harness for captured H3 segments.

This module deliberately contains no LLM calls and no scoring logic.  It is
used by ``run_prompt_experiment.py`` and can also be imported by unit tests.
"""

import copy
import hashlib
import json
import os
import re
from pathlib import Path


SCHEMA_VERSION = 1
VARIANT_NAMES = ("A_current", "B_raw_scene", "C_action_only", "D_compact")
_TIMESTAMP_RE = re.compile(
    r"(?=At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds)?\s*,?)",
    re.IGNORECASE,
)
_SHOT_PREFIX_RE = re.compile(r"^\s*\[\s*Shot\s+1\s*\]\s*", re.IGNORECASE)
_FIELD_PREFIX_RE = re.compile(
    r"^\s*(?:detailed_description|overall_soundscape|non_diegetic_music)\s*:\s*",
    re.IGNORECASE,
)


class FixtureError(ValueError):
    """A captured fixture is missing required reproducibility data."""


def load_fixture(path):
    path = Path(path).resolve()
    try:
        with path.open("r", encoding="utf-8") as handle:
            fixture = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureError(f"Could not read fixture {path}: {error}") from error
    validate_fixture(fixture)
    fixture["_fixture_path"] = str(path)
    return fixture


def validate_fixture(fixture):
    if not isinstance(fixture, dict):
        raise FixtureError("Fixture must be a JSON object.")
    if fixture.get("schema_version") != SCHEMA_VERSION:
        raise FixtureError(
            f"Unsupported fixture schema: {fixture.get('schema_version')!r}."
        )
    segment = fixture.get("segment")
    inputs = fixture.get("inputs")
    render = fixture.get("render")
    if not isinstance(segment, dict) or not isinstance(inputs, dict):
        raise FixtureError("Fixture must contain segment and inputs objects.")
    if not isinstance(render, dict):
        raise FixtureError("Fixture must contain a render object.")
    try:
        if int(segment["number"]) <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise FixtureError("segment.number must be a positive integer.") from error
    for key in ("raw_scene", "subject_definitions"):
        if not isinstance(inputs.get(key), str):
            raise FixtureError(f"inputs.{key} must be a string.")
    request2 = inputs.get("request2_result")
    if not isinstance(request2, dict):
        raise FixtureError("inputs.request2_result must be an object.")
    if not isinstance(inputs.get("final_h3_prompt"), str):
        raise FixtureError("inputs.final_h3_prompt must be a string.")
    if render.get("workflow_type") not in {"initial", "append", "clean_refresh"}:
        raise FixtureError("render.workflow_type is invalid or missing.")
    if not isinstance(render.get("duration"), (int, float)):
        raise FixtureError("render.duration must be numeric.")
    if not isinstance(render.get("steps"), int):
        raise FixtureError("render.steps must be an integer.")
    return fixture


def _clean_text(value):
    text = str(value or "").replace("\r\n", "\n").strip()
    text = _FIELD_PREFIX_RE.sub("", text, count=1)
    return text.strip()


def _strip_shot_prefix(value):
    return _SHOT_PREFIX_RE.sub("", _clean_text(value), count=1).strip()


def _mode_prefix(mode):
    if mode == "append":
        return "[Shot 1] Continuing directly from the final state of <Video 1>."
    if mode == "clean_refresh":
        return (
            "[Shot 1] The opening composition is already established by the "
            "supplied first frame. Continue directly from that frame."
        )
    return "[Shot 1]"


def _assemble_action_prompt(subject_definitions, description, mode):
    description = _strip_shot_prefix(description)
    prefix = _mode_prefix(mode)
    if prefix == "[Shot 1]":
        body = f"[Shot 1] {description}".strip()
    elif description:
        body = f"{prefix} {description}".strip()
    else:
        body = prefix
    sections = []
    if str(subject_definitions or "").strip():
        sections.append(f"subject_definitions: {subject_definitions.strip()}")
    sections.append(f"detailed_description: {body}")
    return "\n\n".join(sections)


def _action_only_description(value):
    """Remove only known formatter labels, retaining semantic action prose."""
    text = _clean_text(value)
    text = re.sub(r"(?im)^\s*retention_analysis\s*:\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compact_description(value):
    """Return a conservative timestamp-block compaction or a skip reason."""
    text = _strip_shot_prefix(value)
    parts = [part.strip() for part in _TIMESTAMP_RE.split(text) if part.strip()]
    if len(parts) < 2:
        return None, "no opening text plus timestamped action blocks were found"

    opening_match = re.search(r"[.!?](?:[\"'’”)]*)?(?:\s|$)", parts[0])
    if opening_match is None:
        return None, "opening text has no safe sentence boundary"
    opening = parts[0][:opening_match.end()].strip()
    actions = []
    for part in parts[1:]:
        part = re.sub(r"^\s*[,;:]\s*", "", part).strip()
        if not part:
            return None, "a timestamped block was empty"
        actions.append(part)
    if not actions:
        return None, "no timestamped actions remained after compaction"
    return " ".join([opening, "\n\n".join(actions)]), ""


def build_variant_prompts(fixture):
    validate_fixture(fixture)
    inputs = fixture["inputs"]
    mode = fixture["segment"].get("conditioning_mode") or "initial"
    subject_definitions = inputs.get("subject_definitions", "")
    request2 = inputs["request2_result"]
    variants = {
        "A_current": inputs["final_h3_prompt"],
        "B_raw_scene": _assemble_action_prompt(
            subject_definitions,
            inputs["raw_scene"],
            mode,
        ),
        "C_action_only": _assemble_action_prompt(
            subject_definitions,
            _action_only_description(request2.get("detailed_description", "")),
            mode,
        ),
    }
    compact, reason = _compact_description(
        request2.get("detailed_description", "")
    )
    if compact is None:
        variants["D_compact"] = {
            "status": "skipped",
            "reason": reason,
        }
    else:
        variants["D_compact"] = _assemble_action_prompt(
            subject_definitions,
            compact,
            mode,
        )
    return variants


def prompt_sha256(prompt):
    return hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()


def review_template(variant_names=VARIANT_NAMES):
    return {
        name: {
            "action_accuracy": None,
            "continuity": None,
            "motion_quality": None,
            "visual_coherence": None,
            "notes": "",
        }
        for name in variant_names
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def resolve_fixture_path(fixture, value):
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = Path(fixture.get("_fixture_path", ".")).resolve().parent / path
    return str(path.resolve())

