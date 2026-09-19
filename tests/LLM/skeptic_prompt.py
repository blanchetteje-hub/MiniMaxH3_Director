from __future__ import annotations

import json
from collections.abc import Mapping

from cases import BeatCase
from llama_client import get_model_settings


def build_skeptic_messages(
    case: BeatCase,
    settings: Mapping[str, object] | None = None,
) -> list[dict[str, str]]:
    """Build the short second-pass prompt used only after a primary VALID."""
    if settings is None:
        settings = get_model_settings()
    system = (
        "You are a skeptical story continuity checker. The first validator "
        "considered this beat valid. Look for one concrete reason that decision "
        "may be wrong. Check the authoritative state, required beat job, story "
        "fidelity, chronology, repetition, containment, object availability, "
        "irreversible state, and unsupported additions. Do not invent problems. "
        "If there is no clear violation, return valid. Return only one JSON "
        "object with boolean valid and string issue."
    )
    state = case.state_now if isinstance(case.state_now, dict) else {}
    user = f"""
STORY
{case.premise}

PHASE GOAL
{case.phase_goal}

PREVIOUS FINAL BEAT
{case.previous_final_beat}

AUTHORITATIVE STATE BEFORE THIS BEAT
{json.dumps(state, ensure_ascii=False)}

REQUIRED BEAT JOB
{case.beat_job}

CANDIDATE BEAT
{case.candidate_beat}

Return exactly one JSON object and no markdown:
{{"valid": true, "issue": ""}}
or
{{"valid": false, "issue": "short concrete explanation"}}
If there is no clear violation, use valid true and an empty issue.
""".strip()
    if settings and settings.get("user_prompt_only"):
        user = f"{system}\n\n{user}"
        system = ""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
