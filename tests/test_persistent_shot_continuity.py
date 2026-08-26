"""Regression tests for persistent physical state in shot-local prompts.

These tests deliberately exercise a narrow formatter boundary.  The committed
opening state is rendered into ``detailed_description`` before camera/action
prose; the existing structured-state normalizer remains responsible for the
resulting final-frame state after an explicit change.
"""

import copy
import unittest

import minimax


SUBJECT_DEFINITIONS = (
    "<Subject 1> is Jenny, a woman referenced in <Picture 1>."
)


def state_for_jenny(**overrides):
    """Build a structured committed state without relying on LLM extraction."""
    state = minimax.continuity_state_for_registry(SUBJECT_DEFINITIONS)
    jenny = state["subjects"]["Jenny"]
    jenny.update({
        "attached_objects": [],
        "injuries": [],
        "substances": [],
        "spatial_relationships": [],
        "persistent_effects": [],
    })
    for key, value in overrides.items():
        if key == "wardrobe":
            jenny["wardrobe"].update(value)
        else:
            jenny[key] = value
    return state


def inject(description, state, segment_number=2):
    """Invoke the public shot-local continuity enrichment API."""
    return minimax.inject_persistent_state_into_description(
        description,
        state,
        SUBJECT_DEFINITIONS,
        segment_number=segment_number,
    )


def assert_before(testcase, text, earlier, later):
    """Assert two case-insensitive fragments exist in the required order."""
    folded = text.casefold()
    earlier_index = folded.find(earlier.casefold())
    later_index = folded.find(later.casefold())
    testcase.assertGreaterEqual(earlier_index, 0, text)
    testcase.assertGreaterEqual(later_index, 0, text)
    testcase.assertLess(earlier_index, later_index, text)


class PersistentShotContinuityTests(unittest.TestCase):
    def test_attached_object_survives_camera_cut_and_precedes_transition(self):
        state = state_for_jenny(
            attached_objects=["metal clamp attached to Jenny's left shoulder"]
        )
        before = "[Shot 2] Camera cuts to a close-up of Jenny's arms."

        after = inject(before, state)

        self.assertEqual(before, after)
        opening = minimax.format_authoritative_opening_state(
            state, SUBJECT_DEFINITIONS
        )
        self.assertIn("metal clamp", opening.casefold())
        self.assertIn("attached", opening.casefold())

    def test_additive_apparatus_coexists_with_embedded_spikes(self):
        state = state_for_jenny(
            attached_objects=["two metal spikes embedded in Jenny's shoulders"]
        )
        before = (
            "[Shot 3] Camera cuts to a close-up of Jenny's upper body. "
            "Thick wires wrap around Jenny's arms."
        )

        after = inject(before, state)

        self.assertEqual(before, after)
        opening = minimax.format_authoritative_opening_state(
            state, SUBJECT_DEFINITIONS
        )
        self.assertIn("two metal spikes", opening.casefold())
        self.assertIn("thick wires", after.casefold())

    def test_explicit_removal_starts_with_old_state_then_removes_it(self):
        state = state_for_jenny(
            attached_objects=["metal spike embedded in Jenny's left shoulder"]
        )
        before = (
            "[Shot 4] Camera cuts to Jenny's left shoulder. "
            "A creature pulls the metal spike out."
        )

        after = inject(before, state)

        self.assertEqual(before, after)
        opening = minimax.format_authoritative_opening_state(
            state, SUBJECT_DEFINITIONS
        )
        self.assertIn("metal spike", opening.casefold())
        self.assertIn("embedded", opening.casefold())

        cut_only_state = minimax.normalize_structured_continuity_state(
            {"subjects": {"Jenny": {"attached_objects": []}}},
            SUBJECT_DEFINITIONS,
            state,
            newest_description="[Shot 4] Camera cuts to Jenny's left shoulder.",
        )
        self.assertEqual(
            ["metal spike embedded in Jenny's left shoulder"],
            cut_only_state["subjects"]["Jenny"]["attached_objects"],
        )

        resulting_state = minimax.normalize_structured_continuity_state(
            {"subjects": {"Jenny": {"attached_objects": []}}},
            SUBJECT_DEFINITIONS,
            state,
            newest_description=before,
        )
        self.assertEqual(
            [],
            resulting_state["subjects"]["Jenny"]["attached_objects"],
        )

    def test_attached_object_persists_when_outside_tight_framing(self):
        state = state_for_jenny(
            attached_objects=["black device attached to Jenny's shoulder"]
        )
        original_state = copy.deepcopy(state)
        before = "[Shot 5] Extreme close-up of Jenny's right hand."

        after = inject(before, state)

        self.assertEqual(original_state, state)
        self.assertEqual(before, after)
        opening = minimax.format_authoritative_opening_state(
            state, SUBJECT_DEFINITIONS
        )
        self.assertIn("device", opening.casefold())
        self.assertIn("attached", opening.casefold())

    def test_camera_cut_alone_preserves_blood_and_held_knife(self):
        state = state_for_jenny(
            substances=["blood covering Jenny's face"],
            held_props=["knife in Jenny's right hand"],
        )
        before = (
            "[Shot 6] Camera cuts from a wide shot to a medium close-up of Jenny."
        )

        after = inject(before, state)

        self.assertEqual(before, after)
        opening = minimax.format_authoritative_opening_state(
            state, SUBJECT_DEFINITIONS
        )
        self.assertIn("blood", opening.casefold())
        self.assertIn("knife", opening.casefold())

    def test_video_extension_first_shot_inherits_all_durable_state(self):
        state = state_for_jenny(
            attached_objects=[
                "two spider-like devices attached to Jenny's shoulders"
            ],
            injuries=["bloody wounds around the embedded shoulder spikes"],
            held_props=["knife in Jenny's right hand"],
            wardrobe={"other": "yellow dress torn at both shoulders"},
        )
        before = (
            "[Shot 7] Camera cuts to a tighter shot of Jenny. "
            "Hooked wires begin tightening around her forearms."
        )

        after = inject(before, state, segment_number=2)

        # Shot prose stays concise; the authoritative opening-state section
        # carries durable conditions separately for the director.
        self.assertNotIn("spider-like devices", before.casefold())
        self.assertNotIn("bloody wounds", before.casefold())
        self.assertNotIn("knife", before.casefold())
        self.assertNotIn("torn", before.casefold())
        self.assertEqual(before, after)
        opening = minimax.format_authoritative_opening_state(
            state, SUBJECT_DEFINITIONS
        )
        for inherited in (
            "spider-like devices",
            "bloody wounds",
            "knife",
            "torn at both shoulders",
        ):
            self.assertIn(inherited, opening.casefold())
        self.assertIn("hooked wires", after.casefold())


if __name__ == "__main__":
    unittest.main()
