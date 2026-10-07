import unittest
from unittest import mock

import minimax
from world_state import new_world_state, seed_canonical_static_location_state


class FinalH3WorldStateAuthorityTests(unittest.TestCase):
    def test_final_h3_validator_does_not_promote_raw_staging_into_state_authority(self):
        state = new_world_state({
            "source_sha256": "validator-authority",
            "subjects": {
                "1": {"subject_id": 1, "name": "Amy", "gender": "female", "picture_ids": []},
            },
        })
        state, location_id = seed_canonical_static_location_state(
            state,
            {"location": {"name": "Tavern"}, "anchors": [], "objects": []},
        )
        state["subjects"]["subject_1"].update({
            "presence": "present",
            "location_id": location_id,
            "support_id": None,
            "posture": "standing",
        })
        vocabulary = {
            "subjects": [{"id": "subject_1", "name": "Amy"}],
            "props": [],
            "locations": [{"id": location_id, "name": "Tavern"}],
        }
        request = mock.Mock(return_value={"valid": True, "issue": ""})

        result = minimax.validate_final_h3_world_state_plan(
            final_h3_prompt="Amy stands in the tavern facing east.",
            raw_scene="Amy looks toward the west wall.",
            state_actions=[],
            opening_world_state=state,
            predicted_end_world_state=state,
            vocabulary=vocabulary,
            llm_request=request,
        )

        self.assertTrue(result["valid"])
        system_prompt = request.call_args.args[0][0]["content"]
        self.assertIn("canonical Python WorldState", system_prompt)
        self.assertIn("complete authority", system_prompt)
        self.assertIn("do not derive additional persistent constraints from RAW prose", system_prompt)
        self.assertIn("Ignore facing direction", system_prompt)


if __name__ == "__main__":
    unittest.main()
