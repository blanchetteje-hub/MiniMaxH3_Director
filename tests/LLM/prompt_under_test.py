from __future__ import annotations

import json
from collections.abc import Mapping

from tests.LLM.cases import BeatCase
from tests.LLM.llama_client import get_model_settings


_DEFAULT_STATE_STRINGS = frozenset({"n/a", "null"})


_INJURY_FIELDS = frozenset({
    "injury", "injuries", "current_injury", "current_injuries",
    "injury_status",
})
_INJURY_DEFAULT_STRINGS = frozenset({
    "none", "no injury", "no injuries", "not injured", "uninjured",
})


def compact_beat_validation_state(state: Mapping[str, object]) -> dict[str, object]:
    """Keep the benchmark's prompt context compaction in sync with production."""
    if not isinstance(state, dict):
        return {}

    def lookup_path(root, path):
        cursor = root
        for part in str(path).split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return False, None
            cursor = cursor[part]
        return True, cursor

    progress = state.get("story_progress")
    effects = progress.get("persistent_state_effects") if isinstance(progress, dict) else None
    redundant_effects = isinstance(effects, dict) and all(
        lookup_path(state, path)[0] and lookup_path(state, path)[1] == value
        for path, value in effects.items()
    )
    progress_bookkeeping = {
        "completed_required_event_ids", "pending_required_event_ids",
        "current_macro_phase",
    }

    def prune(value, key=None, path=()):
        if value is None:
            return None, True
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in _DEFAULT_STATE_STRINGS:
                return None, True
            if key in _INJURY_FIELDS and normalized in _INJURY_DEFAULT_STRINGS:
                return None, True
            return value, False
        if isinstance(value, list):
            result = []
            for item in value:
                compacted, omitted = prune(item, key=key, path=path)
                if not omitted:
                    result.append(compacted)
            return result, not result
        if isinstance(value, dict):
            result = {}
            for child_key, child_value in value.items():
                if not path and child_key == "version":
                    continue
                if path == ("story_progress",) and child_key in progress_bookkeeping:
                    continue
                if (
                    path == ("story_progress",)
                    and child_key == "persistent_state_effects"
                    and redundant_effects
                ):
                    continue
                compacted, omitted = prune(
                    child_value,
                    key=child_key,
                    path=path + (str(child_key),),
                )
                if not omitted:
                    result[child_key] = compacted
            return result, not result
        return value, False

    compacted, _ = prune(state)
    return compacted


def build_validation_messages(
    previous_final_beat,
    current_state,
    beat_job,
    next_beat_job,
    candidate_beat,
    settings=None,
    assigned_state_effects=None,
) -> list[dict[str, str]]:
    settings = settings or get_model_settings()
    state = compact_beat_validation_state(current_state)
    effects = assigned_state_effects if assigned_state_effects is not None else []
    system = (
        "You validate one candidate story beat. Judge meaning, not exact wording. "
        "Accept reasonable paraphrases and clear semantic implications. Reject "
        "only clear errors. Return one JSON object with boolean valid and string issue."
    )
    user = f"""
PREVIOUS FINAL BEAT
{previous_final_beat or "None; this is the first beat."}

CURRENT STATE
{json.dumps(state, ensure_ascii=False, separators=(",", ":"))}

CURRENT JOB
{beat_job}

NEXT JOB
{next_beat_job or "None; this is the final beat."}

STATE EFFECTS IF VALID
{json.dumps(effects, ensure_ascii=False, separators=(",", ":"))}

CANDIDATE BEAT
{candidate_beat}

CHECKS
A. CURRENT JOB: The candidate must accomplish the meaning of CURRENT JOB. Accept
paraphrases and clear implications, but require every materially required action
or result when the job has multiple parts. PREVIOUS FINAL BEAT is history only:
it may constrain what is possible, but it cannot satisfy, replace, or excuse any
action or result explicitly assigned to CURRENT JOB. Every such requirement must
be visibly accomplished by CANDIDATE BEAT. When CURRENT JOB explicitly assigns
an action to this beat, CANDIDATE BEAT must show that action being performed or
completed in this beat. Do not infer the required action only from an aftermath,
condition, or state that could already have been produced by PREVIOUS FINAL BEAT.
An aftermath can satisfy an explicitly required result, but it cannot by itself
satisfy a separately required action. Do not reject harmless visible detail.

B. CONTINUITY / POSSIBILITY: Treat PREVIOUS FINAL BEAT and CURRENT STATE as
authoritative history. Reject only clear contradictions or physical impossibilities,
such as repeating an irreversible action, using an unavailable object, crossing a
known closed or locked barrier without resolving it, escaping containment without
release, contradicting a known location, or reviving a dead, destroyed, removed,
or otherwise terminal entity. Unknown is not automatically contradictory. Apply
explicit candidate actions in order when they change what becomes possible.

C. NEXT JOB: Do not materially complete the distinct NEXT JOB early. Preparation
and incidental overlap that naturally belongs to the current action are allowed.
Reject only when the distinct work of the next beat has actually been completed,
including semantic equivalents of terminal or exhaustive results.

D. TYPED STATE EFFECTS: Every listed typed effect must be supported by what
visibly happens in the candidate. Judge meaning, not exact verbs. Possession is
not automatically equipped; breaking a barrier is not automatically entering
through it; a wound is not automatically death. Reject explicit contradiction or
partial action when the assigned effect requires a complete result. Do not require
state effects for temporary detail that is not assigned. Any new persistent change
created by the candidate must be represented by an assigned typed effect.

OUTPUT CONTRACT
If valid:
{{"valid": true, "issue": ""}}

If invalid:
{{"valid": false, "issue": "short concrete explanation"}}

Return exactly one JSON object and no markdown. The issue value must always be a
string. Do not output category names, issue codes, lists, or arrays.
""".strip()
    if settings.get("user_prompt_only"):
        user = f"{system}\n\n{user}"
        system = ""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_messages(
    case: BeatCase,
    settings: Mapping[str, object] | None = None,
) -> list[dict[str, str]]:
    return build_validation_messages(
        previous_final_beat=case.previous_final_beat,
        current_state=case.state_now,
        beat_job=case.beat_job,
        next_beat_job=case.next_beat_job,
        candidate_beat=case.candidate_beat,
        settings=settings,
    )
