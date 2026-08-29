import copy
import unittest

import minimax


SUBJECTS = "<Subject 1> is Amy, referenced in <Picture 1>."


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


class ContinuityReplacementTests(unittest.TestCase):
    def normalize(self, old_state, candidate, description=""):
        return minimax.normalize_structured_continuity_state(
            candidate,
            SUBJECTS,
            old_state,
            newest_description=description,
        )

    def test_na_replaces_old_ongoing_action(self):
        old = committed_state()
        old["ongoing_action"] = "Amy is being dragged"

        result = self.normalize(old, complete_candidate(old))

        self.assertEqual(result["ongoing_action"], "N/A")

    def test_current_ongoing_action_replaces_na(self):
        old = committed_state()
        candidate = complete_candidate(old)
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

    def test_empty_held_props_removes_old_pocketknife(self):
        old = committed_state(held_props=["pocketknife in right hand"])

        result = self.normalize(old, complete_candidate(old))

        self.assertEqual(result["subjects"]["Amy"]["held_props"], [])

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

    def test_absent_substances_and_effects_disappear(self):
        old = committed_state(
            substances=["black ichor on Amy's shoulder"],
            persistent_effects=["blue sparks flickering around Amy"],
        )

        result = self.normalize(old, complete_candidate(old))

        amy = result["subjects"]["Amy"]
        self.assertEqual(amy["substances"], [])
        self.assertEqual(amy["persistent_effects"], [])

    def test_na_clears_old_erroneous_topology(self):
        old = committed_state(topology="Amy is fused to a metal chair")

        result = self.normalize(old, complete_candidate(old))

        self.assertEqual(result["subjects"]["Amy"]["topology"], "N/A")

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

    def test_incomplete_candidate_fails_without_mutating_committed_state(self):
        old = committed_state(
            position="against the west wall",
            held_props=["pocketknife in right hand"],
        )
        original = copy.deepcopy(old)

        result = self.normalize(
            old,
            {"subjects": {"Amy": {"position": "by the doorway"}}},
        )

        self.assertIsNone(result)
        self.assertEqual(old, original)
        fallback = old if result is None else result
        self.assertEqual(fallback, original)

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
            self.assertEqual(amy["substances"], [])
            self.assertEqual(amy["held_props"], [])


if __name__ == "__main__":
    unittest.main()
