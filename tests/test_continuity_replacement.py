import copy
import unittest

import minimax


SUBJECTS = "<Subject 1> is Amy, referenced in <Picture 1>."
WARDROBE_SUBJECTS = "<Subject 1> is Taylor, referenced in <Picture 1>."


def committed_state(**subject_updates):
    state = minimax.continuity_state_for_registry(SUBJECTS)
    amy = state["subjects"]["Amy"]
    for field, value in subject_updates.items():
        if field == "wardrobe":
            amy["wardrobe"].update(value)
        else:
            amy[field] = copy.deepcopy(value)
    return state


def complete_candidate(old_state=None):
    identities = minimax.continuity_state_for_registry(SUBJECTS, old_state)
    candidate = minimax.new_continuity_state()
    candidate["subjects"] = {
        name: minimax.new_subject_continuity_record(copy.deepcopy(record))
        for name, record in identities["subjects"].items()
    }
    return candidate


def wardrobe_state(**updates):
    state = minimax.continuity_state_for_registry(WARDROBE_SUBJECTS)
    state["subjects"]["Taylor"]["wardrobe"].update(updates)
    return state


def wardrobe_candidate(old_state):
    candidate = minimax.new_continuity_state()
    identity = minimax.continuity_state_for_registry(
        WARDROBE_SUBJECTS,
        old_state,
    )["subjects"]["Taylor"]
    candidate["subjects"]["Taylor"] = minimax.new_subject_continuity_record(
        copy.deepcopy(identity)
    )
    return candidate


