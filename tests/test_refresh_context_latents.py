import base64
import os
import tempfile
import unittest
from unittest import mock

import minimax
from tests.test_reference_pruning import enable_all_references


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)


class RefreshContextLatentTests(unittest.TestCase):
    def test_refresh_uses_final_22_frames_as_context_latents(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_video = os.path.join(directory, "previous.mp4")
            with open(previous_video, "wb") as handle:
                handle.write(b"video")
            with open(os.path.join(directory, "0.png"), "wb") as handle:
                handle.write(VALID_PNG)

            with mock.patch("minimax.COMFY_INPUT", directory), mock.patch(
                "minimax.get_video_frame_count", return_value=192,
            ):
                workflow = minimax.prepare_refresh_workflow(
                    8.0,
                    0.3,
                    "prompt",
                    previous_video,
                    7,
                    steps=6,
                    segment_length=8.0,
                    noise_seed=123,
                )

        _, loader = minimax.find_workflow_node(
            workflow,
            minimax.REFRESH_LOAD_VIDEO_NODE_NAME,
            "prepared refresh",
            "VHS_LoadVideoPath",
        )
        self.assertEqual(loader["inputs"]["skip_first_frames"], 170)
        self.assertEqual(loader["inputs"]["frame_load_cap"], 22)
        self.assertEqual(loader["inputs"]["format"], "H3")

        _, extend = minimax.find_workflow_node(
            workflow,
            minimax.REFRESH_EXTEND_NODE_NAME,
            "prepared refresh",
            "MiniMaxH3VideoExtendPatched",
        )
        self.assertEqual(extend["inputs"]["context_frames"], 7)

        _, duration, _, _ = minimax.find_duration_node(
            workflow, "prepared refresh"
        )
        self.assertEqual(duration["inputs"]["value"], 8.0)

    def test_refresh_routes_zero_one_and_multiple_references(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_video = os.path.join(directory, "previous.mp4")
            with open(previous_video, "wb") as handle:
                handle.write(b"video")
            for number in (1, 3):
                with open(os.path.join(directory, f"reference_{number}.png"), "wb") as handle:
                    handle.write(VALID_PNG)
            for selected in ((), (3,), (1, 3)):
                with self.subTest(selected=selected):
                    overrides = {number: f"reference_{number}.png" for number in selected}
                    with mock.patch("minimax.COMFY_INPUT", directory), mock.patch.dict(
                        minimax.REFERENCE_IMAGE_OVERRIDES, overrides, clear=True,
                    ), mock.patch("minimax.get_video_frame_count", return_value=192):
                        workflow = minimax.prepare_refresh_workflow(
                            8.0, 0.3, "prompt", previous_video, 7, noise_seed=123,
                        )
                    _, conditioner = minimax.find_workflow_node(
                        workflow, minimax.REFRESH_EXTEND_NODE_NAME, "test",
                    )
                    if not selected:
                        self.assertNotIn("ref_images", conditioner["inputs"])
                    elif len(selected) == 1:
                        image_id, _ = minimax.find_workflow_node(
                            workflow, "Reference Image 3", "test", "LoadImage",
                        )
                        self.assertEqual(conditioner["inputs"]["ref_images"], [image_id, 0])
                    else:
                        batch_id, batch = minimax.find_workflow_node(
                            workflow, minimax.REFRESH_REFERENCE_BATCH_NODE_NAME, "test", "ImageBatchMulti",
                        )
                        self.assertEqual(conditioner["inputs"]["ref_images"], [batch_id, 0])
                        self.assertEqual(batch["inputs"]["inputcount"], 2)

    def test_refresh_reference_batch_compacts_and_returns_picture_map(self):
        workflow = minimax.load_workflow(minimax.REFRESH_WORKFLOW_FILE)
        enable_all_references(workflow, "refresh")
        with tempfile.TemporaryDirectory() as directory:
            for number in (1, 3, 5):
                name = f"reference_{number}.png"
                with open(os.path.join(directory, name), "wb") as handle:
                    handle.write(VALID_PNG)
            for number in range(1, 7):
                _, node = minimax.find_workflow_node(
                    workflow,
                    f"Reference Image {number}",
                    "refresh test",
                    "LoadImage",
                )
                node["inputs"]["image"] = f"reference_{number}.png"

            removed, mapping = minimax.prune_missing_reference_images(
                workflow,
                "refresh test",
                "refresh",
                input_directory=directory,
                return_picture_slot_map=True,
            )

        self.assertEqual(removed, [2, 4, 6])
        self.assertEqual(mapping, {1: 1, 3: 2, 5: 3})
        _, batch = minimax.find_workflow_node(
            workflow,
            minimax.REFRESH_REFERENCE_BATCH_NODE_NAME,
            "refresh test",
            "ImageBatchMulti",
        )
        self.assertEqual(batch["inputs"]["inputcount"], 3)
        for slot in range(1, 4):
            self.assertIn(f"image_{slot}", batch["inputs"])
        self.assertNotIn("image_4", batch["inputs"])


if __name__ == "__main__":
    unittest.main()
