from __future__ import annotations

import json
from collections.abc import Mapping

from tests.LLM.cases import BeatCase
from tests.LLM.llama_client import get_model_settings


def build_messages(
    case: BeatCase,
    settings: Mapping[str, object] | None = None,
) -> list[dict[str, str]]:
    """Build the production validity-first validator prompt."""
    if settings is None:
        settings = get_model_settings()

    state = case.state_now if isinstance(case.state_now, dict) else {}

    system = (
        "You validate concise story beats. Judge the candidate against the "
        "authoritative current state and the current beat job. The current state "
        "is true at the start of the beat. Apply explicit candidate actions from "
        "left to right. Do not invent hidden actions or facts. Do not require "
        "details the beat job does not require. Only the current beat job defines "
        "work required now, but every explicit candidate action must still be "
        "consistent with authoritative state and history. Treat terminal or "
        "exhaustive wording such as 'last', 'final', 'final remaining', "
        "'only remaining', 'all remaining', or 'completely eliminates' in "
        "NEXT BEAT MUST DO as protected future work; do not "
        "allow the candidate to perform that work early. When CURRENT BEAT JOB "
        "requires an action, the candidate must perform that action now; merely "
        "describing its resulting state is not enough. Return only one JSON "
        "object with boolean valid and string issue."
    )

    user = f"""
STORY
{case.premise}

PHASE GOAL
{case.phase_goal}

PREVIOUS FINAL BEAT
{case.previous_final_beat}

CURRENT STATE — authoritative snapshot before this beat
{json.dumps(state, ensure_ascii=False)}

CURRENT BEAT JOB
{case.beat_job}

NEXT BEAT MUST DO (context only; not required for this beat)
{case.next_beat_job or "None; this is the final beat."}

DO NOT COMPLETE YET
{case.next_beat_job or "There is no later beat job."}

CANDIDATE BEAT
{case.candidate_beat}

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

   If CURRENT BEAT JOB requires an action, require that action itself now.
   A result-only statement does not satisfy an action job: "the last standing
   zombie lies dead" does not satisfy "shoots the last standing zombie".

   Also compare every explicit candidate action with NEXT BEAT MUST DO before
   accepting the candidate. If the candidate performs the distinct next job,
   it is invalid even when it also completes CURRENT BEAT JOB. In particular,
   when NEXT BEAT MUST DO is "shoots the last standing zombie", a candidate
   that says "shoots the last standing zombie, killing it" is invalid here.

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
   - something permanently dead, destroyed, defeated, escaped, or finished
     becomes active again;
   - a new threat appears after CURRENT STATE explicitly says the immediate
     threat area is clear;
   - an important person, threat, object, or event is introduced without support
     from STORY, PHASE GOAL, CURRENT BEAT JOB, or CURRENT STATE;
   - the candidate completes the distinct NEXT BEAT MUST DO action early,
     especially a terminal or exhaustive action such as killing the last
     standing threat.

DECISION RULES

- Completing CURRENT BEAT JOB does not excuse another violation.
- Check every explicit candidate action, not only the required action.
- Terminal or exhaustive NEXT BEAT MUST DO wording is protected: "last",
  "final", "final remaining", "only remaining", "all remaining", and
  "completely eliminates" mean that work must wait for the next beat. For
  example, if the next job is to kill the last standing zombie, a candidate
  that shoots and kills it now is invalid.
- Before returning valid, compare each explicit candidate action with NEXT BEAT
  MUST DO. Performing that distinct next action early is always invalid, even
  if the candidate also completes the current job.
- An action-type CURRENT BEAT JOB requires the action, not only the outcome. A
  candidate saying "the last zombie lies dead" is invalid for a job requiring
  the kill; "shoots the last zombie, killing it" is valid when that is the
  current job.
- Explicit movement establishes a location change.
- Explicit opening or unlocking can resolve a barrier.
- Explicit release can resolve containment.
- A known entity returning from a permanent state is invalid.
- A new threat violates a cleared-area condition only when CURRENT STATE
  explicitly says that area is already clear.
- Preparation for the current job is allowed.
- Completing the distinct next beat job early is not allowed.
- Ordinary descriptive detail is allowed unless it contradicts established
  state, invents prior history, repeats completed history, or introduces an
  unsupported important fact.
- Report only clear violations. Do not invent possible problems.

OUTPUT CONTRACT

If valid:
{{"valid": true, "issue": ""}}

If invalid:
{{"valid": false, "issue": "short concrete explanation"}}

Return exactly one JSON object and no markdown.
The issue value must always be a string.
Do not output category names, issue codes, lists, or arrays.
""".strip()

    if settings and settings.get("user_prompt_only"):
        user = f"{system}\n\n{user}"
        system = ""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
