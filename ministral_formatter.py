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


DESCRIPTION = "integrated_multimodal_description"
SOUNDSCAPE = "overall_soundscape"
MUSIC = "non_diegetic_music"
COMPLETIONS = "completed_beat_ids"
CORE_FIELDS = (DESCRIPTION, SOUNDSCAPE, MUSIC, COMPLETIONS)
MAX_FORMAT_PASSES = 8

_LABEL = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?"
    r"(integrated_multimodal_description|overall_soundscape|"
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
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _clean_space(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{2,}", " ", value)
    return value.strip()


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


def _subject_maps(context: Mapping[str, Any]) -> tuple[dict[str, int], set[int], set[int]]:
    definitions = str(context.get("subject_definitions", "") or "")
    names: dict[str, int] = {}
    subjects = {int(number) for number in re.findall(r"<Subject\s+(\d+)>", definitions, re.I)}
    pictures = {int(number) for number in re.findall(r"<Picture\s+(\d+)>", definitions, re.I)}
    for match in re.finditer(
        r"<Subject\s+(\d+)>\s*(?:is\s+)?([A-Z][\w'’-]*)", definitions
    ):
        names[match.group(2)] = int(match.group(1))

    known = context.get("known_subjects")
    if isinstance(known, Mapping):
        for key, value in known.items():
            if isinstance(key, str) and str(value).isdigit():
                names[key] = int(value)
            elif str(key).isdigit() and isinstance(value, str):
                names[value] = int(key)
    # These identities are part of the pipeline contract and remain stable even
    # when a shortened context omits definitions.
    names.setdefault("Mark", 1)
    names.setdefault("Jill", 2)
    return names, subjects, pictures


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
    # Remove every model-supplied shot marker.  The pipeline produces one shot
    # per segment, so retaining a second marker would create a false cut.
    description = _SHOT.sub("", description)
    description = _ALIGNMENT.sub("", description).strip()
    description = _ANY_LOCAL_TIME.sub("", description).strip()
    description = re.sub(
        r"(?i)^\s*At\s+0+(?:\.0+)?\s*seconds?\s*[,;:\-]?\s*",
        "",
        description,
    )
    description = re.sub(
        r"(?i)\s+(?:At\s+)?\d{1,2}:\d{2}(?:\.\d+)?\s*,?\s*"
        r"(?:the\s+(?:camera|shot)\s+(?:cuts|changes|switches|transitions)\s+to\s*)?",
        " ",
        description,
    )
    description = _clean_space(description).lstrip(" ,;:-")
    number = _segment_number(context)
    prefix = f"[Shot {number}]"

    if context.get("hard_cut_required"):
        description = re.sub(
            r"(?i)^Camera\s+(?:cuts\s+to\s+a\s+new\s+shot|"
            r"continues\s+from\s+the\s+previous\s+shot)\s*[:.,-]?\s*",
            "",
            description,
        )
        description = f"Camera cuts to a new shot: {description.lstrip()}"
    result[DESCRIPTION] = f"{prefix} {description}".strip()


_CAMERA_VERBS = {
    "zoom in": "zooms in",
    "zoom out": "zooms out",
    "push in": "pushes in",
    "pull out": "pulls out",
    "pan left": "pans left",
    "pan right": "pans right",
    "truck left": "trucks left",
    "truck right": "trucks right",
    "tilt up": "tilts up",
    "tilt down": "tilts down",
    "pedestal up": "pedestals up",
    "pedestal down": "pedestals down",
    "arc shot": "moves in an arc",
    "tracking shot": "uses a tracking shot",
    "static shot": "holds a static shot",
    "shake slightly": "shakes slightly",
    "shake strongly": "shakes strongly",
    "roll clockwise": "rolls clockwise",
    "roll counterclockwise": "rolls counterclockwise",
    "pov": "holds the subject's point of view",
}


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
    names, subjects, pictures = _subject_maps(context)

    def subject(match: re.Match[str]) -> str:
        return match.group(0) if int(match.group(1)) in subjects else ""

    def picture(match: re.Match[str]) -> str:
        return match.group(0) if int(match.group(1)) in pictures else ""

    text = re.sub(
        r"\s*\(\s*Subject\s+\d+\s*\)",
        "",
        result[DESCRIPTION],
        flags=re.I,
    )
    text = re.sub(r"<Subject\s+(\d+)>", subject, text, flags=re.I)
    text = re.sub(r"<Picture\s+(\d+)>", picture, text, flags=re.I)

    # A defined identity reference belongs on its first named appearance.  Do
    # not make tags up for unnamed relatives, and do not duplicate a tag the
    # model already supplied elsewhere in the prompt.
    for name, number in sorted(names.items(), key=lambda item: -len(item[0])):
        if number not in subjects or re.search(
            rf"<Subject\s+{number}>", text, re.I
        ):
            continue
        id_first = re.compile(
            rf"(\(S\d+(?:\s*,\s*S\d+)*\)\s*\b{re.escape(name)}\b)",
            re.I,
        )
        if id_first.search(text):
            text = id_first.sub(rf"<Subject {number}> \1", text, count=1)
        else:
            text = re.sub(
                rf"\b({re.escape(name)}(?:\s*\(S\d+\))?)(?=\s|[,.;:]|$)",
                rf"<Subject {number}> \1",
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
    text = result[DESCRIPTION]
    names, subjects, _ = _subject_maps(context)

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

    # Add a stable ID when a known character directly introduces dialogue.
    attribution = r"says|asks|answers|replies|shouts|whispers|yells|tells|exclaims|narrates"
    for name, canonical in names.items():
        text = re.sub(
            rf"\b({re.escape(name)})\b(?!\s*\(S\d+\))\s+"
            rf"({attribution})(?=[^<]{{0,100}}<d>)",
            lambda match, number=canonical: f"{match.group(1)} (S{number}) {match.group(2)}",
            text,
            flags=re.I,
        )

    # A bare colon before a dialogue block is a missing speech verb.
    text = re.sub(
        r"\b([A-Z][\w'’-]*(?:\s+and\s+[A-Z][\w'’-]*)?\s+"
        r"\(S\d+(?:,S\d+)*\))\s*:\s*(?=<d>)",
        r"\1 says: ",
        text,
    )
    # An ask/tell/reply target may carry an identity ID immediately before
    # the colon.  Do not turn that target into a second speaker.
    text = re.sub(
        r"\b(says|asks|answers|replies|shouts|whispers|yells|tells|exclaims)\b"
        r"(?P<target>[^<>.!?]{0,100}\(S\d+\))\s+says\s*:",
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
        r"(?P<speaker>\b(?P<name>[A-Z][\w'’-]*)\s+\(S\d+\)\s+"
        r"says in an off-screen voiceover:\s*<d>.*?</d>)"
        r"(?!\s+while\s+(?:his|her|their|[A-Z][\w'’-]*'s)\s+lips\s+remain\s+completely\s+closed)",
        re.I | re.S,
    )

    def close_lips(match: re.Match[str]) -> str:
        name = match.group("name")
        pronoun = "her" if name.lower() == "jill" else "his"
        return f"{match.group('speaker')} while {pronoun} lips remain completely closed"

    text = voiceover.sub(close_lips, text)
    text = re.sub(r"([.!?])</d>\s*[.!?,;:]+", r"\1</d>", text)
    result[DESCRIPTION] = _clean_space(text)


def _repair_non_speaking_ids(
    result: dict[str, Any], context: Mapping[str, Any]
) -> None:
    """Use Subject tags, not speaker IDs, in purely visual sentences."""

    names, subjects, _ = _subject_maps(context)
    canonical_names = {name.casefold(): (name, number) for name, number in names.items()}
    pieces = re.split(r"(?<=[.!?])\s+", result[DESCRIPTION])

    def remove_id(match: re.Match[str]) -> str:
        tag = match.group("tag") or ""
        written_name = match.group("name")
        known = canonical_names.get(written_name.casefold())
        if known is None:
            return f"{tag}{written_name}".strip()
        canonical_name, number = known
        if number in subjects:
            return f"<Subject {number}> {canonical_name}"
        return canonical_name

    repaired = []
    for piece in pieces:
        if "<d>" not in piece.lower():
            piece = re.sub(
                r"(?P<tag><Subject\s+\d+>\s*)?"
                r"(?P<name>[A-Z][\w'’-]*)\s*"
                r"\(\s*S\d+(?:\s*,\s*S\d+)*\s*\)",
                remove_id,
                piece,
            )
        repaired.append(piece)
    result[DESCRIPTION] = _clean_space(" ".join(repaired))


def _validate_non_speaking_ids(
    result: Mapping[str, Any], context: Mapping[str, Any]
) -> list[str]:
    del context
    for piece in re.split(r"(?<=[.!?])\s+", str(result.get(DESCRIPTION, ""))):
        if "<d>" in piece.lower():
            continue
        if re.search(
            r"\b[A-Z][\w'’-]*\s*\(\s*S\d+(?:\s*,\s*S\d+)*\s*\)",
            piece,
        ):
            return [
                "A non-speaking person uses a speaker ID; use the defined "
                "<Subject N> identity tag instead."
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
    result[COMPLETIONS] = [current] if current is not None and current in parsed else []
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
    expected = f"[Shot {_segment_number(context)}]"
    issues = []
    shots = _SHOT.findall(text)
    if len(shots) != 1 or not text.startswith(expected):
        issues.append(f"Description must contain exactly one opening {expected} marker.")
    if re.match(
        rf"^{re.escape(expected)}\s+(?:(?:At\s+)?(?:00?:)?00(?:\.0+)?|"
        rf"At\s+0+(?:\.0+)?\s*seconds?)",
        text,
        re.I,
    ):
        issues.append("The opening shot must not have a timestamp.")
    if re.search(r"(?i)reference pictures align|fully referenced", text):
        issues.append("Reference-image alignment instructions do not apply to this pipeline.")
    if context.get("hard_cut_required") and not text.startswith(
        f"{expected} Camera cuts to a new shot:"
    ):
        issues.append("This segment requires the exact hard-cut opening form.")
    return issues


def _validate_camera(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    del context
    if re.search(
        r"(?i)\b(?:camera motion|amplitude|speed|arc shot|static medium close[- ]up|"
        r"tilt down)\s*:",
        str(result.get(DESCRIPTION, "")),
    ):
        return ["Camera motion remains as stacked labels instead of natural prose."]
    return []


def _validate_subject_tags(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    _, subjects, pictures = _subject_maps(context)
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
    return issues


def _validate_dialogue(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    text = str(result.get(DESCRIPTION, ""))
    names, _, _ = _subject_maps(context)
    issues = []
    if text.lower().count("<d>") != text.lower().count("</d>"):
        issues.append("Dialogue tags are unbalanced.")
    for block in re.findall(r"<d>(.*?)</d>", text, re.I | re.S):
        if not re.match(r"\s*\[English\]\s+\S", block):
            issues.append("Every dialogue block must begin with [English].")
        if re.match(r"\s*\[English\]\s*\[[^\]]+\]", block, re.I):
            issues.append("Non-language delivery cues must appear outside <d> dialogue text.")
    for name, canonical in names.items():
        if re.search(rf"\b{re.escape(name)}\b\s*\(S(?!{canonical}\b)\d+\)", text, re.I):
            issues.append(f"{name} must consistently use speaker ID (S{canonical}).")
    for match in re.finditer(r"says in an off-screen voiceover:\s*<d>.*?</d>", text, re.I | re.S):
        after = text[match.end():match.end() + 100]
        if not re.match(
            r"\s+while\s+(?:his|her|their|[A-Z][\w'’-]*'s)\s+lips remain completely closed",
            after,
            re.I,
        ):
            issues.append("Every voiceover must state that the on-screen character's lips remain closed.")
    for clause in re.finditer(
        r"while\s+(?:his|her|their|[A-Z][\w'â€™-]*'s)\s+lips\s+remain\s+completely\s+closed",
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
                r"\b(?:the\s+)?[A-Za-z][\w'â€™-]*(?:\s+[A-Za-z][\w'â€™-]*){0,3}\s+"
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
    concrete = re.search(
        r"(?i)\b(?:piano|strings?|cello|violin|brass|drums?|percussion|guitar|"
        r"synth|electronic|notes?|tempo|rhythm|pulse|chord|volume)\b",
        value,
    )
    if abstract and not concrete:
        issues.append("Music uses abstract mood language without concrete musical details.")
    return issues


def _validate_completions(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    values = result.get(COMPLETIONS)
    if not isinstance(values, list) or any(not isinstance(value, int) for value in values):
        return ["completed_beat_ids must contain only integer metadata IDs."]
    current = _next_beat_id(context)
    if any(value != current for value in values):
        return ["Only the current NEXT beat may be reported complete."]
    if re.search(r"(?i)completed_beat_ids|\bB\d{3}\b", str(result.get(DESCRIPTION, ""))):
        return ["Beat completion IDs must not appear in rendered prompt text."]
    return []


def _semantic_requirements(beat_text: str) -> list[tuple[str, tuple[str, ...]]]:
    lower = beat_text.lower()
    requirements: list[tuple[str, tuple[str, ...]]] = []
    if "mark" in lower:
        requirements.append(("Mark", (r"\bMark\b",)))
    if "jill" in lower:
        requirements.append(("Jill", (r"\bJill\b",)))
    if "family" in lower:
        requirements.append(("Mark's family", (r"\bfamil(?:y|ies)\b",)))
    if "saucer" in lower:
        requirements.append(("flying saucers", (r"\bsaucers?\b",)))
    if "overhead" in lower:
        requirements.append(("overhead flight", (r"\boverhead\b", r"\bacross the sky\b")))
    if "run away" in lower:
        requirements.append(("the family running away", (r"\brun(?:s|ning)?\b", r"\bflee(?:s|ing)?\b")))
    if "abduct" in lower:
        requirements.append(("visible abduction action", (r"\babduct", r"\bseiz", r"\blift", r"\bcarry")))
        requirements.append(("a completed abduction outcome", (
            r"\binto the (?:craft|saucer|ship)\b", r"\bempty (?:ground|pavement|space)\b",
            r"\babduction (?:is |was )?(?:visibly )?complete", r"\bcarrying .*? into\b",
        )))
    return requirements


def _validate_semantics(result: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    current = _next_beat_id(context)
    completed = result.get(COMPLETIONS, [])
    require_completion = bool(context.get("beat_deadline_required")) or (
        current is not None and current in completed
    )

    description = str(result.get(DESCRIPTION, ""))
    beat_text = str(context.get("current_beat_text", "") or "")
    issues = []
    if require_completion:
        for label, alternatives in _semantic_requirements(beat_text):
            if not any(re.search(pattern, description, re.I | re.S) for pattern in alternatives):
                beat = f"B{current:03d}" if current is not None else "current beat"
                issues.append(f"{beat} is missing required visible content: {label}.")

        if "talk" in beat_text.lower():
            def attributed(name: str, speaker: int) -> bool:
                return bool(re.search(
                    rf"(?:<Subject\s+\d+>\s*)?\b{re.escape(name)}\b\s*"
                    rf"\(S{speaker}\)[^<>.!?]{{0,160}}"
                    rf"(?:says|asks|answers|replies|shouts|whispers|yells|tells|exclaims)"
                    rf"[^<>.!?]{{0,100}}:\s*<d>.*?</d>",
                    description,
                    re.I | re.S,
                ))

            if not attributed("Mark", 1) or not attributed("Jill", 2):
                beat = f"B{current:03d}" if current is not None else "current beat"
                issues.append(
                    f"{beat} requires a Mark/Jill exchange with one attributed Mark (S1) "
                    "dialogue block and one attributed Jill (S2) dialogue block."
                )

        if current is not None and current not in completed:
            issues.append(f"B{current:03d} reached its deadline but was not reported complete.")

        visible_action = re.search(r"\b(?:run away|flee|abduct|lift|seize)\b", beat_text, re.I)
        if visible_action and re.search(
            r"\b(?:Mark|Jill|the family|Mark's family)\b[^.!?]{0,60}"
            r"\b(?:unseen|off[- ]screen|not visible|out of view)\b",
            description,
            re.I,
        ):
            issues.append("Required beat action cannot be completed by subjects described as unseen.")

    recent_raw = context.get("recent_descriptions", []) or []
    if isinstance(recent_raw, str):
        recent_raw = [recent_raw]
    recent = " ".join(
        str(item.get(DESCRIPTION, "")) if isinstance(item, Mapping) else str(item)
        for item in recent_raw
    )
    if re.search(r"\b(?:son|child|children)\b", recent, re.I):
        composition = re.search(
            r"\b(?:family|Mark's family)\s+(?:consists of|is made up of|includes only)\s+"
            r"(?P<members>[^.!?]+)",
            description,
            re.I,
        )
        alone = re.search(r"\b(?:only|just)\s+Mark\s+and\s+Jill\b|\bMark and Jill are alone\b", description, re.I)
        if alone or (
            composition
            and not re.search(r"\b(?:son|child|children)\b", composition.group("members"), re.I)
        ):
            issues.append(
                "Family composition contradicts the recently established son or child."
            )

    # Flag only unmistakable enactment of a later beat; shared nouns alone are
    # not sufficient evidence of progression leakage.
    later = " ".join(str(item) for item in context.get("later_beat_texts", []) or []).lower()
    if "abduct" in later and re.search(r"\b(?:abduct\w*|seizes? .* family|lifts? .* family)\b", description, re.I):
        issues.append("Description prematurely enacts the later abduction beat.")
    if "talk" in later and len(re.findall(r"<d>.*?</d>", description, re.I | re.S)) >= 2:
        issues.append("Description prematurely enacts the later Mark/Jill conversation beat.")
    if (
        "saucer" in later
        and not re.search(r"\b(?:saucers?|talk\w*|figure out|what is happening)\b", beat_text, re.I)
        and re.search(r"\bsaucers?\b", description, re.I)
    ):
        issues.append("Description prematurely introduces the later flying-saucer beat.")
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


__all__ = [
    "RULE_REGISTRY",
    "format_ministral_prompt",
    "validate_ministral_prompt",
]
