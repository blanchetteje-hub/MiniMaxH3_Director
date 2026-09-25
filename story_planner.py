"""Deterministic source-span and chapter planning helpers.

This module intentionally owns only structure. Narrative judgments such as
``terminal`` and ``hard_reset`` are supplied by narrow semantic classifiers.
The functions here must not invent, paraphrase, or reinterpret story content.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")


@dataclass(frozen=True)
class SourceUnit:
    """One exact, ordered span from ``story.txt``."""

    id: int
    start: int
    end: int
    text: str
    terminal: bool = False
    hard_reset: bool = False

    def with_flags(
        self,
        *,
        terminal: bool | None = None,
        hard_reset: bool | None = None,
    ) -> "SourceUnit":
        return SourceUnit(
            id=self.id,
            start=self.start,
            end=self.end,
            text=self.text,
            terminal=self.terminal if terminal is None else bool(terminal),
            hard_reset=self.hard_reset if hard_reset is None else bool(hard_reset),
        )


@dataclass(frozen=True)
class ChapterSpan:
    """One chapter built directly from contiguous authoritative source units."""

    chapter: int
    source_unit_ids: tuple[int, ...]
    start: int
    end: int
    source_text: str


def enumerate_source_units(story: str) -> list[SourceUnit]:
    """Split story text conservatively into sentence-sized exact spans.

    Unit text is always copied directly from ``story``. Whitespace between
    units is not rewritten; chapter construction slices the original story
    from the first unit start through the last unit end.
    """

    story = str(story or "")
    units: list[SourceUnit] = []
    cursor = 0

    for match in _SENTENCE_END_RE.finditer(story):
        end = match.end()
        start = cursor
        while start < end and story[start].isspace():
            start += 1
        while end > start and story[end - 1].isspace():
            end -= 1
        if start < end:
            units.append(
                SourceUnit(
                    id=len(units) + 1,
                    start=start,
                    end=end,
                    text=story[start:end],
                )
            )
        cursor = match.end()

    start = cursor
    while start < len(story) and story[start].isspace():
        start += 1
    end = len(story)
    while end > start and story[end - 1].isspace():
        end -= 1
    if start < end:
        units.append(
            SourceUnit(
                id=len(units) + 1,
                start=start,
                end=end,
                text=story[start:end],
            )
        )

    return units


def _validate_ordered_units(units: Sequence[SourceUnit]) -> None:
    expected_id = 1
    previous_end = -1
    for unit in units:
        if unit.id != expected_id:
            raise ValueError(
                f"Source units must use contiguous 1-based IDs; expected "
                f"{expected_id}, received {unit.id}."
            )
        if unit.start < 0 or unit.end <= unit.start:
            raise ValueError(f"Source unit {unit.id} has an invalid source span.")
        if unit.start < previous_end:
            raise ValueError("Source unit spans must not overlap or move backward.")
        previous_end = unit.end
        expected_id += 1


def derive_chapter_boundaries(units: Sequence[SourceUnit]) -> list[int]:
    """Return source-unit IDs after which a new chapter begins.

    Rules are deliberately mechanical:

    * a HARD_RESET starts a new chapter, so split immediately before it;
    * a TERMINAL unit starts a final closure chapter only when another unit
      follows and that following unit is not itself a HARD_RESET;
    * a final TERMINAL stays in the current chapter;
    * a TERMINAL immediately followed by HARD_RESET stays with its current
      phase; the split occurs at the reset instead.
    """

    units = list(units)
    if not units:
        return []
    _validate_ordered_units(units)

    boundaries: set[int] = set()
    for index, unit in enumerate(units):
        if index > 0 and unit.hard_reset:
            boundaries.add(units[index - 1].id)

        if not unit.terminal or index == len(units) - 1:
            continue
        next_unit = units[index + 1]
        if not next_unit.hard_reset and index > 0:
            boundaries.add(units[index - 1].id)

    return sorted(boundaries)


def build_chapter_spans(
    story: str,
    units: Sequence[SourceUnit],
    boundaries_after: Iterable[int] | None = None,
) -> list[ChapterSpan]:
    """Build exact contiguous chapter source spans from source-unit boundaries."""

    story = str(story or "")
    units = list(units)
    if not units:
        return []
    _validate_ordered_units(units)

    valid_boundary_ids = {unit.id for unit in units[:-1]}
    boundaries = set(
        derive_chapter_boundaries(units)
        if boundaries_after is None
        else (int(value) for value in boundaries_after)
    )
    unknown = boundaries - valid_boundary_ids
    if unknown:
        raise ValueError(
            "Chapter boundaries must reference non-final source-unit IDs: "
            + ", ".join(str(value) for value in sorted(unknown))
        )

    chapters: list[ChapterSpan] = []
    chapter_units: list[SourceUnit] = []
    for unit in units:
        chapter_units.append(unit)
        if unit.id in boundaries or unit.id == units[-1].id:
            first = chapter_units[0]
            last = chapter_units[-1]
            chapters.append(
                ChapterSpan(
                    chapter=len(chapters) + 1,
                    source_unit_ids=tuple(item.id for item in chapter_units),
                    start=first.start,
                    end=last.end,
                    source_text=story[first.start:last.end],
                )
            )
            chapter_units = []

    return chapters


def allocate_chapter_beats(
    chapters: Sequence[ChapterSpan],
    total_beats: int,
    *,
    emphasized_source_unit_ids: Iterable[int] = (),
) -> list[int]:
    """Allocate beats without moving source material between chapters.

    Every authoritative source unit receives one minimum beat of capacity.
    Remaining beats go to chapters containing explicitly emphasized source
    units. If no emphasis is supplied, the largest chapter receives the
    remainder; ties go to the earlier chapter.
    """

    chapters = list(chapters)
    if not chapters:
        if int(total_beats) == 0:
            return []
        raise ValueError("Cannot allocate beats without chapters.")

    if isinstance(total_beats, bool):
        raise ValueError("total_beats must be a positive integer.")
    total_beats = int(total_beats)
    if total_beats <= 0:
        raise ValueError("total_beats must be a positive integer.")

    counts = [len(chapter.source_unit_ids) for chapter in chapters]
    minimum = sum(counts)
    if total_beats < minimum:
        raise ValueError(
            f"{total_beats} beats cannot explicitly represent {minimum} "
            "authoritative source units."
        )

    remaining = total_beats - minimum
    if remaining == 0:
        return counts

    emphasized = {int(value) for value in emphasized_source_unit_ids}
    target_indices = [
        index
        for index, chapter in enumerate(chapters)
        if emphasized.intersection(chapter.source_unit_ids)
    ]
    if not target_indices:
        largest = max(counts)
        target_indices = [counts.index(largest)]

    cursor = 0
    while remaining:
        counts[target_indices[cursor % len(target_indices)]] += 1
        cursor += 1
        remaining -= 1

    return counts


def assign_source_units_to_beats(
    source_unit_ids: Sequence[int],
    beat_count: int,
    *,
    repeatable_source_unit_ids: Iterable[int] = (),
) -> list[tuple[int, ...]]:
    """Create a monotonic beat/source-unit assignment.

    Each source unit appears once initially. Extra beats may repeat only
    explicitly repeatable units, preserving source order. Repeated units are
    always assigned alone, which prevents unrelated source-unit mixing.
    """

    ids = [int(value) for value in source_unit_ids]
    if not ids:
        if int(beat_count) == 0:
            return []
        raise ValueError("Cannot assign beats without source units.")
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise ValueError("source_unit_ids must be unique and strictly increasing.")

    if isinstance(beat_count, bool):
        raise ValueError("beat_count must be a positive integer.")
    beat_count = int(beat_count)
    if beat_count < len(ids):
        raise ValueError(
            f"{beat_count} beats cannot explicitly represent "
            f"{len(ids)} source units."
        )

    extra = beat_count - len(ids)
    repeatable_set = {int(value) for value in repeatable_source_unit_ids}
    repeatable = [value for value in ids if value in repeatable_set]
    if extra and not repeatable:
        raise ValueError(
            "Extra beats require at least one explicitly repeatable source unit."
        )

    repeats_by_id = {value: 0 for value in ids}
    for index in range(extra):
        repeats_by_id[repeatable[index % len(repeatable)]] += 1

    assignments: list[tuple[int, ...]] = []
    for unit_id in ids:
        assignments.append((unit_id,))
        assignments.extend((unit_id,) for _ in range(repeats_by_id[unit_id]))
    return assignments


_BINARY_DECISION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "story_unit_binary_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["YES", "NO"]},
                "reason": {"type": "string", "minLength": 1},
            },
            "required": ["decision", "reason"],
            "additionalProperties": False,
        },
    },
}


def build_binary_decision_response_format() -> dict:
    """Return the strict JSON schema used by narrow source-unit classifiers."""

    return _BINARY_DECISION_RESPONSE_FORMAT


def build_terminal_messages(story: str, unit: SourceUnit) -> list[dict[str, str]]:
    """Ask only whether one unit itself ends the central story process."""

    return [
        {
            "role": "system",
            "content": (
                "Answer only the requested binary semantic question. "
                "Return valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "FULL STORY:\n"
                f"{str(story or '').strip()}\n\n"
                "TARGET UNIT:\n"
                f"{unit.id}. {unit.text}\n\n"
                "Use FULL STORY only to identify the central conflict/process.\n"
                "Judge only what TARGET UNIT itself explicitly accomplishes. "
                "Do not credit TARGET UNIT for a later event elsewhere in the "
                "story. An ongoing/repeated main-process statement is NO unless "
                "this unit itself explicitly completes/resolves/ends that process.\n"
                "Does TARGET UNIT itself decisively end the central conflict/process?\n"
                "Choose one: YES or NO.\n"
                "Return JSON with keys decision and reason."
            ),
        },
    ]


def build_hard_reset_messages(
    previous_unit: SourceUnit,
    unit: SourceUnit,
) -> list[dict[str, str]]:
    """Ask only whether a unit begins after a real narrative discontinuity."""

    return [
        {
            "role": "system",
            "content": (
                "Answer only the requested binary semantic question. "
                "Return valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "PREVIOUS UNIT:\n"
                f"{previous_unit.text}\n\n"
                "TARGET UNIT:\n"
                f"{unit.text}\n\n"
                "A HARD RESET means a discontinuity explicitly established by "
                "the source text between actual narrative phases: an explicit time "
                "jump, explicit scene break, explicitly stated relocation after a "
                "completed phase, or equivalent textual restart. A duration phrase "
                "such as 'for most of the night', 'for hours', 'throughout the day', "
                "or 'repeatedly' describes how long an activity lasts; it is NOT by "
                "itself a jump from PREVIOUS UNIT. Likewise, ordinary movement into "
                "a new place (entering a room/building, crossing a doorway, walking "
                "to another area) is NOT a hard reset unless the source explicitly "
                "marks a narrative restart around that relocation. Do NOT infer a "
                "cut, time passage, relocation, montage break, or new phase from "
                "what a film would typically do, from preparation changing into "
                "action, from a summary/duration statement, or from a change in "
                "activity alone. If the discontinuity is not stated or directly "
                "entailed by the two source units, answer NO. A "
                "genre/premise/summary sentence is NOT an actual completed phase, "
                "so moving from framing into the story's first concrete scene is "
                "NO. Immediate cause-and-effect action in the same continuous "
                "sequence is NOT a hard reset, even if danger, equipment, or "
                "physical location changes.\n\n"
                "Does TARGET UNIT begin after a HARD RESET from PREVIOUS UNIT?\n"
                "Choose one: YES or NO.\n"
                "Return JSON with keys decision and reason."
            ),
        },
    ]


def parse_binary_decision(raw_result: object) -> bool:
    """Parse one strict YES/NO classifier result into a boolean."""

    candidate = raw_result
    if isinstance(candidate, str):
        import json

        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("Binary decision response must be valid JSON.") from error

    if not isinstance(candidate, dict):
        raise ValueError("Binary decision response must be a JSON object.")
    if set(candidate) != {"decision", "reason"}:
        raise ValueError(
            "Binary decision response must contain only decision and reason."
        )
    decision = candidate.get("decision")
    reason = candidate.get("reason")
    if decision not in {"YES", "NO"}:
        raise ValueError("Binary decision must be YES or NO.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Binary decision reason must be a non-empty string.")
    return decision == "YES"


def classify_source_units(
    story: str,
    units: Sequence[SourceUnit],
    llm_request,
    *,
    history_metadata: dict | None = None,
    sampling_parameters: dict | None = None,
) -> list[SourceUnit]:
    """Classify terminal/hard-reset flags with two narrow LLM calls per unit.

    Unit 1 can never be a hard reset because no earlier source phase exists.
    All structural chapter decisions remain Python-owned.
    """

    units = list(units)
    if not units:
        return []
    _validate_ordered_units(units)

    sampling = dict(sampling_parameters or {})
    history = dict(history_metadata or {})
    classified: list[SourceUnit] = []

    for index, unit in enumerate(units):
        terminal_raw = llm_request(
            build_terminal_messages(story, unit),
            response_format=build_binary_decision_response_format(),
            history_metadata={
                **history,
                "purpose": "source_unit_terminal",
                "source_unit_id": unit.id,
            },
            **sampling,
        )
        terminal = parse_binary_decision(terminal_raw)

        hard_reset = False
        if index > 0:
            reset_raw = llm_request(
                build_hard_reset_messages(units[index - 1], unit),
                response_format=build_binary_decision_response_format(),
                history_metadata={
                    **history,
                    "purpose": "source_unit_hard_reset",
                    "source_unit_id": unit.id,
                },
                **sampling,
            )
            hard_reset = parse_binary_decision(reset_raw)

        classified.append(
            unit.with_flags(
                terminal=terminal,
                hard_reset=hard_reset,
            )
        )

    return classified


@dataclass(frozen=True)
class CutCandidate:
    """One deterministic exact cut point inside a source unit."""

    label: str
    offset: int
    left_text: str
    right_text: str


_SPLIT_DECISION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "story_unit_split_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["SPLIT", "KEEP_TOGETHER"],
                },
                "reason": {"type": "string", "minLength": 1},
            },
            "required": ["decision", "reason"],
            "additionalProperties": False,
        },
    },
}


def build_split_decision_response_format() -> dict:
    return _SPLIT_DECISION_RESPONSE_FORMAT


def build_source_unit_split_messages(
    story: str,
    unit: SourceUnit,
) -> list[dict[str, str]]:
    """Ask whether one sentence-sized unit crosses an internal large phase."""

    return [
        {
            "role": "system",
            "content": (
                "Decide only whether this one authoritative source unit crosses "
                "an internal LARGE H3 chapter phase boundary. Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "SOURCE UNIT:\n"
                f"{unit.text}\n\n"
                "A chapter is a LARGE H3 refresh unit.\n"
                "Choose SPLIT only in either case:\n"
                "1. this unit contains an explicit substantial time jump/scene break "
                "between two narrative phases; or\n"
                "2. this unit explicitly describes a long/repeated main process "
                "(for example majority, most, repeatedly, throughout, or equivalent "
                "duration/repetition wording) followed by its explicit terminal "
                "resolution. A one-time finite action chain is NOT this case.\n"
                "Otherwise choose KEEP_TOGETHER. Ordinary movement, danger changes, "
                "tool/weapon changes, terminal resolution plus immediate closure, "
                "and continuous work stay together.\n"
                "Choose one: SPLIT or KEEP_TOGETHER.\n"
                "Return JSON with keys decision and reason."
            ),
        },
    ]


def parse_split_decision(raw_result: object) -> bool:
    """Return True only for a strict SPLIT result."""

    candidate = raw_result
    if isinstance(candidate, str):
        import json

        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("Split decision response must be valid JSON.") from error
    if not isinstance(candidate, dict):
        raise ValueError("Split decision response must be a JSON object.")
    if set(candidate) != {"decision", "reason"}:
        raise ValueError("Split decision must contain only decision and reason.")
    decision = candidate.get("decision")
    reason = candidate.get("reason")
    if decision not in {"SPLIT", "KEEP_TOGETHER"}:
        raise ValueError("Split decision must be SPLIT or KEEP_TOGETHER.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Split decision reason must be a non-empty string.")
    return decision == "SPLIT"


def enumerate_cut_candidates(unit: SourceUnit) -> list[CutCandidate]:
    """Enumerate exact grammatical cut points without rewriting source text."""

    text = unit.text
    offsets: set[int] = set()

    for match in re.finditer(r"[,;:](?=\s)", text):
        offsets.add(match.end())

    for match in re.finditer(
        r"\s+(?=(?:and|but|then|while|after|before|when)\b)",
        text,
        flags=re.IGNORECASE,
    ):
        offsets.add(match.start())

    candidates: list[CutCandidate] = []
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for offset in sorted(offsets):
        left = text[:offset].rstrip()
        right = text[offset:].lstrip()
        if len(left) < 8 or len(right) < 8:
            continue
        normalized_offset = len(text[:offset].rstrip())
        while normalized_offset < len(text) and text[normalized_offset].isspace():
            normalized_offset += 1
        right_start = normalized_offset
        left_end = offset
        while left_end > 0 and text[left_end - 1].isspace():
            left_end -= 1
        if left_end <= 0 or right_start >= len(text):
            continue
        candidates.append(
            CutCandidate(
                label=(
                    labels[len(candidates)]
                    if len(candidates) < len(labels)
                    else str(len(candidates) + 1)
                ),
                offset=right_start,
                left_text=text[:left_end],
                right_text=text[right_start:],
            )
        )
    return candidates


def build_cut_choice_messages(
    unit: SourceUnit,
    candidates: Sequence[CutCandidate],
) -> list[dict[str, str]]:
    """Ask for one exact deterministic cut after a prior SPLIT decision."""

    candidate_lines = []
    for candidate in candidates:
        candidate_lines.append(
            f"CANDIDATE {candidate.label}:\n"
            f"LEFT = {candidate.left_text}\n"
            f"RIGHT = {candidate.right_text}"
        )
    allowed = ", ".join(candidate.label for candidate in candidates)
    return [
        {
            "role": "system",
            "content": (
                "The prior unit gate already returned SPLIT. Choose only the "
                "best supplied exact cut point. Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "SOURCE UNIT:\n"
                f"{unit.text}\n\n"
                + "\n\n".join(candidate_lines)
                + "\n\n"
                f"Choose one value from: {allowed}, NONE.\n"
                "Prefer the cut that keeps the ongoing/main process on the left "
                "and the distinct terminal/reset phase on the right. Do not "
                "rewrite either side.\n"
                "Return JSON with keys choice and reason."
            ),
        },
    ]


def build_cut_choice_response_format(
    candidates: Sequence[CutCandidate],
) -> dict:
    choices = [candidate.label for candidate in candidates] + ["NONE"]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "story_unit_cut_choice",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "choice": {"type": "string", "enum": choices},
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["choice", "reason"],
                "additionalProperties": False,
            },
        },
    }


def parse_cut_choice(
    raw_result: object,
    candidates: Sequence[CutCandidate],
) -> CutCandidate | None:
    """Parse one supplied candidate label or NONE."""

    candidate_result = raw_result
    if isinstance(candidate_result, str):
        import json

        try:
            candidate_result = json.loads(candidate_result)
        except json.JSONDecodeError as error:
            raise ValueError("Cut choice response must be valid JSON.") from error
    if not isinstance(candidate_result, dict):
        raise ValueError("Cut choice response must be a JSON object.")
    if set(candidate_result) != {"choice", "reason"}:
        raise ValueError("Cut choice must contain only choice and reason.")
    reason = candidate_result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Cut choice reason must be a non-empty string.")

    by_label = {candidate.label: candidate for candidate in candidates}
    choice = candidate_result.get("choice")
    if choice == "NONE":
        return None
    if choice not in by_label:
        raise ValueError("Cut choice did not name a supplied candidate.")
    return by_label[choice]


def refine_source_units(
    story: str,
    units: Sequence[SourceUnit],
    llm_request,
    *,
    history_metadata: dict | None = None,
    sampling_parameters: dict | None = None,
) -> list[SourceUnit]:
    """Refine only units explicitly gated SPLIT, preserving exact source spans."""

    units = list(units)
    if not units:
        return []
    _validate_ordered_units(units)

    sampling = dict(sampling_parameters or {})
    history = dict(history_metadata or {})
    refined_spans: list[tuple[int, int]] = []

    for unit in units:
        # If Python cannot enumerate a legal exact cut point, the unit cannot
        # be split without rewriting story.txt. Keep it without spending an LLM
        # call or inviting the model to invent a boundary.
        candidates = enumerate_cut_candidates(unit)
        if not candidates:
            refined_spans.append((unit.start, unit.end))
            continue

        split_raw = llm_request(
            build_source_unit_split_messages(story, unit),
            response_format=build_split_decision_response_format(),
            history_metadata={
                **history,
                "purpose": "source_unit_split_gate",
                "source_unit_id": unit.id,
            },
            **sampling,
        )
        if not parse_split_decision(split_raw):
            refined_spans.append((unit.start, unit.end))
            continue

        cut_raw = llm_request(
            build_cut_choice_messages(unit, candidates),
            response_format=build_cut_choice_response_format(candidates),
            history_metadata={
                **history,
                "purpose": "source_unit_cut_choice",
                "source_unit_id": unit.id,
            },
            **sampling,
        )
        chosen = parse_cut_choice(cut_raw, candidates)
        if chosen is None:
            refined_spans.append((unit.start, unit.end))
            continue

        absolute_cut = unit.start + chosen.offset
        left_end = absolute_cut
        while left_end > unit.start and story[left_end - 1].isspace():
            left_end -= 1
        right_start = absolute_cut
        while right_start < unit.end and story[right_start].isspace():
            right_start += 1

        if left_end <= unit.start or right_start >= unit.end:
            refined_spans.append((unit.start, unit.end))
            continue
        refined_spans.append((unit.start, left_end))
        refined_spans.append((right_start, unit.end))

    refined: list[SourceUnit] = []
    for start, end in refined_spans:
        refined.append(
            SourceUnit(
                id=len(refined) + 1,
                start=start,
                end=end,
                text=story[start:end],
            )
        )
    return refined


def plan_story_chapters(
    story: str,
    llm_request,
    *,
    history_metadata: dict | None = None,
    sampling_parameters: dict | None = None,
) -> tuple[list[SourceUnit], list[ChapterSpan]]:
    """Run the source-span planner through exact chapter construction."""

    units = enumerate_source_units(story)
    units = refine_source_units(
        story,
        units,
        llm_request,
        history_metadata=history_metadata,
        sampling_parameters=sampling_parameters,
    )
    units = classify_source_units(
        story,
        units,
        llm_request,
        history_metadata=history_metadata,
        sampling_parameters=sampling_parameters,
    )
    chapters = build_chapter_spans(story, units)
    return units, chapters


def build_visible_responsibility_messages(
    unit: SourceUnit,
) -> list[dict[str, str]]:
    """Ask only whether one source unit owns required visible beat material."""

    return [
        {
            "role": "system",
            "content": (
                "Decide only whether one authoritative source unit creates a "
                "concrete visible beat responsibility. Return valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "SOURCE UNIT:\n"
                f"{unit.text}\n\n"
                "YES = this unit itself requires a concrete on-screen event or "
                "visible state to happen in the adaptation.\n"
                "NO = this unit is genre/premise/summary framing or purely internal "
                "thought. A sentence saying what the film/story is ABOUT remains "
                "NO even if its premise names an action such as protecting, "
                "escaping, fighting, or surviving; later concrete source units own "
                "those actions.\n"
                "Choose one: YES or NO.\n"
                "Return JSON with keys decision and reason."
            ),
        },
    ]


def classify_visible_source_unit_ids(
    units: Sequence[SourceUnit],
    llm_request,
    *,
    history_metadata: dict | None = None,
    sampling_parameters: dict | None = None,
) -> list[int]:
    """Return source-unit IDs that own concrete visible beat responsibility."""

    units = list(units)
    if not units:
        return []
    _validate_ordered_units(units)

    sampling = dict(sampling_parameters or {})
    history = dict(history_metadata or {})
    visible_ids: list[int] = []

    for unit in units:
        raw_result = llm_request(
            build_visible_responsibility_messages(unit),
            response_format=build_binary_decision_response_format(),
            history_metadata={
                **history,
                "purpose": "source_unit_visible_responsibility",
                "source_unit_id": unit.id,
            },
            **sampling,
        )
        if parse_binary_decision(raw_result):
            visible_ids.append(unit.id)

    return visible_ids


_LOCAL_RELATION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "story_unit_local_relation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "relation": {
                    "type": "string",
                    "enum": ["MERGE", "NEW_TASK"],
                },
            },
            "required": ["relation"],
            "additionalProperties": False,
        },
    },
}


def build_local_relation_messages(
    left_unit: SourceUnit,
    right_unit: SourceUnit,
) -> list[dict[str, str]]:
    """Decide whether two adjacent finite visible units share one beat job."""

    return [
        {
            "role": "system",
            "content": (
                "Decide only whether two adjacent source responsibilities belong "
                "to one local beat job. Return valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "LEFT:\n"
                f"{left_unit.text}\n\n"
                "RIGHT:\n"
                f"{right_unit.text}\n\n"
                "Choose one:\n"
                "MERGE only when RIGHT's PRIMARY ACTION is one of these:\n"
                "- the same uninterrupted local action as LEFT;\n"
                "- a direct immediate response caused by the event in LEFT itself "
                "(for example alarm -> shut down/call for help); or\n"
                "- the immediate mechanical completion of the exact object/action "
                "LEFT just obtained/opened/started (retrieve -> equip, open -> remove).\n"
                "NEW_TASK when RIGHT's PRIMARY ACTION is a distinct objective after "
                "LEFT reaches a usable stopping point. A shared larger goal is not "
                "enough to MERGE. Carrying, wearing, or using an item from LEFT while "
                "performing a different primary task is NEW_TASK. Starting a fresh "
                "item/test after LEFT completed one is NEW_TASK.\n"
                "For causality, distinguish LEFT itself from a shared earlier cause: "
                "danger -> immediate protection may MERGE, but protection -> fetch "
                "gear is NEW_TASK because the gear retrieval responds to the danger, "
                "not to the completed protection action.\n"
                "Judge only the concrete local actions.\n"
                "Return JSON with the single key relation."
            ),
        },
    ]


def parse_local_relation(raw_result: object) -> str:
    """Parse one strict MERGE/NEW_TASK result."""

    candidate = raw_result
    if isinstance(candidate, str):
        import json

        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("Local relation response must be valid JSON.") from error
    if not isinstance(candidate, dict) or set(candidate) != {"relation"}:
        raise ValueError("Local relation response must contain only relation.")
    relation = candidate.get("relation")
    if relation not in {"MERGE", "NEW_TASK"}:
        raise ValueError("Local relation must be MERGE or NEW_TASK.")
    return str(relation)


def group_chapter_source_responsibilities(
    units: Sequence[SourceUnit],
    chapter: ChapterSpan,
    visible_source_unit_ids: Iterable[int],
    repeatable_source_unit_ids: Iterable[int],
    llm_request,
    *,
    history_metadata: dict | None = None,
    sampling_parameters: dict | None = None,
) -> tuple[tuple[int, ...], ...]:
    """Group visible finite units into local beat responsibilities.

    Explicitly repeatable units always remain isolated so Python can allocate
    surplus beats to them without asking the LLM to perform counting or pacing.
    Non-visible source units never consume beat capacity. A gap caused by a
    non-visible source unit is a conservative group boundary.
    """

    units = list(units)
    _validate_ordered_units(units)
    units_by_id = {unit.id: unit for unit in units}
    visible = {int(value) for value in visible_source_unit_ids}
    repeatable = {int(value) for value in repeatable_source_unit_ids}
    sampling = dict(sampling_parameters or {})
    history = dict(history_metadata or {})

    ordered_ids = [
        unit_id
        for unit_id in chapter.source_unit_ids
        if unit_id in visible
    ]
    if not ordered_ids:
        raise ValueError(
            f"Chapter {chapter.chapter} has no concrete visible source responsibility."
        )

    groups: list[tuple[int, ...]] = []
    current: list[int] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            groups.append(tuple(current))
            current = []

    for unit_id in ordered_ids:
        if unit_id in repeatable:
            flush_current()
            groups.append((unit_id,))
            continue

        if not current:
            current = [unit_id]
            continue

        left_id = current[-1]
        if unit_id != left_id + 1:
            flush_current()
            current = [unit_id]
            continue

        raw_relation = llm_request(
            build_local_relation_messages(
                units_by_id[left_id],
                units_by_id[unit_id],
            ),
            response_format=_LOCAL_RELATION_RESPONSE_FORMAT,
            history_metadata={
                **history,
                "purpose": "source_unit_local_relation",
                "left_source_unit_id": left_id,
                "right_source_unit_id": unit_id,
            },
            **sampling,
        )
        relation_value = parse_local_relation(raw_relation)
        if relation_value == "MERGE":
            current.append(unit_id)
        else:
            flush_current()
            current = [unit_id]

    flush_current()
    return tuple(groups)


def allocate_grouped_chapter_beats(
    chapter_groups: Sequence[Sequence[Sequence[int]]],
    total_beats: int,
    *,
    emphasized_source_unit_ids: Iterable[int] = (),
) -> list[int]:
    """Allocate beats from grouped visible responsibilities, not raw sentences."""

    groups = [tuple(tuple(item) for item in chapter) for chapter in chapter_groups]
    if not groups:
        if int(total_beats) == 0:
            return []
        raise ValueError("Cannot allocate beats without chapters.")
    if isinstance(total_beats, bool):
        raise ValueError("total_beats must be a positive integer.")
    total_beats = int(total_beats)
    if total_beats <= 0:
        raise ValueError("total_beats must be a positive integer.")

    counts = [len(chapter) for chapter in groups]
    if any(count <= 0 for count in counts):
        raise ValueError("Every chapter must own at least one visible responsibility.")
    minimum = sum(counts)
    if total_beats < minimum:
        raise ValueError(
            f"{total_beats} beats cannot represent {minimum} grouped visible "
            "source responsibilities."
        )

    remaining = total_beats - minimum
    if remaining == 0:
        return counts

    emphasized = {int(value) for value in emphasized_source_unit_ids}
    target_indices = []
    for index, chapter in enumerate(groups):
        owned_ids = {
            int(unit_id)
            for group in chapter
            for unit_id in group
        }
        if owned_ids.intersection(emphasized):
            target_indices.append(index)

    if not target_indices:
        largest = max(counts)
        target_indices = [counts.index(largest)]

    cursor = 0
    while remaining:
        counts[target_indices[cursor % len(target_indices)]] += 1
        cursor += 1
        remaining -= 1
    return counts


def expand_grouped_responsibilities_to_beats(
    groups: Sequence[Sequence[int]],
    beat_count: int,
    *,
    repeatable_source_unit_ids: Iterable[int] = (),
) -> tuple[tuple[int, ...], ...]:
    """Expand grouped responsibilities by repeating only explicit repeatables."""

    normalized = [tuple(int(value) for value in group) for group in groups]
    if not normalized:
        raise ValueError("Cannot assign beats without grouped responsibilities.")
    beat_count = int(beat_count)
    if beat_count < len(normalized):
        raise ValueError(
            f"{beat_count} beats cannot represent {len(normalized)} grouped "
            "source responsibilities."
        )

    extra = beat_count - len(normalized)
    repeatable = {int(value) for value in repeatable_source_unit_ids}
    repeatable_indices = [
        index
        for index, group in enumerate(normalized)
        if len(group) == 1 and group[0] in repeatable
    ]
    if extra and not repeatable_indices:
        raise ValueError(
            "Extra grouped beats require an explicitly repeatable source unit."
        )

    repeats_by_index = [0] * len(normalized)
    for offset in range(extra):
        index = repeatable_indices[offset % len(repeatable_indices)]
        repeats_by_index[index] += 1

    result: list[tuple[int, ...]] = []
    for index, group in enumerate(normalized):
        result.append(group)
        result.extend(group for _ in range(repeats_by_index[index]))
    return tuple(result)


_EXPLICIT_REPEATABLE_PATTERNS = (
    re.compile(r"\bmajority\b", re.IGNORECASE),
    re.compile(r"\bmost\s+of\b", re.IGNORECASE),
    re.compile(r"\brepeatedly\b", re.IGNORECASE),
    re.compile(r"\bthroughout\b", re.IGNORECASE),
    re.compile(r"\bover\s+and\s+over\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class PlannedChapter:
    """One fixed chapter with deterministic beat budget/source ownership."""

    chapter: int
    source_unit_ids: tuple[int, ...]
    source_text: str
    beat_count: int
    beat_source_unit_ids: tuple[tuple[int, ...], ...] | None


@dataclass(frozen=True)
class StoryPlan:
    """Complete source-authoritative planning result."""

    source_units: tuple[SourceUnit, ...]
    chapters: tuple[PlannedChapter, ...]

    @property
    def total_beats(self) -> int:
        return sum(chapter.beat_count for chapter in self.chapters)


def explicit_repeatable_source_unit_ids(
    units: Sequence[SourceUnit],
) -> list[int]:
    """Return units whose own source wording explicitly authorizes repetition."""

    result = []
    for unit in units:
        if any(pattern.search(unit.text) for pattern in _EXPLICIT_REPEATABLE_PATTERNS):
            result.append(unit.id)
    return result


def build_story_plan(
    story: str,
    total_beats: int,
    llm_request,
    *,
    history_metadata: dict | None = None,
    sampling_parameters: dict | None = None,
) -> StoryPlan:
    """Build a source-authoritative chapter plan with grouped beat ownership.

    The LLM makes only narrow semantic decisions: source-unit visibility and
    local finite-unit relationships. Python owns grouping, beat arithmetic,
    repeat allocation, chapter boundaries, and final source ownership.
    """

    units, chapter_spans = plan_story_chapters(
        story,
        llm_request,
        history_metadata=history_metadata,
        sampling_parameters=sampling_parameters,
    )
    repeatable = explicit_repeatable_source_unit_ids(units)
    visible = classify_visible_source_unit_ids(
        units,
        llm_request,
        history_metadata=history_metadata,
        sampling_parameters=sampling_parameters,
    )

    chapter_groups = [
        group_chapter_source_responsibilities(
            units,
            chapter,
            visible,
            repeatable,
            llm_request,
            history_metadata=history_metadata,
            sampling_parameters=sampling_parameters,
        )
        for chapter in chapter_spans
    ]
    beat_counts = allocate_grouped_chapter_beats(
        chapter_groups,
        total_beats,
        emphasized_source_unit_ids=repeatable,
    )

    planned = []
    repeatable_set = set(repeatable)
    for chapter, groups, beat_count in zip(
        chapter_spans,
        chapter_groups,
        beat_counts,
    ):
        chapter_repeatable = [
            unit_id
            for unit_id in chapter.source_unit_ids
            if unit_id in repeatable_set
        ]
        assignments = None
        if beat_count == len(groups):
            assignments = tuple(groups)
        elif chapter_repeatable:
            assignments = expand_grouped_responsibilities_to_beats(
                groups,
                beat_count,
                repeatable_source_unit_ids=chapter_repeatable,
            )

        planned.append(
            PlannedChapter(
                chapter=chapter.chapter,
                source_unit_ids=chapter.source_unit_ids,
                source_text=chapter.source_text,
                beat_count=beat_count,
                beat_source_unit_ids=assignments,
            )
        )

    result = StoryPlan(
        source_units=tuple(units),
        chapters=tuple(planned),
    )
    if result.total_beats != int(total_beats):
        raise ValueError(
            f"Story plan allocated {result.total_beats} beats; expected "
            f"{int(total_beats)}."
        )
    return result
