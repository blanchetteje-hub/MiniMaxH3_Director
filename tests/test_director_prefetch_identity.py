import unittest
from unittest import mock

import minimax


class DirectorPrefetchIdentityTests(unittest.TestCase):
    def setUp(self):
        self.beats = [
            minimax.BeatDefinition("Amy hears a low growl."),
            minimax.BeatDefinition("A partial shadow reveals the werewolf."),
            minimax.BeatDefinition("The werewolf lunges fully into view."),
        ]

    def test_prefetch_target_is_the_upcoming_beat_not_a_completed_count_lookahead(self):
        completed = {1}

        target = minimax.resolve_execution_target(self.beats, 2)

        self.assertEqual(target["segment_number"], 2)
        self.assertEqual(target["beat_id"], 2)
        self.assertIs(target["beat"], self.beats[1])
        completed.add(target["beat_id"])
        next_target = minimax.resolve_execution_target(self.beats, 3)
        self.assertEqual(next_target["beat_id"], 3)
        self.assertIs(next_target["beat"], self.beats[2])
        # The completed set is intentionally not used to resolve either target.
        self.assertEqual(minimax.get_next_beat_id(self.beats, completed), 3)

    def test_mismatched_prefetch_is_rejected_before_render_acceptance(self):
        requested = {"segment_number": 2, "beat_id": 2}
        wrong_response = {
            "segment_number": 2,
            "beat_id": 3,
            "fingerprint": "same-state",
        }
        comfyui_queue = mock.Mock()

        accepted = minimax.prefetched_response_is_usable(
            requested,
            wrong_response,
            current_segment_number=2,
            authoritative_beat_id=2,
            expected_fingerprint="same-state",
        )
        if accepted:
            comfyui_queue()

        self.assertFalse(accepted)
        comfyui_queue.assert_not_called()

    def test_matching_prefetch_can_pass_the_identity_gate(self):
        requested = {"segment_number": 2, "beat_id": 2}
        response = {
            "segment": 2,
            "active_beat_id": 2,
            "fingerprint": "same-state",
        }

        self.assertTrue(
            minimax.prefetched_response_is_usable(
                requested,
                response,
                current_segment_number=2,
                authoritative_beat_id=2,
                expected_fingerprint="same-state",
            )
        )

    def test_completed_segment_checkpoint_keeps_global_beat_identity(self):
        state = {"segments": []}
        minimax.record_completed_segment(
            state,
            segment_number=1,
            video_path="segment-1.mp4",
            llm_result={"detailed_description": "scene"},
            completed_beat_ids={1},
            beat_id=1,
        )
        record = minimax.record_completed_segment(
            state,
            segment_number=2,
            video_path="segment-2.mp4",
            llm_result={"detailed_description": "scene"},
            completed_beat_ids={1, 2},
            beat_id=2,
        )

        self.assertEqual(record["segment_number"], 2)
        self.assertEqual(record["beat_id"], 2)
        self.assertEqual(state["segments"][1]["beat_id"], 2)

    def test_director_messages_carry_the_same_resolved_beat_definition(self):
        target = minimax.resolve_execution_target(self.beats, 2)
        messages, _, _ = minimax.build_generation_messages(
            director_rules="director rules",
            story="Amy is in the forest.",
            beats=self.beats,
            completed_beat_ids={1},
            recent_results=[],
            current_segment=2,
            total_segments=3,
            segment_length=5,
            total_length=15,
            active_beat=target["beat"],
            active_beat_id=target["beat_id"],
        )

        self.assertIn(
            "AUTHORITATIVE ACTIVE BEAT (execute this exact beat only):\n"
            "Beat 2: A partial shadow reveals the werewolf.",
            messages[-1]["content"],
        )
        self.assertNotIn("Beat 3: The werewolf lunges fully into view.", messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