class ContinuityReplacementTests(unittest.TestCase):
    def normalize(self, old_state, candidate, description=""):
        return minimax.normalize_structured_continuity_state(
            candidate,
            SUBJECTS,
            old_state,
            newest_description=description,
        )

    def test_na_does_not_lazily_erase_old_ongoing_action(self):
        old = committed_state()
        old["ongoing_action"] = "Amy is being dragged"

        result = self.normalize(old, complete_candidate(old))

        self.assertEqual(result["ongoing_action"], "Amy is being dragged")

    def test_current_ongoing_action_replaces_na(self):
        old = committed_state()
        candidate = minimax.new_continuity_state()
        candidate["ongoing_action"] = "Amy is being dragged"

        result = self.normalize(old, candidate)

        self.assertEqual(result["ongoing_action"], "Amy is being dragged")

    def test_candidate_injury_list_replaces_duplicate_history(self):
        old = committed_state(injuries=[
            "puncture wounds in right shoulder",
            "bleeding punctures on right shoulder",
            "deep shoulder bite punctures",
        ])
        candidate = complete_candidate(old)
        candidate["subjects"]["Amy"]["injuries"] = [
            "bleeding puncture wounds in right shoulder"
        ]

        result = self.normalize(old, candidate)

        self.assertEqual(
            result["subjects"]["Amy"]["injuries"],
            ["bleeding puncture wounds in right shoulder"],
        )

    def test_empty_held_props_without_release_evidence_preserves_pocketknife(self):
        old = committed_state(held_props=["pocketknife in right hand"])

        result = self.normalize(old, complete_candidate(old))

        self.assertEqual(
            result["subjects"]["Amy"]["held_props"],
            ["pocketknife in right hand"],
        )

    def test_spatial_relationship_list_is_replaced(self):
        old = committed_state(
            spatial_relationships=["Amy is being dragged by creatures"]
        )
        candidate = complete_candidate(old)
        candidate["subjects"]["Amy"]["spatial_relationships"] = [
            "Amy is restrained upright between two creatures"
        ]

        result = self.normalize(old, candidate)

        self.assertEqual(
            result["subjects"]["Amy"]["spatial_relationships"],
            ["Amy is restrained upright between two creatures"],
        )

    def test_empty_substances_and_effects_do_not_lazily_erase_state(self):
        old = committed_state(
            substances=["black ichor on Amy's shoulder"],
            persistent_effects=["blue sparks flickering around Amy"],
        )

        result = self.normalize(old, complete_candidate(old))

        amy = result["subjects"]["Amy"]
        self.assertEqual(amy["substances"], ["black ichor on Amy's shoulder"])
        self.assertEqual(
            amy["persistent_effects"],
            ["blue sparks flickering around Amy"],
        )

    def test_na_without_reversal_evidence_preserves_topology(self):
        old = committed_state(topology="Amy is fused to a metal chair")

        result = self.normalize(old, complete_candidate(old))

        self.assertEqual(
            result["subjects"]["Amy"]["topology"],
            "Amy is fused to a metal chair",
        )

    def test_structural_rejection_restores_only_the_rejected_field(self):
        old = committed_state(
            topology="Amy's left arm is fused to a cable",
            position="against the west wall",
            injuries=["old cheek scratch"],
        )
        candidate = complete_candidate(old)
        amy = candidate["subjects"]["Amy"]
        amy["topology"] = "Amy has a newly grown second head"
        amy["position"] = "kneeling by the doorway"
        amy["injuries"] = ["fresh cut on right palm"]

        result = self.normalize(
            old,
            candidate,
            description="Amy kneels by the doorway and raises her right palm.",
        )

        amy = result["subjects"]["Amy"]
        self.assertEqual(amy["topology"], "Amy's left arm is fused to a cable")
        self.assertEqual(amy["position"], "kneeling by the doorway")
        self.assertEqual(amy["injuries"], ["fresh cut on right palm"])

    def test_incomplete_candidate_patches_without_mutating_committed_state(self):
        old = committed_state(
            position="against the west wall",
            held_props=["pocketknife in right hand"],
        )
        original = copy.deepcopy(old)

        result = self.normalize(
            old,
            {"subjects": {"Amy": {"position": "by the doorway"}}},
        )

        self.assertIsNotNone(result)
        self.assertEqual(old, original)
        self.assertEqual(result["subjects"]["Amy"]["position"], "by the doorway")
        self.assertEqual(
            result["subjects"]["Amy"]["held_props"],
            ["pocketknife in right hand"],
        )

    def test_multi_piece_wardrobe_value_is_decomposed_into_independent_slots(self):
        old = wardrobe_state()
        candidate = wardrobe_candidate(old)
        candidate["subjects"]["Taylor"]["wardrobe"]["upper"] = (
            "navy jacket and tan trousers"
        )

        result = minimax.normalize_structured_continuity_state(
            candidate,
            WARDROBE_SUBJECTS,
            old,
            newest_description="Taylor wears a navy jacket and tan trousers.",
        )

        wardrobe = result["subjects"]["Taylor"]["wardrobe"]
        self.assertEqual(wardrobe["upper"], "navy jacket")
        self.assertEqual(wardrobe["lower"], "tan trousers")

    def test_newest_description_fills_an_omitted_wardrobe_component(self):
        old = wardrobe_state()
        candidate = wardrobe_candidate(old)
        candidate["subjects"]["Taylor"]["wardrobe"]["upper"] = "navy jacket"

        result = minimax.normalize_structured_continuity_state(
            candidate,
            WARDROBE_SUBJECTS,
            old,
            newest_description=(
                "Taylor is wearing a navy jacket and tan trousers."
            ),
        )

        wardrobe = result["subjects"]["Taylor"]["wardrobe"]
        self.assertEqual(wardrobe["upper"], "navy jacket")
        self.assertEqual(wardrobe["lower"], "tan trousers")

    def test_explicit_absence_changes_only_the_affected_wardrobe_slot(self):
        old = wardrobe_state(
            upper="green jacket",
            lower="black trousers",
            footwear="brown boots",
        )
        candidate = wardrobe_candidate(old)

        result = minimax.normalize_structured_continuity_state(
            candidate,
            WARDROBE_SUBJECTS,
            old,
            newest_description=(
                "Taylor's green jacket is destroyed, and Taylor has no upper "
                "garment in the final frame."
            ),
        )

        wardrobe = result["subjects"]["Taylor"]["wardrobe"]
        self.assertEqual(wardrobe["upper"], "absent")
        self.assertEqual(wardrobe["lower"], "black trousers")
        self.assertEqual(wardrobe["footwear"], "brown boots")

    def test_h3_serialization_omits_unknown_wardrobe_slots(self):
        state = wardrobe_state(upper="navy jacket")

        opening_state = minimax.format_authoritative_opening_state(
            state,
            WARDROBE_SUBJECTS,
        )

        self.assertIn("navy jacket", opening_state)
        self.assertNotIn("N/A", opening_state)

    def test_replacement_survives_registry_migration_and_checkpoint(self):
        old = committed_state(
            injuries=["old shoulder wound"],
            substances=["old black residue"],
            held_props=["pocketknife in right hand"],
        )
        candidate = complete_candidate(old)
        candidate["subjects"]["Amy"]["injuries"] = ["small palm cut"]

        normalized = self.normalize(old, candidate)
        registered = minimax.continuity_state_for_registry(
            SUBJECTS,
            normalized,
        )
        migrated = minimax.migrate_continuity_state(registered)
        generation_state = {}
        record = minimax.record_completed_segment(
            generation_state,
            1,
            "segment_001.mp4",
            {"detailed_description": "Amy lowers her empty hand."},
            [1],
            continuity_state=migrated,
        )

        for state in (
            registered,
            migrated,
            record["continuity_state"],
            generation_state["continuity_state"],
        ):
            amy = state["subjects"]["Amy"]
            self.assertEqual(amy["injuries"], ["small palm cut"])
            self.assertEqual(amy["substances"], ["old black residue"])
            self.assertEqual(amy["held_props"], ["pocketknife in right hand"])


