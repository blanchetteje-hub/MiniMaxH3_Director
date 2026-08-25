"""Qwen-specific formatting for MiniMax H3 prompt fields.

The repairs in this module are limited to patterns observed in Qwen responses.
The shared Ministral formatter still owns the common H3
schema and validation rules.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from formatter_base import BaseFormatter
import ministral_formatter as ministral


_ABSTRACT_MUSIC_WORDS = re.compile(
    r"(?i)\b(?:ominous|tense|sad|happy|hopeful|dramatic|emotional|scary|"
    r"mysterious)\b\s*,?\s*"
)
_SOUNDSCAPE_MUSIC_FRAGMENT = re.compile(
    r"(?i)\b(?:(?:lively|cheerful|distant|soft|faint|background)\s+)*"
    r"(?:theme[- ]park\s+)?music"
    r"(?:\s+(?:plays?|continues?|swells?|fades?)"
    r"(?:\s+in\s+the\s+background)?)?"
    r"(?:\s+in\s+the\s+background)?"
    r"\s*(?:,\s*|\s+(?:mixed|blended)\s+with\s+|\s+with\s+)?"
)
_TIMESTAMP = re.compile(
    r"(?i)\bAt\s+(?P<minutes>\d{1,2}):(?P<seconds>\d{2})\."
    r"(?P<milliseconds>\d{3})(?P<suffix>(?:\s+seconds?)?,)"
)


def _prepare_qwen_result(
    llm_result: Any,
    context: Mapping[str, Any],
) -> Any:
    """Repair Qwen field-local patterns before shared rules discard context."""

    if not isinstance(llm_result, Mapping):
        return llm_result

    prepared = copy.deepcopy(dict(llm_result))
    description = str(prepared.get(ministral.DESCRIPTION, "") or "")
    description = re.sub(
        r"(?i)(Camera\s+continues\s+from\s+the\s+previous\s+shot)\.{2,}",
        r"\1.",
        description,
    )

    # Qwen often writes "Mark's face as he says: <d>...".  Preserve the
    # camera prose while making the known speaker explicit for H3.
    records = ministral._subject_records(context)
    speech_verbs = (
        r"says|asks|answers|replies|shouts|whispers|yells|tells|"
        r"exclaims|narrates"
    )
    for name, record in sorted(records.items(), key=lambda item: -len(item[0])):
        speaker_id = record.get("speaker_id")
        if not speaker_id:
            continue
        description = re.sub(
            rf"\b({re.escape(name)}'s\s+[^.!?\n]{{0,100}}?\s+as\s+)"
            rf"(?:he|she|they)\s+(?P<verb>{speech_verbs})(?=\s*:?[^<>]{{0,40}}<d>)",
            lambda match, canonical=name, speaker=speaker_id: (
                f"{match.group(1)}{canonical} ({speaker}) "
                f"{match.group('verb')}"
            ),
            description,
            flags=re.I,
        )
    prepared[ministral.DESCRIPTION] = description

    soundscape = str(prepared.get(ministral.SOUNDSCAPE, "") or "")
    soundscape = _SOUNDSCAPE_MUSIC_FRAGMENT.sub("", soundscape)
    soundscape = " ".join(
        sentence
        for sentence in ministral._sentences(soundscape)
        if not re.search(r"\b[A-Z][\w'-]*'s\s+[^.!?]{0,60}'[^']+'", sentence)
    )
    soundscape = re.sub(r"(?i)^with\s+", "", soundscape).strip()
    if soundscape:
        soundscape = soundscape[0].upper() + soundscape[1:]
    prepared[ministral.SOUNDSCAPE] = soundscape

    music = str(prepared.get(ministral.MUSIC, "") or "")
    music = _ABSTRACT_MUSIC_WORDS.sub("", music)
    music = re.sub(
        r"(?i)\b(low|high|soft|loud)\s*,\s*"
        r"(?=(?:drone|tones?|notes?|strings?|brass|bass|piano|guitar)\b)",
        r"\1 ",
        music,
    )
    prepared[ministral.MUSIC] = music
    return prepared


def _clamp_terminal_timestamps(description: str, duration: Any) -> str:
    try:
        duration_ms = round(float(duration) * 1000)
    except (TypeError, ValueError):
        return description
    if duration_ms <= 0:
        return description

    terminal_matches = [
        match
        for match in _TIMESTAMP.finditer(description)
        if (
            int(match.group("minutes")) * 60_000
            + int(match.group("seconds")) * 1000
            + int(match.group("milliseconds"))
        ) >= duration_ms
    ]
    next_terminal = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal next_terminal
        timestamp_ms = (
            int(match.group("minutes")) * 60_000
            + int(match.group("seconds")) * 1000
            + int(match.group("milliseconds"))
        )
        if timestamp_ms < duration_ms:
            return match.group(0)
        replacement_ms = max(
            0,
            duration_ms - len(terminal_matches) + next_terminal,
        )
        next_terminal += 1
        minutes, remainder = divmod(replacement_ms, 60_000)
        seconds, milliseconds = divmod(remainder, 1000)
        return (
            f"At {minutes:02d}:{seconds:02d}.{milliseconds:03d}"
            f"{match.group('suffix')}"
        )

    return _TIMESTAMP.sub(replace, description)


def _remove_visual_speaker_ids(description: str) -> str:
    """Remove Qwen's identity-only speaker IDs while preserving dialogue IDs."""

    simple_id = re.compile(r"\(S\d+\)", re.I)
    speech = re.compile(
        r"(?i)^\s+(?:says|asks|answers|replies|shouts|whispers|yells|tells|"
        r"exclaims|narrates)\b[^<>]{0,80}<d>"
    )

    def replace(match: re.Match[str]) -> str:
        tail = description[match.end():match.end() + 120]
        return match.group(0) if speech.search(tail) else ""

    return simple_id.sub(replace, description)


class QwenFormatter(BaseFormatter):
    """Format locally tested Qwen responses for MiniMax H3."""

    def __init__(self) -> None:
        self._shared = ministral.MinistralFormatter()

    def format_prompt(
        self,
        llm_result: Any,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        safe_context: Mapping[str, Any] = context or {}
        prepared = _prepare_qwen_result(llm_result, safe_context)
        formatted = self._shared.format_prompt(prepared, safe_context)
        description = _remove_visual_speaker_ids(formatted[ministral.DESCRIPTION])
        description = re.sub(
            r"(?i)\((S\d+)\)\s+\(\1\)",
            r"(\1)",
            description,
        )
        formatted[ministral.DESCRIPTION] = _clamp_terminal_timestamps(
            re.sub(
                r"(?i)(Camera\s+continues\s+from\s+the\s+previous\s+shot\.)"
                r"\s*(?:\.\s*)+",
                r"\1 ",
                description,
            ),
            safe_context.get("segment_duration"),
        )
        return formatted

    def validate_prompt(
        self,
        result: Mapping[str, Any],
        context: Mapping[str, Any] | None,
    ) -> list[str]:
        return self._shared.validate_prompt(result, context)


__all__ = ["QwenFormatter"]
