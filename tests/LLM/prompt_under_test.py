from __future__ import annotations

import json
from cases import BeatCase


def build_messages(case: BeatCase) -> list[dict[str, str]]:
    """Build the production validity-first validator prompt."""
    state = case.state_now if isinstance(case.state_now, dict) else {}
    system = (
        "You validate concise story beats. Judge the meaning of the candidate "
        "against the current state and the current beat job. A requirement is "
        "satisfied when its action or fact is stated or unambiguously entailed. "
        "A stated outcome does not require a second demonstration, a named "
        "mechanism, or extra detail unless the job explicitly requires it. "
        "The current state is authoritative at the start of the beat. Simulate "
        "explicit actions from left to right. Require direct evidence; never "
        "invent facts or hidden actions. Only the current beat job defines work "
        "required now; the premise and phase goal are context, not additional "
        "requirements for this beat. Return only one "
        "JSON object with boolean valid and string issue. If invalid, issue must "
        "briefly state the concrete problem. Do not use labels, codes, or lists."
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
1. Split CURRENT BEAT JOB into atomic requirements and compare their meaning
   with the candidate. Each requirement may be conveyed by a statement, an
   action, or an unambiguous implication. A setup requirement is satisfied by
   establishing the requested facts; identifying their cause or resolving them
   is separate work unless expressly required. Count all participants in an
   action, including its objects, and allow one sentence to satisfy multiple
   requirements. Do not require a separate sentence repeating each fact.
2. Read CURRENT STATE literally, including object, barrier, containment,
   location, threat, and irreversible-status facts. Treat missing facts as
   unknown, not as permission to invent them.
3. Apply explicit candidate actions in order. Opening or unlocking can permit a
   later crossing; releasing can permit a later departure; entering or crossing
   can establish a later location. Do not compare a later action with the
   untouched start state after the candidate explicitly changed that state.
4. Check all of the following for direct contradictions or omissions:
   - required beat-job fidelity, without demanding broader phase work;
   - object availability, closed barriers, containment, and unexplained location
     changes;
   - something permanently dead, destroyed, defeated, escaped, or finished
     becoming active again;
   - a new threat after the current state explicitly says the immediate-threat
     area is clear;
   - an earlier event, injury, or permission not established by the supplied
     current state or previous context;
   - repeating an action the current state says is already complete;
   - an important person, threat, object, or event unsupported by the story,
     state, job, or phase goal;
   - a distinct later state-changing action completed before its turn.

DECISION RULES
- Check job completion and contradictions independently. Completing the job
  does not excuse another clear violation. Describe that violation accurately
  instead of claiming the completed job was omitted.
- Explicit movement establishes a location change. Explicit opening/unlocking
  resolves a barrier for later actions. Explicit release resolves containment
  for later actions. Do not report a contradiction after its enabling action is
  explicit in the same candidate.
- A contained entity appearing outside without release is a containment problem;
  do not add a second location explanation for the same fact. A separately
  crossed closed or locked barrier remains an additional concrete problem.
- A known entity returning from a permanent or finished state is a continuity
  problem, not an unsupported-new-entity problem. A past event explicitly stated
  in the supplied context is supported; do not call it invented.
- A threat violates a cleared-area condition only if the current state already
  explicitly marks that area clear. A false or missing clearance value is not
  a reason to reject danger. Permanent destruction remains binding regardless
  of the area's clearance value.
- Preparation for the current job is allowed. A separate later state change is
  not allowed merely because the phase goal mentions it.
- Ordinary descriptive detail is allowed unless it contradicts established state
  or introduces an unsupported important fact.

OUTPUT CONTRACT
Return exactly one JSON object and no markdown:
{{"valid": true, "issue": ""}}
or
{{"valid": false, "issue": "short concrete explanation"}}
The issue value is always a string. If several clear problems exist, mention them
briefly in the same issue string. Do not output category names, issue codes, or
an array.
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