class CurrentFrameContinuityTests(unittest.TestCase):
    SUBJECTS = (
        "<Subject 1> is Mark, referenced in <Picture 1>.\n"
        "<Subject 2> is Jill, referenced in <Picture 2>."
    )

    def normalize(self, old_state, candidate, description):
        return minimax.normalize_structured_continuity_state(
            candidate,
            self.SUBJECTS,
            old_state,
            newest_description=description,
        )

    def test_location_transition_rebuilds_scene_state_but_carries_body_state(self):
        old = minimax.continuity_state_for_registry(self.SUBJECTS)
        old["environment"].update({
            "location": "theme park midway",
            "persistent_state": "roller coaster overhead; game stalls flashing",
        })
        old["camera"] = "camera circles the carousel"
        old["ongoing_action"] = "Mark and Jill run past the game stalls"
        old["ongoing_audio"] = "carousel music and crowd noise"
        mark = old["subjects"]["Mark"]
        mark.update({
            "position": "beside the carousel",
            "pose_action": "running toward the roller coaster",
            "body_state": "left antenna remains bent",
            "injuries": ["small cut on right palm"],
            "substances": ["blue paint on left sleeve"],
            "spatial_relationships": ["Mark stands beside Jill near the carousel"],
            "held_props": ["silver ticket in right hand"],
        })
        mark["wardrobe"]["upper"] = "red jacket torn at left shoulder"

        # Simulate an updater that correctly changes location but also lazily
        # copies several obsolete current-frame values forward.
        candidate = copy.deepcopy(old)
        candidate["environment"]["location"] = "inside an alien spacecraft"
        candidate["environment"]["persistent_state"] = (
            "roller coaster overhead; game stalls flashing; "
            "green control panels glow along the spacecraft walls"
        )
        candidate["camera"] = "N/A"
        candidate["ongoing_action"] = "N/A"
        candidate["ongoing_audio"] = "N/A"
        candidate["subjects"]["Jill"]["position"] = "at the spacecraft console"
        candidate["subjects"]["Jill"]["pose_action"] = "bracing at the console"
        candidate["subjects"]["Jill"]["spatial_relationships"] = [
            "Jill stands in front of the spacecraft console"
        ]

        result = self.normalize(
            old,
            candidate,
            (
                "Mark and Jill enter an alien spacecraft. By the final frame, "
                "Jill braces at the spacecraft console while green control panels "
                "glow along the walls."
            ),
        )

        self.assertEqual(result["environment"]["location"], "inside an alien spacecraft")
        self.assertEqual(
            result["environment"]["persistent_state"],
            "green control panels glow along the spacecraft walls",
        )
        self.assertEqual(result["camera"], "N/A")
        self.assertEqual(result["ongoing_action"], "N/A")
        self.assertEqual(result["ongoing_audio"], "N/A")
        self.assertEqual(result["subjects"]["Mark"]["position"], "N/A")
        self.assertEqual(result["subjects"]["Mark"]["pose_action"], "N/A")
        self.assertEqual(result["subjects"]["Mark"]["spatial_relationships"], [])
        self.assertEqual(
            result["subjects"]["Jill"]["spatial_relationships"],
            ["Jill stands in front of the spacecraft console"],
        )
        self.assertEqual(mark["body_state"], result["subjects"]["Mark"]["body_state"])
        self.assertEqual(mark["wardrobe"], result["subjects"]["Mark"]["wardrobe"])
        self.assertEqual(mark["injuries"], result["subjects"]["Mark"]["injuries"])
        self.assertEqual(mark["substances"], result["subjects"]["Mark"]["substances"])
        self.assertEqual(mark["held_props"], result["subjects"]["Mark"]["held_props"])

    def test_lazy_unknowns_do_not_erase_durable_state(self):
        old = minimax.continuity_state_for_registry(self.SUBJECTS)
        mark = old["subjects"]["Mark"]
        mark["body_state"] = "left antenna remains bent"
        mark["injuries"] = ["small cut on right palm"]
        mark["substances"] = ["blue paint on left sleeve"]
        mark["held_props"] = ["silver ticket in right hand"]
        mark["wardrobe"]["upper"] = "red jacket torn at left shoulder"

        candidate = complete_candidate(old)
        candidate["subjects"] = {
            name: minimax.new_subject_continuity_record(copy.deepcopy(record))
            for name, record in minimax.continuity_state_for_registry(
                self.SUBJECTS,
                old,
            )["subjects"].items()
        }

        result = self.normalize(
            old,
            candidate,
            "A close-up shows Mark looking toward Jill.",
        )

        current = result["subjects"]["Mark"]
        self.assertEqual(current["body_state"], mark["body_state"])
        self.assertEqual(current["wardrobe"], mark["wardrobe"])
        self.assertEqual(current["injuries"], mark["injuries"])
        self.assertEqual(current["substances"], mark["substances"])
        self.assertEqual(current["held_props"], mark["held_props"])

    def test_explicitly_completed_transient_state_is_removed(self):
        old = minimax.continuity_state_for_registry(self.SUBJECTS)
        old["environment"]["location"] = "theme park midway"
        old["environment"]["persistent_state"] = "fountain spraying over the path"
        old["ongoing_action"] = "Mark waves toward Jill"
        old["ongoing_audio"] = "carousel music"
        mark = old["subjects"]["Mark"]
        mark["pose_action"] = "running beside Jill"
        mark["physical_condition"] = "startled"
        mark["spatial_relationships"] = ["Mark stands beside Jill"]
        mark["injuries"] = ["small cut on right palm"]

        candidate = minimax.new_continuity_state()
        candidate["environment"]["location"] = "theme park midway"
        candidate["subjects"] = {
            name: minimax.new_subject_continuity_record(copy.deepcopy(record))
            for name, record in minimax.continuity_state_for_registry(
                self.SUBJECTS,
                old,
            )["subjects"].items()
        }

        result = self.normalize(
            old,
            candidate,
            (
                "The fountain stops spraying and Jill leaves. By the final frame, "
                "Mark calms and stands still as the midway falls silent."
            ),
        )

        current = result["subjects"]["Mark"]
        self.assertEqual(result["environment"]["persistent_state"], "N/A")
        self.assertEqual(result["ongoing_action"], "N/A")
        self.assertEqual(result["ongoing_audio"], "N/A")
        self.assertEqual(current["pose_action"], "N/A")
        self.assertEqual(current["physical_condition"], "N/A")
        self.assertEqual(current["spatial_relationships"], [])
        self.assertEqual(current["injuries"], ["small cut on right palm"])


if __name__ == "__main__":
    unittest.main()
