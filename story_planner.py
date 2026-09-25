"""Deterministic source-span and chapter planning helpers.

This module intentionally owns only structure. Narrative judgments such as
``terminal`` and ``hard_reset`` are supplied by narrow semantic classifiers.
The functions here must not invent, paraphrase, or reinterpret story content.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


_SENTENCE_END_RE = re.compile(r"[.!?](?=\\s|$)")


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
                "Question: Does TARGET UNIT itself decisively end the story's "
                "central conflict/process, rather than merely preparing for it "
                "or closing the story after it was already resolved?\n"
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
                "A HARD RESET means a discontinuity between narrative phases: "
                "an explicit time jump, scene break, relocation after a completed "
                "phase, or equivalent restart. Immediate cause-and-effect action "
                "in the same continuous sequence is NOT a hard reset, even if "
                "danger, equipment, or physical location changes.\n\n"
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
