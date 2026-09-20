import unittest
from unittest.mock import Mock, patch

import minimax


SUBJECTS = (
    "<Subject 1> is Amy, referenced in <Picture 1>.\n"
    "<Subject 2> is Will, referenced in <Picture 2>."
)


class H3ContinuityBoundaryTests(unittest.TestCase):
    def state(self):
        state = minimax.continuity_state_for_registry(SUBJECTS)
        state["environment"].update(
            location="hallway",
            persistent_state="the basement door is locked",
        )
        state["subjects"]["Amy"].update(
            position="in the hallway",
            pose_action="aiming a pistol",
            physical_condition="bleeding from the arm",
            held_props=["pistol"],
            injuries=["bullet wound"],
        )
        state["subjects"]["Amy"]["wardrobe"]["upper"] = "red jacket"
        state["subjects"]["Will"].update(
            position="in the basement",
            held_props=["flashlight"],
        )
        state["ongoing_audio"] = "eggs sizzling in the kitchen"
        return state

    def test_canonical_state_is_preserved_but_opening_is_scene_scoped(self):
        state = self.state()
        opening = minimax.format_authoritative_opening_state(
            state,
            SUBJECTS,
            current_scene=(
                "Amy aims her pistol at a threat approaching through the hallway."
            ),
            conditioning_mode="clean_refresh",
        )

        self.assertEqual(state["subjects"]["Will"]["position"], "in the basement")
        self.assertIn("Amy", opening)
        self.assertIn("pistol", opening)
        self.assertIn("red jacket", opening)
        self.assertIn("bleeding from the arm", opening)
        self.assertNotIn("Will", opening)
        self.assertNotIn("flashlight", opening)
        self.assertNotIn("eggs sizzling", opening)
        self.assertNotIn("basement door", opening)

    def test_one_shot_and_remote_audio_are_not_carried_forward(self):
        state = self.state()
        state["ongoing_audio"] = "a gunshot echoed in the kitchen"
        opening = minimax.format_authoritative_opening_state(
            state,
            SUBJECTS,
            current_scene="Amy waits in the hallway.",
            conditioning_mode="clean_refresh",
        )
        self.assertNotIn("gunshot", opening)

    def test_request_two_receives_filtered_opening_state(self):
        state = self.state()
        request = Mock(side_effect=[
            {"raw_scene": "Amy aims her pistol through the hallway."},
            {
                "detailed_description": "[Shot 2] Amy aims her pistol.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
            },
        ])
        bundle = {
            "segment": 2,
            "active_beat_id": 2,
            "current_duration": 4.5,
            "conditioning_mode": "clean_refresh",
            "registry_state": state,
            "subject_definitions": SUBJECTS,
            "messages": [{"role": "user", "content": "Director input."}],
        }

        with patch("minimax.ask_llm", request):
            minimax.request_segment_llm(
                bundle,
                [],
                "run-1",
                {"source_sha256": "source-1"},
            )

        formatter_user_message = request.call_args_list[1].args[0][1]["content"]
        self.assertIn("Amy", formatter_user_message)
        self.assertIn("pistol", formatter_user_message)
        self.assertNotIn("Will", formatter_user_message)
        self.assertNotIn("eggs sizzling", formatter_user_message)

    def test_final_h3_prompt_does_not_append_previous_continuity_again(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": "[Shot 2] <Subject 1> Amy aims her pistol.",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            previous_state=(
                "Amy is in the hallway wearing a red jacket. "
                "Will is in the basement with a flashlight."
            ),
            segment_number=2,
            conditioning_mode="clean_refresh",
            continuity_state=self.state(),
        )

        self.assertNotIn("Will is in the basement", prompt)
        self.assertNotIn("retention_analysis", prompt)
        self.assertEqual(prompt.count("Amy aims her pistol"), 1)

    def test_append_prompt_does_not_reconstruct_previous_frame(self):
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 2] <Subject 1> Amy raises the pistol and fires."
                ),
                "overall_soundscape": "A sharp report.",
                "non_diegetic_music": "N/A",
            },
            SUBJECTS,
            previous_state="Amy is in the hallway wearing a red jacket.",
            segment_number=2,
            conditioning_mode="continuation",
            continuity_state=self.state(),
        )

        self.assertIn("<Video 1>", prompt)
        self.assertIn("Amy raises the pistol and fires", prompt)
        self.assertNotIn("wearing a red jacket", prompt)
        self.assertNotIn("retention_analysis", prompt)


if __name__ == "__main__":
    unittest.main()
