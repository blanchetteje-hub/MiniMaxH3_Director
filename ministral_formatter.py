"""Deterministic formatting and validation for MiniMax H3 prompt fields.

This module deliberately has no network or project dependencies.  Formatting
repairs representation mistakes that can be corrected without authoring story
content.  Validation reports the remaining structural or semantic problems so
the caller can decide whether a new model response is required.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from formatter_base import BaseFormatter


DESCRIPTION = "detailed_description"
LEGACY_DESCRIPTION = "integrated_multimodal_description"
SOUNDSCAPE = "overall_soundscape"
MUSIC = "non_diegetic_music"
COMPLETIONS = "completed_beat_ids"
CORE_FIELDS = (DESCRIPTION, SOUNDSCAPE, MUSIC, COMPLETIONS)
MAX_FORMAT_PASSES = 8

_LABEL = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?"
    r"(detailed_description|integrated_multimodal_description|overall_soundscape|"
    r"non_diegetic_music|completed_beat_ids)\s*:\s*(?:\*\*)?"
)
_SHOT = re.compile(r"\[\s*Shot\s+\d+\s*\]", re.IGNORECASE)
_ALIGNMENT = re.compile(
    r"(?is)^\s*(?:For the target video,\s*at\s*0(?:\.0+)?\s*seconds.*?"
    r"is fully referenced\.|How the reference pictures align with the target "
    r"video.*?(?:\.|\n))\s*"
)
_OPENING_TIME = re.compile(
    r"(?i)^\s*(?:At\s+)?(?:00?:)?00(?:\.0+)?(?:\s*seconds?)?\s*[,;:\-]?\s*"
)
_ANY_LOCAL_TIME = re.compile(
    r"(?i)^\s*(?:At\s+)?\d{1,2}:\d{2}(?:\.\d+)?\s*[,;:\-]?\s*"
)
_LOCAL_TIME = re.compile(
    r"(?i)(?<![\w:])(?:at\s+)?(?P<minutes>\d{1,2}):"
    r"(?P<seconds>\d{2})(?:(?P<separator>[.:])(?P<fraction>\d{1,3}))?"
    r"(?:\s+seconds?)?\s*[,;:\-]?\s*"
)
_ZERO_LOCAL_TIME = re.compile(
    r"(?i)(?<![\w:])(?:at\s+)?(?:\d{1,2}:00(?:[.:]0{1,3})?|"
    r"0+\.0{1,3})(?:\s+seconds?)?\s*[,;:\-]?\s*"
)
_CONTINUATION_OPENING = re.compile(
    r"(?is)^\s*(?:At\s+\d{1,2}:\d{2}(?:[.:]\d{1,3})?"
    r"(?:\s+seconds?)?\s*[,;:\-]?\s*)?"
    r"Camera\s+continues\s+(?:seamlessly\s+)?from\s+the\s+previous\s+shot"
    r"(?:\s*(?:At\s+\d{1,2}:\d{2}(?:[.:]\d{1,3})?"
    r"(?:\s+seconds?)?\s*[,;:\-]?))?\s*[,.:;\-]?\s*"
)
_CONFLICTING_CONTINUATION = re.compile(
    r"(?is)^\s*(?:At\s+00:00\.000(?:\s+seconds?)?\s*[,;:\-]?\s*)?"
    r"camera\s+continues\s+from\s+the\s+previous\s+shot\s*[.!]?\s*"
)
_TRAILING_PARENTHESIZED_TIME = re.compile(
    r"(?P<boundary>^|(?<=[.!?])\s+)"
    r"(?P<transition>Camera\s+(?:cuts\s+to\s+a\s+new\s+shot|"
    r"continues\s+from\s+the\s+previous\s+shot)\s*[:.,-]?\s*)?"
    r"(?P<action>[^.!?\n]*?\S)\s*"
    r"\(\s*(?P<minutes>\d{1,2}):(?P<seconds>\d{2})"
    r"[.:](?P<milliseconds>\d{1,3})\s*\)"
    r"(?P<punct>[.!?])",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _clean_space(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(
        r"\b(?P<word>[\w]+)\s+(?P<suffix>['’](?:s|d|m|re|ve|ll|t))\b",
        r"\g<word>\g<suffix>",
        value,
        flags=re.I,
    )
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{2,}", " ", value)
    return value.strip()


def _format_local_timestamp(match: re.Match[str]) -> str:
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    fraction = (match.group("fraction") or "0").ljust(3, "0")
    prefix = "\n" if match.start() > 0 else ""
    return f"{prefix}At {minutes:02d}:{seconds:02d}.{fraction}, "



def _format_continuation_opening(description: str) -> str:
    """Remove the obsolete generic continuation phrase from an opening.

    Physical camera continuity must be expressed by the actual camera movement
    chosen for the active beat.  The formatter must never inject or preserve
    the generic phrase "Camera continues from the previous shot" because that
    phrase encourages a static composition and contradicts the director rules.
    """
    match = _CONTINUATION_OPENING.match(description)
    if match is None:
        return description
    remainder = description[match.end():].lstrip(" ,;:-")
    if re.match(r"^['\u2019]s\b", remainder, re.I):
        remainder = re.sub(
            r"^['\u2019]s\s+final\s+frame\s+with\s+",
            "The camera resumes from the previous final frame with ",
            remainder,
            count=1,
            flags=re.I,
        )
    return remainder.rstrip()

def _strip_markdown(value: str) -> str:
    """Remove presentation-only Markdown emphasis without touching field names."""

    # MiniMax consumes prose rather than Markdown.  Ministral commonly wraps a
    # whole camera direction or dialogue attribution in one or two asterisks;
    # an asterisk has no useful prompt meaning here, so removing the marker is
    # safer and more complete than trying to balance malformed pairs.
    return value.replace("*", "")


def _replace_unsupported_dashes(value: str) -> str:
    """Replace dash glyphs that MiniMax H3 does not parse reliably."""

    value = value.replace("\u2014", ", ").replace("â€”", ", ")
    value = re.sub(r"\s*,\s*,\s*", ", ", value)
    value = re.sub(r",\s*([,.;:!?])", r"\1", value)
    return _clean_space(value)


def _strip_fence(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^```(?:json|text)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _strip_field_prefix(value: str, field: str) -> str:
    value = _strip_fence(str(value)).strip()
    pattern = re.compile(
        rf"^\s*(?:(?:#{{1,6}}\s*)|(?:[-*]\s*))?(?:\*\*)?"
        rf"{re.escape(field)}\s*:\s*(?:\*\*)?",
        re.IGNORECASE,
    )
    previous = None
    while previous != value:
        previous = value
        value = pattern.sub("", value, count=1).strip()
    return _clean_space(_strip_markdown(value.replace("```", "")))


def _parse_labeled_text(text: str) -> dict[str, Any]:
    matches = list(_LABEL.finditer(text))
    if not matches:
        raise ValueError("Ministral response is neither JSON nor labeled H3 fields.")
    parsed: dict[str, Any] = {}
    for index, match in enumerate(matches):
        field = match.group(1).lower()
        if field == LEGACY_DESCRIPTION:
            field = DESCRIPTION
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        if field == COMPLETIONS:
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                value = re.findall(r"(?i)B?\d+", value)
        parsed[field] = value
    return parsed


def _coerce_result(llm_result: Any) -> dict[str, Any]:
    if isinstance(llm_result, Mapping):
        result = copy.deepcopy(dict(llm_result))
    elif isinstance(llm_result, (str, bytes, bytearray)):
        raw = llm_result.decode("utf-8", errors="replace") if not isinstance(llm_result, str) else llm_result
        raw = _strip_fence(raw)
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            result = _parse_labeled_text(raw)
        else:
            if not isinstance(decoded, dict):
                raise ValueError("Ministral JSON response must be an object.")
            result = decoded
    else:
        raise TypeError("Ministral response must be a mapping or text.")

    if DESCRIPTION not in result and LEGACY_DESCRIPTION in result:
        result[DESCRIPTION] = result[LEGACY_DESCRIPTION]

    # Some models put the entire labeled prompt in the description field.
    description = result.get(DESCRIPTION)
    if isinstance(description, str) and len(_LABEL.findall(description)) > 1:
        spill = _parse_labeled_text(description)
        result.update(spill)

    normalized: dict[str, Any] = {}
    for field in (DESCRIPTION, SOUNDSCAPE, MUSIC):
        value = result.get(field, "")
        normalized[field] = value if isinstance(value, str) else str(value or "")
    normalized[COMPLETIONS] = copy.deepcopy(result.get(COMPLETIONS, []))
    return normalized


def _segment_number(context: Mapping[str, Any]) -> int:
    raw = context.get("segment_number", context.get("shot_number", 1))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _next_beat_id(context: Mapping[str, Any]) -> int | None:
    raw = context.get("next_beat_id", context.get("current_beat_id"))
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _subject_records(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = str(context.get("subject_definitions", "") or "")
    records: dict[str, dict[str, Any]] = {}
    for match in re.finditer(
        r"(?im)^\s*<Subject\s+(?P<subject>\d+)>\s*(?:is\s+)?"
        r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)\s*,\s*"
        r".*?\b(?:created|established)\s+(?:by\s+<Video\s+1>|"
        r"in\s+generated\s+"
        r"video\s+segment\s+\d+).*?\.?\s*$",
        definitions,
    ):
        name = match.group("name").strip()
        records[name] = {
            "subject_id": int(match.group("subject")),
            "picture_ids": [],
            "picture_id": None,
            "speaker_id": f"S{match.group('subject')}",
        }
    for match in re.finditer(
        r"(?im)^\s*<Subject\s+(?P<subject>\d+)>\s*(?:is\s+)?"
        r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)\s*,\s*"
        r".*?(?P<pictures>(?:<Picture\s+\d+>\s*(?:,?\s*(?:and\s+)?)*?)+)"
        r"(?:.*?\(?S(?P<speaker>\d+)\)?)?\s*\.?\s*$",
        definitions,
    ):
        name = match.group("name").strip()
        picture_ids = list(dict.fromkeys(
            int(value) for value in re.findall(
                r"(?i)<Picture\s+(\d+)>",
                match.group("pictures"),
            )
        ))
        records[name] = {
            "subject_id": int(match.group("subject")),
            "picture_ids": picture_ids,
            "picture_id": picture_ids[0],
            "speaker_id": (
                f"S{match.group('speaker')}"
                if match.group("speaker") else None
            ),
        }
        if records[name]["speaker_id"] is None:
            records[name]["speaker_id"] = f"S{records[name]['subject_id']}"
    for match in re.finditer(
        r"(?im)^\s*(?:<\s*)?Picture\s+(?P<picture>\d+)\s*(?:>\s*)?"
        r"(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
        r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)"
        r"(?:\s+and\s+aligns\s+with\s+the\s+\d+(?:\.\d+)?-second\s+"
        r"mark\s+of\s+the\s+target\s+video)?\.\s*$",
        definitions,
    ):
        name = match.group("name").strip()
        subject_id = int(match.group("picture"))
        records.setdefault(name, {
            "subject_id": subject_id,
            "picture_ids": [subject_id],
            "picture_id": subject_id,
            "speaker_id": f"S{subject_id}",
        })
    known = context.get("known_subjects")
    if isinstance(known, Mapping):
        for key, value in known.items():
            if isinstance(key, str) and str(value).isdigit():
                records.setdefault(key, {
                    "subject_id": int(value),
                    "picture_id": None,
                    "speaker_id": f"S{int(value)}",
                })
    return records


def _subject_maps(context: Mapping[str, Any]) -> tuple[dict[str, int], set[int], set[int]]:
    records = _subject_records(context)
    names = {
        name: record["subject_id"]
        for name, record in records.items()
    }
    subjects = {
        record["subject_id"] for record in records.values()
        if record["subject_id"] is not None
    }
    pictures = {
        picture
        for record in records.values()
        for picture in record.get("picture_ids", [record["picture_id"]])
        if record["picture_id"] is not None
    }
    return names, subjects, pictures


def normalize_summary_subject_references(
    summary: str,
    subject_definitions: str,
) -> str:
    """Use stable Subject tags instead of speaker IDs in continuity summaries."""
    if not isinstance(summary, str):
        return summary

    definitions = str(subject_definitions or "")
    subjects = []
    for match in re.finditer(
        r"(?i)<Subject\s+(\d+)>\s*(?:is\s+)?"
        r"([A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*)*)",
        definitions,
    ):
        subjects.append((int(match.group(1)), match.group(2).strip()))
    for match in re.finditer(
        r"(?im)^\s*(?:<\s*)?Picture\s+(\d+)\s*(?:>\s*)?"
        r"(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
        r"([A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*)*)"
        r"(?:\s+and\s+aligns\s+with\s+the\s+\d+(?:\.\d+)?-second\s+"
        r"mark\s+of\s+the\s+target\s+video)?\.\s*$",
        definitions,
    ):
        subject_id = int(match.group(1))
        name = match.group(2).strip()
        if not any(existing_id == subject_id for existing_id, _ in subjects):
            subjects.append((subject_id, name))

    normalized = summary
    for number, name in sorted(subjects, key=lambda item: -len(item[1])):
        escaped_name = re.escape(name)
        normalized = re.sub(
            rf"(?i)\b{escaped_name}\b\s*\(S\d+\)",
            f"<Subject {number}> {name}",
            normalized,
        )
        normalized = re.sub(
            rf"(?i)\(S\d+\)\s*\b{escaped_name}\b",
            f"<Subject {number}> {name}",
            normalized,
        )
    return normalized


def _repair_fields(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    del context
    for field in (DESCRIPTION, SOUNDSCAPE, MUSIC):
        result[field] = _strip_field_prefix(result.get(field, ""), field)
    for field in (DESCRIPTION, SOUNDSCAPE, MUSIC):
        result[field] = re.sub(
            rf"(?i)\b{re.escape(field)}\s*:\s*", "", result[field]
        ).strip()
        result[field] = re.sub(r"(?i)\s*\(\s*unidentified\s*\)", "", result[field])
        result[field] = _strip_markdown(result[field])
        result[field] = _replace_unsupported_dashes(result[field])



def _repair_shots(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    description = result[DESCRIPTION]
    number = _segment_number(context)
    # Remove every model-supplied shot marker. The pipeline produces one shot
    # per segment, so retaining a second marker would create a false cut.
    description = _SHOT.sub("", description)
    description = _ALIGNMENT.sub("", description).strip()
    description = _TRAILING_PARENTHESIZED_TIME.sub(
        lambda match: (
            f"{match.group('boundary')}{match.group('transition') or ''}"
            f"at {int(match.group('minutes')):02d}:"
            f"{match.group('seconds')}:"
            f"{match.group('milliseconds').ljust(3, '0')} seconds, "
            f"{match.group('action')}"
            f"{match.group('punct')}"
        ),
        description,
    )
    if number == 1:
        description = _ANY_LOCAL_TIME.sub("", description).strip()
        description = re.sub(
            r"(?i)^\s*At\s+0+(?:\.0+)?\s*seconds?\s*[,;:\-]?\s*",
            "",
            description,
        )
        description = re.sub(
            r"(?i)\s+(?:At\s+)?00:00(?:[.:]0{1,3})?"
            r"(?:\s+seconds?)?\s*,?\s*",
            " ",
            description,
        )
    else:
        description = re.sub(
            r"(?i)^\s*(?:At\s+)?(?:\d{1,2}:00(?:[.:]0{1,3})?|"
            r"0+\.0{1,3})(?:\s+seconds?)?\s*[,;:\-]?\s*",
            "At 00:00.000 seconds, ",
            description,
        )
        description = _LOCAL_TIME.sub(_format_local_timestamp, description)
        description = re.sub(
            r"(?i)^At 00:00\.000,\s*",
            "At 00:00.000 seconds, ",
            description,
        )
        # Strip the obsolete generic continuation phrase.  A non-cut segment
        # must describe the physical camera movement itself; the formatter does
        # not invent a movement that the director failed to author.
        description = _format_continuation_opening(description)
    description = _clean_space(description).lstrip(" ,;:-")
    description = re.sub(
        r"(?i)(?<!\])\s+(?=At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds?)?,)",
        "\n",
        description,
    )
    prefix = f"[Shot {number}]"

    if context.get("hard_cut_required"):
        description = re.sub(
            r"(?i)^Camera\s+(?:cuts\s+to\s+a\s+new\s+shot|"
            r"continues\s+from\s+the\s+previous\s+shot)\s*[:.,-]?\s*",
            "",
            description,
        )
        description = _CONFLICTING_CONTINUATION.sub("", description)
        description = f"Camera cuts to a new shot: {description.lstrip()}"
    # For non-cut segments, do not insert "Camera continues..." and do not
    # silently rewrite a model-authored cut as continuity.  Validation will
    # reject an unauthorized cut so the caller can request a genuine rewrite.
    result[DESCRIPTION] = f"{prefix} {description}".strip()

def _camera_label_replacement(match: re.Match[str]) -> str:
    motion = _clean_space(match.group("motion")).lower().rstrip(".")
    amplitude = _clean_space(match.group("amplitude") or "").lower().rstrip(".")
    speed = _clean_space(match.group("speed") or "").lower().rstrip(".")
    verb = _CAMERA_VERBS.get(motion)
    if verb is None:
        return match.group(0)
    phrase = f"The camera {verb}"
    if amplitude in {"small", "large"}:
        phrase += f" with {amplitude} amplitude"
    if speed in {"slow", "fast"}:
        phrase += f" at {speed} speed"
    return phrase + "."


def _repair_camera(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    del context
    description = result[DESCRIPTION]
    labels = re.compile(
        r"(?is)(?:\[?\s*)?Camera\s+Motion\s*:\s*(?P<motion>[^.\]\n;]+)"
        r"\s*(?:\.\s*|;\s*|\]\s*)"
        r"(?:\[?\s*Amplitude\s*:\s*(?P<amplitude>[^.\]\n;]+)"
        r"\s*(?:\.\s*|;\s*|\]\s*))?"
        r"(?:\[?\s*Speed\s*:\s*(?P<speed>[^.\]\n;]+)"
        r"\s*(?:\.\s*|;\s*|\]\s*))?"
    )
    description = labels.sub(_camera_label_replacement, description)
    description = re.sub(
        r"(?i)\bThe camera (?:orbits|arcs) around\b",
        "The camera moves in an arc around",
        description,
    )
    description = re.sub(r"(?i)\bThe camera dollies in\b", "The camera pushes in", description)
    description = re.sub(r"(?i)\bThe camera dollies out\b", "The camera pulls out", description)
    # Ministral also emits terse shot-list labels without the "Camera Motion"
    # wrapper.  Turn the recurring forms into grammatical camera direction.
    description = re.sub(
        r"(?i)(?<![\w])Arc\s+Shot\b\s*:?[ \t]*",
        "The camera moves in an arc ",
        description,
    )
    description = re.sub(
        r"(?i)(?<!holds a )(?<![\w])Static\s+medium\s+close[- ]up\b\s*:?[ \t]*"
        r"(?:(?:frames?|of)\s+)?",
        "The camera holds a static medium close-up of ",
        description,
    )
    description = re.sub(
        r"(?i)(?<![\w])Tilt\s+Down\b\s*:?[ \t]*",
        "The camera tilts down ",
        description,
    )
    result[DESCRIPTION] = _clean_space(description)



def _repair_subject_tags(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    """Canonicalize ordinary character identity references to <Subject N>.

    Picture tags are source-asset references and remain valid when the prose
    explicitly uses the picture itself as a frame/keyframe/composition anchor.
    They are not injected next to character names for routine identity recall.
    """
    names, subjects, pictures = _subject_maps(context)
    subject_pictures = _subject_picture_map(context)
    records = _subject_records(context)
    subject_names = {
        record["subject_id"]: name
        for name, record in records.items()
        if record.get("subject_id") is not None
    }
    picture_to_subject = {
        picture_id: subject_id
        for subject_id, picture_ids in subject_pictures.items()
        for picture_id in picture_ids
    }

    text = re.sub(
        r"\s*\(\s*Subject\s+\d+\s*\)",
        "",
        result[DESCRIPTION],
        flags=re.I,
    )

    # Remove undefined tags without inventing an identity.
    text = re.sub(
        r"<Subject\s+(\d+)>",
        lambda match: match.group(0) if int(match.group(1)) in subjects else "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<Picture\s+(\d+)>",
        lambda match: match.group(0) if int(match.group(1)) in pictures else "",
        text,
        flags=re.I,
    )

    # Legacy "<Subject N> from <Picture N>" identity syntax becomes the
    # stable Subject identity used by ordinary scene prose.
    text = re.sub(
        r"<Subject\s+(\d+)>\s+from\s+<Picture\s+(\d+)>",
        lambda match: (
            f"<Subject {int(match.group(1))}> "
            f"{subject_names.get(int(match.group(1)), '')}"
        ).strip()
        if picture_to_subject.get(int(match.group(2))) == int(match.group(1))
        else match.group(0),
        text,
        flags=re.I,
    )

    # Convert legacy character-adjacent Picture identity tags while leaving
    # standalone Picture anchors untouched.
    for name, subject_id in sorted(names.items(), key=lambda item: -len(item[0])):
        for picture_id in subject_pictures.get(subject_id, []):
            text = re.sub(
                rf"\b{re.escape(name)}\b\s*<Picture\s+{picture_id}>",
                f"<Subject {subject_id}> {name}",
                text,
                flags=re.I,
            )
            text = re.sub(
                rf"<Picture\s+{picture_id}>\s*\b{re.escape(name)}\b",
                f"<Subject {subject_id}> {name}",
                text,
                flags=re.I,
            )

    # Canonicalize an existing Subject tag with its registered name.
    for subject_id, name in subject_names.items():
        text = re.sub(
            rf"<Subject\s+{subject_id}>\s*(?:{re.escape(name)}\b)?",
            f"<Subject {subject_id}> {name}",
            text,
            flags=re.I,
        )
        text = re.sub(
            rf"<Subject\s+{subject_id}>\s+{re.escape(name)}\s+"
            rf"<Subject\s+{subject_id}>\s+{re.escape(name)}",
            f"<Subject {subject_id}> {name}",
            text,
            flags=re.I,
        )

    # Ensure the first ordinary named appearance of every registered subject is
    # tagged.  Do not add Picture tags; subject_definitions already binds them.
    for name, subject_id in sorted(names.items(), key=lambda item: -len(item[0])):
        if subject_id not in subjects or not re.search(rf"\b{re.escape(name)}\b", text, re.I):
            continue
        if re.search(
            rf"<Subject\s+{subject_id}>\s+{re.escape(name)}\b",
            text,
            re.I,
        ):
            continue
        text = re.sub(
            rf"\b{re.escape(name)}\b",
            f"<Subject {subject_id}> {name}",
            text,
            count=1,
            flags=re.I,
        )

    result[DESCRIPTION] = _clean_space(text)

def _canonicalize_compound_ids(text: str, id_map: Mapping[int, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_ids = [int(value) for value in re.findall(r"S(\d+)", match.group(0), re.I)]
        ids = sorted({id_map.get(value, value) for value in raw_ids})
        return "(" + ",".join(f"S{value}" for value in ids) + ")"

    return re.sub(r"\(\s*S\d+(?:\s*,\s*S\d+)+\s*\)", replace, text, flags=re.I)


_LANGUAGE_TAG = re.compile(
    r"(?i)^(?:English|Spanish|French|German|Italian|Portuguese|Japanese|"
    r"Korean|Chinese|Mandarin|Cantonese|Russian|Arabic|Hindi)$"
)


def _move_dialogue_delivery_cues(text: str) -> str:
    """Move leading non-language ``[cue]`` tags outside spoken contents."""

    block = re.compile(
        r"(?P<prefix>\b[A-Z][\w'-]*(?:\s+and\s+[A-Z][\w'-]*)?\s+"
        r"\(S\d+(?:,S\d+)*\)[^<>.!?\n]{0,120}:\s*)?"
        r"<d>\s*(?P<body>.*?)\s*</d>",
        re.I | re.S,
    )

    def replace(match: re.Match[str]) -> str:
        body = match.group("body").strip()
        tags: list[str] = []
        while True:
            leading = re.match(r"^\[([^\]\r\n]+)]\s*", body)
            if not leading:
                break
            label = _clean_space(leading.group(1))
            body = body[leading.end():]
            if not _LANGUAGE_TAG.fullmatch(label):
                tags.append(label)

        rendered = f"<d>[English] {body.strip()}</d>"
        prefix = match.group("prefix") or ""
        if not tags:
            return prefix + rendered

        normalized = {tag.casefold() for tag in tags}
        action = ""
        if "sharp breath" in normalized:
            action = "takes a sharp breath, then "
        elif any(tag in normalized for tag in {"laugh", "laughs", "laughing"}):
            action = "laughs, then "

        delivery: list[str] = []
        if any(tag in normalized for tag in {"tense", "tensely"}):
            delivery.append("tensely")
        if any(tag in normalized for tag in {"panicked", "panicking", "panic"}):
            delivery.append("in a panicked tone")
        known = {
            "sharp breath", "laugh", "laughs", "laughing", "tense", "tensely",
            "panicked", "panicking", "panic",
        }
        delivery.extend(
            f"with {tag.casefold()} delivery"
            for tag in tags
            if tag.casefold() not in known
        )

        if prefix:
            speech = re.compile(
                r"\b(says|asks|answers|replies|shouts|whispers|yells|tells|"
                r"exclaims|narrates)\b",
                re.I,
            )
            matches = list(speech.finditer(prefix))
            if matches:
                verb = matches[-1]
                replacement = action + verb.group(0)
                if delivery:
                    replacement += " " + " and ".join(delivery)
                prefix = prefix[:verb.start()] + replacement + prefix[verb.end():]
                return prefix + rendered

        cue_text = ", and ".join(tags).casefold()
        return f"The line is delivered with {cue_text} delivery: {rendered}"

    return block.sub(replace, text)


def _repair_dialogue(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    # An empty model-generated speaker placeholder blocks the normal
    # ``Name says`` attribution matcher. Remove it before assigning IDs.
    text = re.sub(r"\s*\(\s*\)\s*(?=:)", "", result[DESCRIPTION])
    text = re.sub(r"\s*\(\s*\)\s*", " ", text)
    text = re.sub(
        r"\(\s*[,;:]?\s*(S\d+(?:\s*,\s*S\d+)*)\s*[,;:]?\s*\)",
        lambda match: "(" + ",".join(
            re.findall(r"S\d+", match.group(1), re.I)
        ) + ")",
        text,
        flags=re.I,
    )
    names, subjects, _ = _subject_maps(context)
    records = _subject_records(context)

    for name, record in sorted(records.items(), key=lambda item: -len(item[0])):
        speaker_id = record.get("speaker_id")
        if not speaker_id:
            continue
        text = re.sub(
            rf"\b({re.escape(name)})\b\s*(<Subject\s+\d+>\s*)?\s*"
            rf"\(S\d+\)",
            lambda match, speaker=speaker_id: (
                f"{match.group(1)} "
                f"{match.group(2) + ' ' if match.group(2) else ''}"
                f"({speaker})"
            ),
            text,
            flags=re.I,
        )
        text = re.sub(
            rf"\b({re.escape(name)})\b\s*(<Picture\s+\d+>)?\s+"
            rf"(?P<verb>says|asks|answers|replies|shouts|whispers|yells|"
            rf"tells|exclaims|narrates)\s*:",
            lambda match, speaker=speaker_id: (
                f"{match.group(1)} "
                f"{match.group(2) + ' ' if match.group(2) else ''}"
                f"({speaker}) {match.group('verb')}:"
            ),
            text,
            flags=re.I,
        )
        text = re.sub(
            rf"\b({re.escape(name)})\b\s*(<Picture\s+\d+>)?\s+"
            rf"(?P<verb>says|asks|answers|replies|shouts|whispers|yells|"
            rf"tells|exclaims|narrates)\s+(?=<d>)",
            lambda match, speaker=speaker_id: (
                f"{match.group(1)} "
                f"{match.group(2) + ' ' if match.group(2) else ''}"
                f"({speaker}) {match.group('verb')} "
            ),
            text,
            flags=re.I,
        )

    # Learn drifted numeric IDs from identity-attached occurrences before
    # replacing them.  This lets a later compound (S5,S6) become (S1,S2).
    drift: dict[int, int] = {}
    for name, canonical in names.items():
        for match in re.finditer(
            rf"\b{re.escape(name)}\b\s*\(\s*S(\d+)\s*\)", text, re.I
        ):
            drift[int(match.group(1))] = canonical
        for match in re.finditer(
            rf"\(\s*S(\d+)\s*\)\s*\b{re.escape(name)}\b", text, re.I
        ):
            drift[int(match.group(1))] = canonical

    # Normalize the less common ID-first form before the main identity pass.
    for name, canonical in sorted(names.items(), key=lambda item: -len(item[0])):
        text = re.sub(
            rf"\(\s*S\d+\s*\)\s*\b({re.escape(name)})\b",
            lambda match, number=canonical: f"{match.group(1)} (S{number})",
            text,
            flags=re.I,
        )

    for first, first_id in names.items():
        for second, second_id in names.items():
            if first_id == second_id:
                continue
            text = re.sub(
                rf"(?:<Subject\s+{first_id}>\s*)?"
                rf"\(\s*S\d+\s*,\s*S\d+\s*\)\s*"
                rf"\b{re.escape(first)}\b\s+and\s+"
                rf"(?:<Subject\s+{second_id}>\s*)?\b{re.escape(second)}\b",
                lambda match, ids=sorted((first_id, second_id)), a=first,
                b=second, a_id=first_id, b_id=second_id: (
                    (f"<Subject {a_id}> " if a_id in subjects else "")
                    + f"{a} and "
                    + (f"<Subject {b_id}> " if b_id in subjects else "")
                    + f"{b} (S{ids[0]},S{ids[1]})"
                ),
                text,
                flags=re.I,
            )

    # Identity wins over whatever number Ministral generated.
    for name, canonical in sorted(names.items(), key=lambda item: -len(item[0])):
        text = re.sub(
            rf"\b({re.escape(name)})\b\s*\(\s*S\d+\s*\)",
            lambda match, number=canonical: f"{match.group(1)} (S{number})",
            text,
            flags=re.I,
        )
        text = re.sub(
            rf"\b({re.escape(name)})\b\s+"
            rf"(says|asks|answers|replies|shouts|whispers|yells|tells|exclaims)"
            rf"\s*\(\s*S\d+\s*\)",
            lambda match, number=canonical: f"{match.group(1)} (S{number}) {match.group(2)}",
            text,
            flags=re.I,
        )

    text = _canonicalize_compound_ids(text, drift)
    for first, first_id in names.items():
        for second, second_id in names.items():
            if first_id == second_id:
                continue
            text = re.sub(
                rf"(?:<Subject\s+{first_id}>\s*)?\b{re.escape(first)}\b\s+and\s+"
                rf"(?:<Subject\s+{second_id}>\s*)?\b{re.escape(second)}\b"
                rf"\s*\(\s*S\d+\s*,\s*S\d+\s*\)",
                lambda match, ids=sorted((first_id, second_id)), a=first,
                b=second, a_id=first_id, b_id=second_id: (
                    (f"<Subject {a_id}> " if a_id in subjects else "")
                    + f"{a} and "
                    + (f"<Subject {b_id}> " if b_id in subjects else "")
                    + f"{b} (S{ids[0]},S{ids[1]})"
                ),
                text,
                flags=re.I,
            )

    # A speech verb that has been concatenated to its adverb or following word
    # (for example, "saysagain" or "saysfirmly") should still read as two
    # words, while punctuation forms like "says:" remain unchanged.
    text = re.sub(
        r"(?i)\b(says|asks|answers|replies|shouts|whispers|yells|tells|exclaims|narrates)"
        r"(?=[a-z])",
        r"\1 ",
        text,
    )

    # Add a stable ID when a known character directly introduces dialogue.
    attribution = r"says|asks|answers|replies|shouts|whispers|yells|tells|exclaims|narrates"
    for name, canonical in names.items():
        text = re.sub(
            rf"\b(?P<name>{re.escape(name)})\b"
            rf"(?P<picture>\s*<Picture\s+\d+>)?"
            rf"(?!\s*\(S\d+\))\s+"
            rf"(?P<verb>{attribution})"
            rf"(?=(?:[^<.!?]|<Picture\s+\d+>){{0,160}}<d>)",
            lambda match, number=canonical: (
                f"{match.group('name')}"
                f"{match.group('picture') or ''} (S{number}) "
                f"{match.group('verb')}"
            ),
            text,
            flags=re.I,
        )

    # A bare colon before a dialogue block is a missing speech verb.
    text = re.sub(
        r"\b([A-Z][\w'’-]*(?:\s+and\s+[A-Z][\w'’-]*)?\s+"
        r"(?:<Picture\s+\d+>\s+)?\(S\d+(?:,S\d+)*\))\s*:\s*(?=<d>)",
        r"\1 says: ",
        text,
    )
    # An ask/tell/reply target may carry an identity ID immediately before
    # the colon.  Do not turn that target into a second speaker.
    text = re.sub(
        r"\b(says|asks|answers|replies|shouts|whispers|yells|tells|exclaims)\b"
        r"(?P<target>(?:[^<>.!?]|<Picture\s+\d+>){0,100}\(S\d+\))"
        r"\s+says\s*:",
        lambda match: f"{match.group(1)}{match.group('target')}:",
        text,
        flags=re.I,
    )

    text = _move_dialogue_delivery_cues(text)

    # The language tag is metadata, not dialogue text.  Adding/replacing it
    # does not alter any authored spoken word or punctuation.
    def language(match: re.Match[str]) -> str:
        content = match.group(1)
        content = re.sub(
            r"^\s*\[(?:English|Spanish|French|German|Italian|Portuguese|Japanese|"
            r"Korean|Chinese|Mandarin|Cantonese|Russian|Arabic|Hindi)\]\s*",
            "",
            content,
            flags=re.I,
        )
        return f"<d>[English] {content}</d>"

    text = re.sub(r"<d>\s*(.*?)\s*</d>", language, text, flags=re.I | re.S)

    # Normalize the explicit voiceover form and add its visual lip constraint.
    text = re.sub(
        r"(?i)\b(narrates|says\s+(?:as|in)\s+(?:an?\s+)?(?:off[- ]screen\s+)?voiceover)\s*:",
        "says in an off-screen voiceover:",
        text,
    )
    voiceover = re.compile(
        r"(?P<speaker>\b(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)\s+"
        r"(?:<Picture\s+\d+>\s+)?\(S\d+\)\s+"
        r"says in an off-screen voiceover:\s*<d>.*?</d>)"
        r"(?!\s+while\s+(?:his|her|their|[A-Z][\w'’-]*'s)\s+lips\s+remain\s+completely\s+closed)",
        re.I | re.S,
    )

    def close_lips(match: re.Match[str]) -> str:
        name = match.group("name")
        return f"{match.group('speaker')} while {name}'s lips remain completely closed"

    text = voiceover.sub(close_lips, text)
    text = re.sub(r"([.!?])</d>\s*[.!?,;:]+", r"\1</d>", text)
    result[DESCRIPTION] = _clean_space(text)



def _repair_non_speaking_ids(
    result: dict[str, Any], context: Mapping[str, Any]
) -> None:
    """Remove speaker IDs from visual prose while preserving Subject identity."""

    names, subjects, _ = _subject_maps(context)
    canonical_names = {name.casefold(): (name, number) for name, number in names.items()}
    pieces = re.split(r"(?<=[.!?])\s+", result[DESCRIPTION])

    def remove_id(match: re.Match[str]) -> str:
        written_name = match.group("name")
        known = canonical_names.get(written_name.casefold())
        if known is None:
            return written_name
        canonical_name, number = known
        if number in subjects:
            return f"<Subject {number}> {canonical_name}"
        return canonical_name

    repaired = []
    for piece in pieces:
        if "<d>" not in piece.lower():
            piece = re.sub(
                r"(?:<Subject\s+\d+>\s*)?"
                r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)\s*"
                r"\(\s*S\d+(?:\s*,\s*S\d+)*\s*\)",
                remove_id,
                piece,
            )
            # Speaker IDs have meaning only for attributed spoken dialogue.
            piece = re.sub(
                r"\s*\(\s*S\d+(?:\s*,\s*S\d+)*\s*\)",
                "",
                piece,
                flags=re.I,
            )
        repaired.append(piece)
    result[DESCRIPTION] = _clean_space(" ".join(repaired))


def _subject_picture_map(context: Mapping[str, Any]) -> dict[int, list[int]]:
    definitions = str(context.get("subject_definitions", "") or "")
    result: dict[int, list[int]] = {}
    for match in re.finditer(
        r"(?im)^\s*<Subject\s+(\d+)>.*$",
        definitions,
    ):
        pictures = list(dict.fromkeys(
            int(picture) for picture in re.findall(
                r"(?i)<Picture\s+(\d+)>", match.group(0)
            )
        ))
        if pictures:
            result[int(match.group(1))] = pictures
    for match in re.finditer(
        r"(?im)^\s*(?:<\s*)?Picture\s+(\d+)\s*(?:>\s*)?"
        r"(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
        r"([A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*)*)"
        r"(?:\s+and\s+aligns\s+with\s+the\s+\d+(?:\.\d+)?-second\s+"
        r"mark\s+of\s+the\s+target\s+video)?\.\s*$",
        definitions,
    ):
        picture = int(match.group(1))
        result.setdefault(picture, [picture])
    return result


def _repair_canonical_subject_tags(
    result: dict[str, Any], context: Mapping[str, Any]
) -> None:
    """Final-pass normalization for stable <Subject N> scene references.

    Standalone <Picture N> references are preserved because they may be explicit
    frame/keyframe/composition anchors. Character-adjacent Picture tags are
    treated as legacy identity syntax and converted to the registered Subject.
    Every ordinary use of a registered canonical name is tagged as <Subject N>.
    """
    records = _subject_records(context)
    subject_pictures = _subject_picture_map(context)
    text = result[DESCRIPTION]

    for name, record in sorted(records.items(), key=lambda item: -len(item[0])):
        subject_id = record.get("subject_id")
        if subject_id is None:
            continue

        # Convert legacy character-adjacent Picture identity tags. Standalone
        # Picture anchors such as "composition established by <Picture 1>" are
        # deliberately untouched.
        for picture_id in subject_pictures.get(subject_id, []):
            text = re.sub(
                rf"\b{re.escape(name)}\b\s*<Picture\s+{picture_id}>",
                name,
                text,
                flags=re.I,
            )
            text = re.sub(
                rf"<Picture\s+{picture_id}>\s*\b{re.escape(name)}\b",
                name,
                text,
                flags=re.I,
            )

        # Normalize any existing Subject tag/name pair first.
        text = re.sub(
            rf"<Subject\s+{subject_id}>\s*(?:{re.escape(name)}\b)?",
            f"<Subject {subject_id}> {name}",
            text,
            flags=re.I,
        )
        text = re.sub(
            rf"(?:<Subject\s+{subject_id}>\s+{re.escape(name)}\s*){{2,}}",
            f"<Subject {subject_id}> {name} ",
            text,
            flags=re.I,
        )

        # Tag every ordinary canonical-name reference, including dialogue
        # attributions. Do not duplicate a Subject tag already immediately
        # before the name.
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.I)

        def tag_name(match: re.Match[str], *, sid=subject_id, canonical=name) -> str:
            prefix = text[max(0, match.start() - 64):match.start()]
            if re.search(rf"<Subject\s+{sid}>\s*$", prefix, re.I):
                return canonical
            return f"<Subject {sid}> {canonical}"

        text = pattern.sub(tag_name, text)

        # Collapse any duplicates introduced by malformed input or earlier
        # repair passes.
        text = re.sub(
            rf"(?:<Subject\s+{subject_id}>\s+{re.escape(name)}\s*){{2,}}",
            f"<Subject {subject_id}> {name} ",
            text,
            flags=re.I,
        )

    result[DESCRIPTION] = _clean_space(text)


def _validate_non_speaking_ids(
    result: Mapping[str, Any], context: Mapping[str, Any]
) -> list[str]:
    del context
    for piece in re.split(r"(?<=[.!?])\s+", str(result.get(DESCRIPTION, ""))):
        if "<d>" in piece.lower():
            continue
        if re.search(
            r"\(\s*S\d+(?:\s*,\s*S\d+)*\s*\)",
            piece,
            re.I,
        ):
            return [
                "Speaker IDs may appear only in sentences containing "
                "attributed dialogue."
            ]
        if re.search(
            r"\b[A-Z][\w'’-]*\s*\(\s*S\d+(?:\s*,\s*S\d+)*\s*\)",
            piece,
        ):
            return [
                "Speaker IDs may appear only in sentences containing "
                "attributed dialogue."
            ]
    return []


def _repair_visible_text(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    del context
    text = result[DESCRIPTION]
    # All-caps signage is an especially reliable boundary: stop before a
    # following action clause and preserve the visible words exactly.
    pattern = re.compile(
        r"(?P<head>(?i:(?:sign|banner|label|subtitle|neon\s+(?:sign|text))\s+"
        r"(?:reading|reads|displaying|displays|showing|shows|saying|says)\s+))"
        r"(?P<visible>[A-Z][A-Z0-9 &'’!?,.:-]*[A-Z0-9!?])"
        r"(?=\s+(?:while|as|beside|above|below|and\s+(?:people|visitors|the\s+camera))\b|[.;]|$)"
    )

    def quote(match: re.Match[str]) -> str:
        visible = match.group("visible").strip()
        if visible.startswith('"') and visible.endswith('"'):
            return match.group(0)
        return f'{match.group("head")}"{visible}"'

    result[DESCRIPTION] = pattern.sub(quote, text)


def _sentences(value: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(value.strip()) if part.strip()]


def _limit_sentences(value: str, maximum: int) -> str:
    parts = _sentences(value)
    if len(parts) <= maximum:
        return value.strip()
    kept = parts[: maximum - 1]
    tail = "; ".join(part.rstrip(".!?") for part in parts[maximum - 1:]) + "."
    return " ".join(kept + [tail])


def _repair_soundscape(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    del context
    value = result[SOUNDSCAPE]
    value = re.sub(r"<d>.*?</d>", "", value, flags=re.I | re.S)
    kept: list[str] = []
    for sentence in _sentences(value):
        lower = sentence.lower()
        if "all language is in english" in lower:
            continue
        if re.search(
            r"[\"“”]|\b(?:says|asks|replies|shouts?|yells?|spoken dialogue|sings?|"
            r"announces?|pa announcements?|vendor calls?)\b",
            sentence,
            re.I,
        ):
            continue
        music = re.search(
            r"\b(?:non[- ]diegetic|diegetic|music|score|melody|piano|guitar|brass|"
            r"violins?|calliope)\b|"
            r"\bstrings\s+(?:play|sustain|swell)|\bdrums?\s+(?:play|enter|pulse)",
            lower,
        )
        if music:
            continue
        kept.append(sentence)
    result[SOUNDSCAPE] = _limit_sentences(" ".join(kept), 4)


_NA = re.compile(
    r"(?i)^\s*(?:n\s*[./]?\s*a\.?|none\.?|no\s+(?:non[- ]diegetic\s+)?music\.?)\s*$"
)


def _repair_music(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    del context
    value = result[MUSIC].strip()
    result[MUSIC] = "N/A" if _NA.match(value) else _limit_sentences(value, 3)


def _parse_beat_id(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    match = re.fullmatch(r"\s*(?:B\s*0*)?(\d+)\s*", str(raw), re.I)
    return int(match.group(1)) if match else None



def _repair_completions(result: dict[str, Any], context: Mapping[str, Any]) -> None:
    raw = result.get(COMPLETIONS, [])
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    parsed = {_parse_beat_id(value) for value in raw}
    parsed.discard(None)

    current = _next_beat_id(context)
    segment = _segment_number(context)
    expected = segment if current is not None else None
    result[COMPLETIONS] = [expected] if expected is not None and expected in parsed else []
    result[DESCRIPTION] = re.sub(
        r"(?i)\s*completed_beat_ids\s*:\s*\[[^\]]*\]\s*", " ", result[DESCRIPTION]
    ).strip()

def _validate_fields(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    del context
    issues = []
    for field in (DESCRIPTION, SOUNDSCAPE, MUSIC):
        if not isinstance(result.get(field), str) or not result.get(field, "").strip():
            issues.append(f"Missing non-empty {field} text.")
        elif re.search(rf"(?i)\b{re.escape(field)}\s*:", result[field]):
            issues.append(f"{field} still contains a duplicated field label.")
        if isinstance(result.get(field), str) and (
            "\u2014" in result[field] or "â€”" in result[field]
        ):
            issues.append(f"{field} contains an unsupported em dash.")
    if not isinstance(result.get(COMPLETIONS), list):
        issues.append("completed_beat_ids must be a list.")
    return issues



def _validate_shots(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    text = str(result.get(DESCRIPTION, ""))
    number = _segment_number(context)
    expected = f"[Shot {number}]"
    issues = []
    shots = _SHOT.findall(text)
    if len(shots) != 1 or not text.startswith(expected):
        issues.append(f"Description must contain exactly one opening {expected} marker.")
    if number == 1 and re.match(
        rf"^{re.escape(expected)}\s+(?:At\s+)?(?:\d{{1,2}}:00(?:[.:]0{{1,3}})?|"
        rf"0+\.0{{1,3}})(?:\s+seconds?)?",
        text,
        re.I,
    ):
        issues.append("The opening shot must not have a timestamp.")
    if number > 1:
        if re.match(
            rf"^{re.escape(expected)}\s+At\s+00:00\.000 seconds,",
            text,
            re.I,
        ):
            issues.append("The continuation opening must not contain a timestamp.")
        if re.match(
            rf"^{re.escape(expected)}\s+Camera\s+continues\s+"
            r"(?:seamlessly\s+)?from\s+the\s+previous\s+shot\b",
            text,
            re.I,
        ):
            issues.append(
                "Do not use the generic continuation phrase; describe the actual "
                "physical camera movement into the new composition."
            )
        if not context.get("hard_cut_required") and re.match(
            rf"^{re.escape(expected)}\s+Camera\s+cuts\s+to\s+a\s+new\s+shot:",
            text,
            re.I,
        ):
            issues.append("Only scheduled hard-cut segments may begin with a camera cut.")
    if re.search(r"(?i)reference pictures align|fully referenced", text):
        issues.append("Reference-image alignment instructions do not apply to this pipeline.")
    if context.get("hard_cut_required") and not text.startswith(
        f"{expected} Camera cuts to a new shot:"
    ):
        issues.append("This segment requires the exact hard-cut opening form.")
    return issues

def _repair_timestamp_line_breaks(
    result: dict[str, Any], context: Mapping[str, Any]
) -> None:
    del context
    description = re.sub(
        r"(?i)(?<!\])\s+(?=At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds?)?,)",
        "\n",
        result[DESCRIPTION],
    )
    # Remove timestamp-only fragments that contain no event text.
    description = re.sub(
        r"(?im)^\s*At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds?)?,\s*"
        r"(?:and|then)?\s*(?:[.,;:!?])?\s*$\n?",
        "",
        description,
    )
    description = re.sub(
        r"(?i)\b(?:and|then)\s*\n(?=At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds?)?,)",
        "",
        description,
    )
    description = re.sub(
        r"(?i)At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds?)?,\s*(?:and|then)\b",
        "",
        description,
    )
    description = re.sub(
        r"(?i)At\s+\d{2}:\d{2}\.\d{3}(?:\s+seconds?)?,\s*[.,;:!?](?=\s|$)",
        "",
        description,
    )
    result[DESCRIPTION] = description.strip()



def _validate_camera(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    text = str(result.get(DESCRIPTION, ""))
    issues = []
    if re.search(
        r"(?i)\b(?:camera motion|amplitude|speed|arc shot|static medium close[- ]up|"
        r"tilt down)\s*:",
        text,
    ):
        issues.append("Camera motion remains as stacked labels instead of natural prose.")

    number = _segment_number(context)
    hard_cut = bool(context.get("hard_cut_required"))
    if number > 1 and not hard_cut:
        if re.search(
            r"(?i)\b(?:camera\s+cuts?|hard\s+cut|jump\s+cut|cutaway)\b",
            text,
        ):
            issues.append("This segment must reach its new composition without a camera cut.")
        movement = re.search(
            r"(?i)\b(?:the\s+camera\s+)?(?:"
            r"zooms?\s+(?:in|out)|push(?:es)?\s+in|pull(?:s)?\s+out|"
            r"pans?\s+(?:left|right)|trucks?\s+(?:left|right)|"
            r"tilts?\s+(?:up|down)|pedestals?\s+(?:up|down)|"
            r"moves?\s+in\s+an\s+arc|tracks?|uses?\s+a\s+tracking\s+shot|"
            r"rolls?\s+(?:clockwise|counterclockwise))\b",
            text,
        )
        if not movement:
            issues.append(
                "A non-cut continuation segment must explicitly describe visible "
                "continuous camera movement into a materially different composition."
            )
    return issues


def _validate_subject_tags(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    names, subjects, pictures = _subject_maps(context)
    subject_pictures = _subject_picture_map(context)
    text = str(result.get(DESCRIPTION, ""))
    issues = []
    for raw in re.findall(r"<Subject\s+(\d+)>", text, re.I):
        if int(raw) not in subjects:
            issues.append(f"Undefined <Subject {int(raw)}> tag remains.")
    for raw in re.findall(r"<Picture\s+(\d+)>", text, re.I):
        if int(raw) not in pictures:
            issues.append(f"Undefined <Picture {int(raw)}> tag remains.")
    if re.search(r"\(\s*Subject\s+\d+\s*\)", text, re.I):
        issues.append("Parenthetical Subject annotations must be removed.")
    if re.search(r"(?:^|\]\s+|[.!?]\s+)['\u2019]s\b", text, re.I):
        issues.append("Description contains an orphaned possessive with no subject.")

    for name, subject_id in names.items():
        if not re.search(rf"\b{re.escape(name)}\b", text, re.I):
            continue
        if not re.search(
            rf"<Subject\s+{subject_id}>\s+{re.escape(name)}\b",
            text,
            re.I,
        ):
            issues.append(
                f"{name} must use the stable <Subject {subject_id}> identity tag "
                "in ordinary scene prose."
            )
        for picture_id in subject_pictures.get(subject_id, []):
            if re.search(
                rf"(?:\b{re.escape(name)}\b\s*<Picture\s+{picture_id}>|"
                rf"<Picture\s+{picture_id}>\s*\b{re.escape(name)}\b)",
                text,
                re.I,
            ):
                issues.append(
                    f"Do not use <Picture {picture_id}> as an ordinary identity tag "
                    f"next to {name}; use <Subject {subject_id}> instead."
                )
    return issues

def _validate_dialogue(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    text = str(result.get(DESCRIPTION, ""))
    names, _, _ = _subject_maps(context)
    records = _subject_records(context)
    issues = []
    if text.lower().count("<d>") != text.lower().count("</d>"):
        issues.append("Dialogue tags are unbalanced.")
    for block in re.findall(r"<d>(.*?)</d>", text, re.I | re.S):
        if not re.match(r"\s*\[English\]\s+\S", block):
            issues.append("Every dialogue block must begin with [English].")
        if re.match(r"\s*\[English\]\s*\[[^\]]+\]", block, re.I):
            issues.append("Non-language delivery cues must appear outside <d> dialogue text.")
    for name, record in records.items():
        speaker_id = record.get("speaker_id")
        if speaker_id and re.search(
            rf"\b{re.escape(name)}\b\s*(?:<Picture\s+\d+>\s*)?"
            rf"\(S(?!{re.escape(speaker_id[1:])}\b)\d+\)",
            text,
            re.I,
        ):
            issues.append(f"{name} must consistently use speaker ID ({speaker_id}).")
    for match in re.finditer(r"says in an off-screen voiceover:\s*<d>.*?</d>", text, re.I | re.S):
        after = text[match.end():match.end() + 100]
        if not re.match(
            r"\s+while\s+(?:his|her|their|[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*'s)\s+lips remain completely closed",
            after,
            re.I,
        ):
            issues.append("Every voiceover must state that the on-screen character's lips remain closed.")
    for clause in re.finditer(
        r"while\s+(?:his|her|their|[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*'s)\s+lips\s+remain\s+completely\s+closed",
        text,
        re.I,
    ):
        before = text[max(0, clause.start() - 300):clause.start()]
        if not re.search(
            r"says in an off-screen voiceover:\s*<d>.*?</d>\s*$",
            before,
            re.I | re.S,
        ):
            issues.append("A closed-lips clause may only accompany a matching off-screen voiceover.")
    if re.search(r"(?i)\b(?:narrates|voice[- ]over)\s*:", text):
        issues.append("Voiceover must use the exact phrase 'says in an off-screen voiceover'.")

    # Every dialogue block needs a nearby, explicit speaker ID.  A role such as
    # "the son" must remain unresolved rather than being assigned a guessed ID.
    for match in re.finditer(r"<d>.*?</d>", text, re.I | re.S):
        before = text[max(0, match.start() - 220):match.start()]
        before = re.sub(r"<Subject\s+\d+>|<Picture\s+\d+>", "", before, flags=re.I)
        # Attribute only from the current clause.  A speaker ID belonging to a
        # previous dialogue block must not accidentally license "the son says".
        last_block = before.lower().rfind("</d>")
        if last_block >= 0:
            before = before[last_block + len("</d>"):]
        boundaries = [before.rfind(mark) for mark in (". ", "! ", "? ")]
        sentence = before[max(boundaries) + 2:] if max(boundaries) >= 0 else before
        attributed = re.search(
            r"\(S\d+(?:,S\d+)*\)[^<>.!?]{0,140}"
            r"(?:says|asks|answers|replies|shouts|whispers|yells|tells|exclaims|narrates)"
            r"[^<>.!?]{0,100}:?\s*$",
            sentence,
            re.I,
        )
        if not attributed:
            direct = re.search(
                r"\b(?:the\s+)?[A-Za-z][\w'’-]*(?:\s+[A-Za-z][\w'’-]*){0,3}\s+"
                r"(?:says|asks|answers|replies|shouts|whispers|yells|tells|exclaims)"
                r"[^<>.!?]{0,100}:?\s*$",
                sentence,
                re.I,
            )
            if direct:
                issues.append(
                    "An undefined or unknown directly speaking character is missing "
                    "a stable speaker ID."
                )
            else:
                issues.append("Dialogue block is missing an attributed speaker ID.")

    without_blocks = re.sub(r"<d>.*?</d>", "", text, flags=re.I | re.S)
    if re.search(
        r"\b(?:says|asks|answers|replies|shouts|whispers|yells|tells|exclaims)\b"
        r"[^.!?\n]{0,100}[\"“][^\"”]+[\"”]",
        without_blocks,
        re.I,
    ):
        issues.append("Quoted spoken dialogue must be enclosed in <d> tags.")
    return issues


def _validate_visible_text(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    del context
    text = str(result.get(DESCRIPTION, ""))
    if re.search(
        r"(?i)\b(?:sign|banner|label|subtitle|neon\s+(?:sign|text))\s+"
        r"(?:reading|reads|displaying|displays|showing|shows|saying|says)\s+"
        r"(?!\")\S+",
        text,
    ):
        return ["Explicitly visible on-screen text must be enclosed in English double quotes."]
    return []


def _validate_soundscape(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    value = str(result.get(SOUNDSCAPE, "")).strip()
    if value.upper() == "N/A":
        return [] if context.get("allow_silence") else [
            "overall_soundscape may be N/A only when complete silence is explicitly allowed."
        ]
    issues = []
    count = len(_sentences(value))
    if not 1 <= count <= 4:
        issues.append("overall_soundscape must contain 1-4 English sentences.")
    if re.search(
        r"(?i)<d>|all language is in english|[\"“”]|"
        r"\b(?:non[- ]diegetic music|score|says|asks|replies|shouts?|yells?|"
        r"pa announcements?|vendor calls?)\b",
        value,
    ):
        issues.append("overall_soundscape must not repeat dialogue, music, or a language suffix.")
    if re.search(
        r"(?i)\b(?:diegetic|music|melody|piano|guitar|brass|violins?|strings?|calliope)\b",
        value,
    ):
        issues.append("overall_soundscape must not contain diegetic or non-diegetic music.")
    return issues


def _validate_music(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    del context
    value = str(result.get(MUSIC, "")).strip()
    if value == "N/A":
        return []
    issues = []
    if not 1 <= len(_sentences(value)) <= 3:
        issues.append("non_diegetic_music must contain 1-3 English sentences or N/A.")
    abstract = re.search(
        r"(?i)\b(?:ominous|tense|sad|happy|hopeful|dramatic|emotional|scary|mysterious)\b",
        value,
    )
    if abstract:
        issues.append("Music uses abstract mood language without concrete musical details.")
    return issues



def _validate_completions(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    values = result.get(COMPLETIONS)
    if not isinstance(values, list) or any(not isinstance(value, int) for value in values):
        return ["completed_beat_ids must contain only integer metadata IDs."]

    current = _next_beat_id(context)
    if current is None:
        if values:
            return ["completed_beat_ids must be empty when beat tracking is disabled or complete."]
    else:
        expected = _segment_number(context)
        if current != expected:
            return [
                f"Beat context mismatch: Segment {expected} must use Beat {expected}, "
                f"but the formatter context supplied Beat {current}."
            ]
        if values != [expected]:
            return [
                f"Segment {expected} must report exactly one completed beat ID: "
                f"[{expected}]."
            ]

    if re.search(
        r"(?i)completed_beat_ids|\bB\s*0*\d+\b",
        str(result.get(DESCRIPTION, "")),
    ):
        return ["Beat completion IDs must not appear in rendered prompt text."]
    return []

def _validate_semantics(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    description = str(result.get(DESCRIPTION, ""))
    issues = []
    del context
    return issues


@dataclass(frozen=True)
class PromptRule:
    """An ordered deterministic repair paired with its validation checks."""

    name: str
    repair: Callable[[dict[str, Any], Mapping[str, Any]], None]
    validate: Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]]


RULE_REGISTRY = (
    PromptRule("fields", _repair_fields, _validate_fields),
    PromptRule("shots", _repair_shots, _validate_shots),
    PromptRule("camera", _repair_camera, _validate_camera),
    PromptRule("subject_tags", _repair_subject_tags, _validate_subject_tags),
    PromptRule("dialogue", _repair_dialogue, _validate_dialogue),
    PromptRule(
        "non_speaking_ids",
        _repair_non_speaking_ids,
        _validate_non_speaking_ids,
    ),
    PromptRule("visible_text", _repair_visible_text, _validate_visible_text),
    PromptRule("soundscape", _repair_soundscape, _validate_soundscape),
    PromptRule("music", _repair_music, _validate_music),
    PromptRule("completions", _repair_completions, _validate_completions),
    PromptRule(
        "timestamp_line_breaks",
        _repair_timestamp_line_breaks,
        lambda result, context: [],
    ),
    PromptRule(
        "canonical_subject_tags",
        _repair_canonical_subject_tags,
        lambda result, context: [],
    ),
)


def format_ministral_prompt(llm_result: Any, context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic, locally repaired H3 response object.

    The function never performs I/O.  It intentionally does not raise merely
    because semantic problems remain; call :func:`validate_ministral_prompt`
    after formatting and use those issues for a last-resort content re-query.
    """

    formatted = _coerce_result(llm_result)
    safe_context: Mapping[str, Any] = context or {}
    for _ in range(MAX_FORMAT_PASSES):
        before = copy.deepcopy(formatted)
        for rule in RULE_REGISTRY:
            rule.repair(formatted, safe_context)
        formatted = {field: formatted[field] for field in CORE_FIELDS}
        if formatted == before:
            break
    return formatted


def validate_ministral_prompt(
    result: Mapping[str, Any], context: Mapping[str, Any] | None
) -> list[str]:
    """Return stable descriptions of unresolved format and content violations."""

    safe_context: Mapping[str, Any] = context or {}
    if not isinstance(result, Mapping):
        return ["Formatted Ministral result must be an object."]
    issues: list[str] = []
    for rule in RULE_REGISTRY:
        issues.extend(rule.validate(result, safe_context))
    issues.extend(_validate_semantics(result, safe_context))
    # Preserve rule order while avoiding repeated diagnostics.
    return list(dict.fromkeys(issues))


class MinistralFormatter(BaseFormatter):
    """Adapter exposing the Ministral repair pipeline through the shared API."""

    def format_prompt(
        self,
        llm_result: Any,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return format_ministral_prompt(llm_result, context)

    def validate_prompt(
        self,
        result: Mapping[str, Any],
        context: Mapping[str, Any] | None,
    ) -> list[str]:
        return validate_ministral_prompt(result, context)


__all__ = [
    "MinistralFormatter",
    "RULE_REGISTRY",
    "format_ministral_prompt",
    "validate_ministral_prompt",
]
