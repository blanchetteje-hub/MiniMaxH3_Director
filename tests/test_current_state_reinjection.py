import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

from PIL import Image

import minimax


class CurrentStateReinjectionTests(unittest.TestCase):
    SUBJECTS = "<Subject 1> is Amy, a woman referenced in <Picture 1>."

    def _manifest(self, root, input_directory):
        current_path = os.path.join(root, "Amy_current.png")
        Image.new("RGB", (4, 4), (20, 40, 60)).save(current_path)
        state = minimax.continuity_state_for_registry(self.SUBJECTS)
        state["subjects"]["Amy"]["current_state_reference"] = current_path
        return minimax.build_segment_reference_manifest(
            self.SUBJECTS,
            state,
            "[Shot 2] <Subject 1> Amy enters.",
            2,
            previous_video_path=os.path.join(root, "segment_0001.mp4"),
            input_directory=input_directory,
        )

    def test_current_state_is_connected_in_initial_refresh_and_append(self):
        with tempfile.TemporaryDirectory() as root:
            input_directory = os.path.join(root, "input")
            os.makedirs(input_directory)
            previous_video = os.path.join(root, "segment_0001.mp4")
            with open(previous_video, "wb") as video:
                video.write(b"video")
            with open(os.path.join(input_directory, "refresh.png"), "wb") as frame:
                Image.new("RGB", (4, 4), (1, 2, 3)).save(frame, format="PNG")

            manifest = self._manifest(root, input_directory)
            self.assertEqual(
                [(item.picture_id, item.role) for item in manifest.picture_references],
                [(1, "canonical_identity"), (2, "rendered_current_state")],
            )

            with mock.patch.object(minimax, "COMFY_INPUT", input_directory):
                initial = minimax.prepare_initial_workflow(
                    6.0,
                    1.0,
                    "subject_definitions: <Picture 2> state",
                    1,
                    segment_reference_manifest=manifest,
                )
                refresh = minimax.prepare_refresh_workflow(
                    6.0,
                    1.0,
                    "subject_definitions: <Picture 2> state",
                    "refresh.png",
                    2,
                    segment_reference_manifest=manifest,
                )
                append = minimax.prepare_append_workflow(
                    6.0,
                    "subject_definitions: <Picture 2> state",
                    previous_video,
                    2,
                    segment_reference_manifest=manifest,
                )

            for workflow, destination_name, input_name in (
                (
                    initial,
                    minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
                    "ref_images.ref_image_1",
                ),
                (
                    refresh,
                    minimax.REFRESH_CONDITIONING_NODE_NAME,
                    "ref_images.ref_image_1",
                ),
            ):
                _, image_node = minimax.find_workflow_node(
                    workflow,
                    "Reference Image 2",
                    "reinjection test",
                    "LoadImage",
                )
                self.assertEqual(image_node["inputs"]["image"], "Amy_current.png")
                _, destination = minimax.find_workflow_node(
                    workflow,
                    destination_name,
                    "reinjection test",
                )
                self.assertIn(input_name, destination["inputs"])

            _, image_node = minimax.find_workflow_node(
                append,
                "Reference Image 2",
                "reinjection test",
                "LoadImage",
            )
            batch_id, batch = minimax.find_workflow_node(
                append,
                minimax.IMAGE_BATCH_NODE_NAME,
                "reinjection test",
            )
            current_node_id, _ = minimax.find_workflow_node(
                append,
                "Reference Image 2",
                "reinjection test",
                "LoadImage",
            )
            self.assertEqual(image_node["inputs"]["image"], "Amy_current.png")
            self.assertEqual(batch["inputs"]["image_1"], [current_node_id, 0])
            self.assertEqual(manifest.effective_picture_slot_map[2], 1)

    def test_prompt_describes_only_the_wired_current_state_picture(self):
        with tempfile.TemporaryDirectory() as root:
            input_directory = os.path.join(root, "input")
            os.makedirs(input_directory)
            manifest = self._manifest(root, input_directory)
            prompt = minimax.build_h3_prompt(
                {
                    "detailed_description": "[Shot 2] <Subject 1> Amy enters.",
                    "overall_soundscape": "Room tone.",
                    "non_diegetic_music": "N/A",
                },
                self.SUBJECTS,
                segment_number=2,
                conditioning_mode="latent_continuation",
                segment_reference_manifest=manifest,
            )
            self.assertIn(
                "<Picture 1> defines Amy's canonical identity and permanent design",
                prompt,
            )
            self.assertIn(
                "<Picture 2> defines Amy's most recent rendered appearance",
                prompt,
            )
            self.assertIn(
                "<Video 1> defines Amy's immediate pose, position, motion",
                prompt,
            )

    def test_story_defined_subject_can_use_current_state_without_canonical_image(self):
        definitions = "<Subject 2> is Werewolf, story-defined."
        with tempfile.TemporaryDirectory() as root:
            input_directory = os.path.join(root, "input")
            os.makedirs(input_directory)
            current_path = os.path.join(root, "Werewolf_current.png")
            Image.new("RGB", (4, 4), (90, 30, 10)).save(current_path)
            state = minimax.continuity_state_for_registry(definitions)
            state["subjects"]["Werewolf"]["current_state_reference"] = current_path
            manifest = minimax.build_segment_reference_manifest(
                definitions,
                state,
                "[Shot 2] <Subject 2> Werewolf advances.",
                2,
                input_directory=input_directory,
            )
            prompt = minimax.build_h3_prompt(
                {
                    "detailed_description": "[Shot 2] <Subject 2> Werewolf advances.",
                    "overall_soundscape": "Wind.",
                    "non_diegetic_music": "N/A",
                },
                definitions,
                segment_number=2,
                conditioning_mode="latent_continuation",
                segment_reference_manifest=manifest,
            )
            self.assertIn("story-defined", prompt)
            self.assertIn(
                "<Picture 1> defines Werewolf's most recent rendered appearance",
                prompt,
            )

    def test_mixed_registry_allocates_story_only_current_state_and_wires_workflow(self):
        definitions = (
            "<Subject 1> is Amy, a woman referenced in <Picture 1>."
        )
        with tempfile.TemporaryDirectory() as root:
            input_directory = os.path.join(root, "input")
            os.makedirs(input_directory)
            canonical_path = os.path.join(input_directory, "amy.jpg")
            Image.new("RGB", (4, 4), (10, 20, 30)).save(canonical_path)
            amy_current = os.path.join(root, "Amy_current.png")
            werewolf_current = os.path.join(root, "Werewolf_current.png")
            Image.new("RGB", (4, 4), (20, 40, 60)).save(amy_current)
            Image.new("RGB", (4, 4), (90, 30, 10)).save(werewolf_current)

            state = minimax.continuity_state_for_registry(definitions)
            state["subjects"]["Amy"]["canonical_reference"] = canonical_path
            state["subjects"]["Amy"]["current_state_reference"] = amy_current
            # Werewolf is authoritative in the persisted registry but has no
            # canonical definition/picture slot. This mirrors a subject that
            # Step 7 can resolve after it was introduced by the story.
            state["subjects"]["Werewolf"] = {
                "subject_id": 2,
                "name": "Werewolf",
                "picture_ids": [],
                "picture_id": None,
                "canonical_reference": None,
                "current_state_reference": werewolf_current,
                "dino_query": "werewolf",
            }
            description = "[Shot 4] <Subject 1> Amy and <Subject 2> Werewolf advance."

            with mock.patch.object(minimax, "COMFY_INPUT", input_directory):
                verification_output = StringIO()
                with redirect_stdout(verification_output):
                    manifest = minimax.build_segment_reference_manifest(
                        definitions,
                        state,
                        description,
                        4,
                        input_directory=input_directory,
                    )
                self.assertEqual(
                    [
                        (item.picture_id, item.image_name, item.subject_name, item.role)
                        for item in manifest.picture_references
                    ],
                    [
                        (1, "amy.jpg", "Amy", "canonical_identity"),
                        (2, "Amy_current.png", "Amy", "rendered_current_state"),
                        (3, "Werewolf_current.png", "Werewolf", "rendered_current_state"),
                    ],
                )
                prompt = minimax.build_h3_prompt(
                    {
                        "detailed_description": description,
                        "overall_soundscape": "Wind.",
                        "non_diegetic_music": "N/A",
                    },
                    definitions,
                    segment_number=4,
                    conditioning_mode="latent_continuation",
                    segment_reference_manifest=manifest,
                )
                self.assertIn(
                    "<Picture 3> defines Werewolf's most recent rendered appearance "
                    "and persistent visible configuration",
                    prompt,
                )
                self.assertIn(
                    "<Video 1> defines Werewolf's immediate pose, position, motion, "
                    "and spatial continuity where visible",
                    prompt,
                )

                previous_video = os.path.join(root, "segment_0003.mp4")
                with open(previous_video, "wb") as video:
                    video.write(b"video")
                workflow = minimax.prepare_append_workflow(
                    6.0,
                    prompt,
                    previous_video,
                    4,
                    segment_reference_manifest=manifest,
                )

            _, batch = minimax.find_workflow_node(
                workflow,
                minimax.IMAGE_BATCH_NODE_NAME,
                "mixed reinjection test",
            )
            connected = [
                batch["inputs"].get(f"image_{slot}")
                for slot in (1, 2, 3)
            ]
            self.assertTrue(all(isinstance(connection, list) for connection in connected))
            connected_names = []
            for slot in (1, 2, 3):
                node_id = batch["inputs"][f"image_{slot}"][0]
                node = workflow[str(node_id)]
                connected_names.append(node["inputs"]["image"])
            self.assertEqual(
                connected_names,
                ["amy.jpg", "Amy_current.png", "Werewolf_current.png"],
            )

            output = StringIO()
            with redirect_stdout(output):
                minimax._log_segment_reference_mapping(
                    workflow,
                    "append",
                    manifest,
                    "mixed reinjection test",
                )
            log = output.getvalue()
            self.assertIn(
                "Image Werewolf_current.png decoded and verified for segment 4.",
                verification_output.getvalue(),
            )
            self.assertIn(
                "Picture 3 -> Werewolf_current.png\n"
                "      subject=Werewolf\n"
                "      role=rendered_current_state",
                log,
            )


if __name__ == "__main__":
    unittest.main()
