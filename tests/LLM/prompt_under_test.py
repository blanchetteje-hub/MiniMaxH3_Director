from __future__ import annotations

import json
from collections.abc import Mapping

from tests.LLM.cases import BeatCase
from tests.LLM.llama_client import get_model_settings


def build_validation_messages(
    story,
    phase_goal,
    previous_final_beat,
    current_state,
    beat_job,
    next_beat_job,
    candidate_beat,
    settings=None,
    assigned_state_effects=None,
) -> list[dict[str, str]]:
    """Standalone copy of the production beat-validator prompt builder."""
    settings = settings or get_model_settings()
    state = current_state if isinstance(current_state, dict) else {}
    state_effects_section = ""
    state_effects_rules = ""
    if assigned_state_effects is not None:
        state_effects_section = f"""

STATE EFFECTS TO COMMIT IF VALID
{json.dumps(assigned_state_effects, ensure_ascii=False, separators=(",", ":"))}
"""
        state_effects_rules = """

   7. CHECK STATE EFFECTS TO COMMIT.
   If the candidate explicitly states the opposite of a listed state effect, or
   explicitly says that effect does not occur, return INVALID.

   VALID is allowed only when the candidate agrees with the listed effects
   Python will commit if this beat passes.

   Every listed state effect must actually be established by the candidate. If
   a state effect says an entity is dead, destroyed, opened, released, moved,
   equipped, or has another complete result, the candidate must clearly perform
   enough action to establish that result. Do not accept partial progress when
   the committed state effect is terminal or complete.

   If the candidate creates a new persistent change, including structural
   damage, that change must be represented by the assigned state effects.
   Temporary motion, combat actions, reactions, poses, and other non-persistent
   details do not need state effects.
"""
    system = (
        "You validate concise story beats. Judge the candidate against the "
        "authoritative current state and the current beat job. The current state "
        "is true at the start of the beat. Apply explicit candidate actions from "
        "left to right. Do not invent hidden actions or facts. Do not require "
        "details the beat job does not require. Only the current beat job defines "
        "work required now, but every explicit candidate action must still be "
        "consistent with authoritative state and history. Return only one JSON "
        "object with boolean valid and string issue."
    )
    user = f"""
STORY
{story}

PHASE GOAL
{phase_goal}

PREVIOUS FINAL BEAT
{previous_final_beat or "None; this is the first beat."}

CURRENT STATE — authoritative snapshot before this beat
{json.dumps(state, ensure_ascii=False)}

CURRENT BEAT JOB
{beat_job}

NEXT BEAT MUST DO (context only; not required for this beat)
{next_beat_job or "None; this is the final beat."}

DO NOT COMPLETE YET
{next_beat_job or "There is no later beat job."}
{state_effects_section}

CANDIDATE BEAT
{candidate_beat}

VALIDATION METHOD

1. CHECK PRIOR HISTORY.
   Treat CURRENT STATE and PREVIOUS FINAL BEAT as complete evidence of what
   happened before this beat.

   If the candidate says or implies that an injury, damage, event, possession,
   knowledge, permission, or other condition happened earlier, that history must
   be supported by CURRENT STATE or PREVIOUS FINAL BEAT.

   If claimed prior history is absent, it did not happen and the candidate is
   invalid.

2. CHECK FOR REPEATED COMPLETED ACTIONS.
   CURRENT STATE contains the effects of completed earlier actions.

   If an object is already held by a character, retrieving that same object again
   is a repeated completed action unless CURRENT STATE explicitly says it was
   subsequently put away, dropped, lost, or transferred.

   If an object is already ready, making it ready again is repeated unless
   CURRENT STATE explicitly says it became unready.

   Check every explicit candidate action, including extra actions before or after
   the CURRENT BEAT JOB. Any repeated completed action makes the candidate
   invalid.

3. CHECK CURRENT BEAT JOB.
   Split CURRENT BEAT JOB into its required actions or facts and compare their
   meaning with the candidate.

   Paraphrases and unambiguous implications count.

   Do not require a separate sentence for each requirement.

   If the current job is an action, the candidate must explicitly perform or
   unambiguously show that action occurring during THIS beat. A result or
   state left behind by an earlier action is not enough. For example, when the
   job is "Unlock the final gate", "The final gate stands unlocked" is invalid;
   "The operator turns the key and unlocks the final gate" performs the action.
   A state-only candidate may satisfy a job that explicitly asks for a state,
   but it must not substitute for an action-type job.

   If CURRENT BEAT JOB contains multiple required actions, people, objects, or
   results, the candidate must satisfy ALL of them. Completing only one item from
   an explicit list or one side of a compound requirement is invalid.

4. CHECK CURRENT STATE.
   Read object, barrier, containment, location, threat, and irreversible-status
   facts literally.

   For present-state facts, missing information is unknown.

   This does NOT apply to claims about events before this beat: prior history is
   complete as described in Rule 1.

5. APPLY CANDIDATE ACTIONS IN ORDER.
   Explicit actions may legitimately change state during the beat.

   Opening or unlocking a barrier can permit later crossing.
   Releasing someone can permit later departure.
   Entering, leaving, crossing, returning, or traveling can establish a new
   location.

   Do not compare a later candidate action against the untouched start state when
   an earlier explicit action already changed that state.

6. CHECK FOR OTHER CLEAR VIOLATIONS:
   - the required current beat job is not completed;
   - an unavailable object is used or possessed;
   - a closed or locked barrier is crossed without being opened;
   - a contained entity appears outside containment without release;
   - location changes without explicit movement or transition;
   - something in an explicitly terminal, inactive, removed, exited, or
     finished state becomes active again;
   - a new threat appears after CURRENT STATE explicitly says the immediate
     threat area is clear;
   - an important person, threat, object, or event is introduced without support
     from STORY, PHASE GOAL, CURRENT BEAT JOB, or CURRENT STATE;
   - the candidate completes the distinct NEXT BEAT MUST DO action early.

   Treat terminal or exhaustive wording in NEXT BEAT MUST DO semantically, not
   by exact word matching. If the next job says last, final, all remaining,
   final remaining, only remaining, completely resolves, or an equivalent
   terminal condition, the current candidate must not explicitly establish that
   condition early. For example, if the next job is "Complete the final
   checkpoint", a candidate that marks the only remaining checkpoint complete is
   early completion even when the wording differs.

DECISION RULES

- Completing CURRENT BEAT JOB does not excuse another violation.
- Check every explicit candidate action, not only the required action.
- Explicit movement establishes a location change.
- Explicit opening or unlocking can resolve a barrier.
- Explicit release can resolve containment.
- A known entity returning from a permanent state is invalid.
- A new threat violates a cleared-area condition only when CURRENT STATE
  explicitly says that area is already clear.
- Preparation for the current job is allowed.
- Completing the distinct next beat job early is not allowed.
- Terminal or exhaustive next-beat completion includes semantic equivalents,
  not only exact repeated wording.
- A result-only description does not perform a required current action.
- Ordinary descriptive detail is allowed unless it contradicts established
  state, invents prior history, repeats completed history, or introduces an
  unsupported important fact.
- Report only clear violations. Do not invent possible problems.
{state_effects_rules}

OUTPUT CONTRACT

If valid:
{{"valid": true, "issue": ""}}

If invalid:
{{"valid": false, "issue": "short concrete explanation"}}

Return exactly one JSON object and no markdown.
The issue value must always be a string.
Do not output category names, issue codes, lists, or arrays.
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
        story=case.premise,
        phase_goal=case.phase_goal,
        previous_final_beat=case.previous_final_beat,
        current_state=case.state_now,
        beat_job=case.beat_job,
        next_beat_job=case.next_beat_job,
        candidate_beat=case.candidate_beat,
        settings=settings,
    )
