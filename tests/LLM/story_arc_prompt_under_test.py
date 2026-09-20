from __future__ import annotations

import json
from collections.abc import Mapping

from tests.LLM.llama_client import get_model_settings
from tests.LLM.story_arc_cases import StoryArcCase


def build_messages(
    case: StoryArcCase,
    settings: Mapping[str, object] | None = None,
) -> list[dict[str, str]]:
    """Build the story-arc validator prompt under test.

    Codex should tune this function only. Keep the cases/scorer frozen.
    """
    if settings is None:
        settings = get_model_settings()

    system = (
        "You validate one complete story arc. Use simple semantic checks. "
        "Return one small JSON object only."
    )

    user = f"""
Check the proposed arc against the source story and instructions.

Reject the arc only when there is a real blocking error.

Reject when:
- The premise, main conflict, or required ending changes.
- A required major source event is missing or out of order.
- The arc adds an unsupported major character, change, procedure, myth, time
  event, plot device, required event, or required end-state fact.
- The arc contradicts an explicit source fact.
- Clearly separate source stages are collapsed into one phase and a meaningful
  stage boundary is lost.
- A defined human Subject has no concrete clothing when first shown. Clothing
  may be added when that Subject is introduced later.
- Dependencies are missing, incoherent, or in the wrong order.
- A phase end state contains a fact that is not true by that phase boundary.
- A persistent state effect is missing, owned by the wrong entity, unrelated,
  malformed, or has the wrong value.

Required events:
- Must be directly supported by the source or explicit instructions.
- Must keep the source order.
- Check the actual event meaning and location against the source order. Do not
  trust event IDs, list order, or a phase summary. If a later source event is
  assigned an earlier beat than a preceding source event, reject the arc.
- Must be concrete enough to show in a beat.
- May use a clear paraphrase, a named item being equipped, a source-stated
  condition, or the minimum physical action needed by a source event.
- Must not promote optional connective action into a required event.
- Do not require optional timing, route, gesture, choreography, or item use.

Required end states:
- Treat each end state as a snapshot at its phase boundary, not as a checklist
  that must repeat every contributing event.
- Check all required events in the current phase and earlier phases together.
- Several events may establish one summary fact. A source-authorized access or
  transition state may be inferred when all of its source-defined prerequisites
  are complete, even if no event repeats the summary words.
- A statement that all items are complete requires all items, not just some.

State effects:
- state_effects is optional and must be a list of typed operations representing
  persistent facts directly established by that required event.
- Use only these operation names: set_location, set_item_state,
  set_barrier_state, set_threat_state, set_object_state, set_containment,
  set_condition, and set_clothing. Do not invent operation names, nested state
  fields, or arbitrary canonical paths.
- Examples: {"op":"set_location","entity":"Will","value":"basement"};
  {"op":"set_item_state","entity":"pistol","owner":"Amy","value":"equipped"}.
- CHECK PERSISTENT STATE COVERAGE: if a required event explicitly establishes a
  persistent canonical fact represented by one of these typed operations, that
  same event must include the matching state_effect. Reject the arc when the
  event says the persistent change or result occurs but its typed effect is
  missing. Apply this generically to persistent modeled facts such as location,
  containment, release, held/equipped objects, barriers, persistent objects,
  terminal entities, clothing, and persistent environment conditions.
- Do not require state effects for temporary actions, feelings, reactions, or
  detail.
- Attach each typed operation to the required event that actually establishes
  that fact. If a later event retrieves or equips named equipment, an earlier
  ordinary setup event must not carry that held/equipped operation; reject the
  arc even if the later event also carries the operation.
- Do not copy an old effect onto an unrelated event just to satisfy coverage.

Do not reject because:
- Phase sizes are unequal.
- One process uses most of the beats.
- Required-event beat numbers have gaps. They must be ordered, not consecutive.
- A one-phase arc is used for one continuous source purpose.
- Wording differs slightly but the meaning is source-authorized.

Python already checks JSON shape, numeric ranges, duplicate IDs, and dependency
field shape. Judge the semantic meaning, not exact wording.

SOURCE STORY
--- STORY START ---
{case.story}
--- STORY END ---

DEFINED SUBJECTS
{case.subject_information or "N/A"}

EXPLICIT BEAT INSTRUCTIONS
{case.beat_instructions or "N/A"}

PROPOSED MACRO STORY ARC
{json.dumps(case.proposed_arc, ensure_ascii=False, indent=2)}

Output exactly one JSON object and nothing else. Do not output analysis,
reasoning, a checklist, markdown, or any text before or after the object.
Use this exact shape: {{"valid": true, "issues": []}} for a valid arc, or
{{"valid": false, "issues": ["one concise blocking issue"]}} for an invalid
arc. Keep the issues array empty when valid is true, and stop immediately after
the closing brace.
""".strip()

    if settings and settings.get("user_prompt_only"):
        user = f"{system}\n\n{user}"
        system = ""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
