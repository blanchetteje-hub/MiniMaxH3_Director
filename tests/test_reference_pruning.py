import base64
import copy
import json
import os
import tempfile
import unittest

import minimax


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


class MissingReferenceImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            "initial": load_json(minimax.INITIAL_WORKFLOW_FILE),
            "append": load_json(minimax.APPEND_WORKFLOW_FILE),
            "refresh": load_json(minimax.REFRESH_WORKFLOW_FILE),
        }

    def test_missing_reference_connections_are_removed_from_all_workflows(self):
        with tempfile.TemporaryDirectory() as input_directory:
            for image_number in (1, 3, 5):
                with open(
                    os.path.join(input_directory, f"reference_{image_number}.png"),
                    "wb",
                ) as image:
                    image.write(VALID_PNG)

            for workflow_kind, source in self.workflows.items():
                with self.subTest(workflow=workflow_kind):
                    workflow = copy.deepcopy(source)
                    for image_number in range(1, 7):
                        _, image_node = minimax.find_workflow_node(
                            workflow,
                            f"Reference Image {image_number}",
                            f"{workflow_kind} test workflow",
                            "LoadImage",
                        )
                        image_node["inputs"]["image"] = (
                            f"reference_{image_number}.png"
                        )

                    removed = minimax.prune_missing_reference_images(
                        workflow,
                        f"{workflow_kind} test workflow",
                        workflow_kind,
                        input_directory=input_directory,
                    )

                    self.assertEqual(removed, [2, 4, 6])
                    destination_name = {
                        "initial": minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME,
                        "append": minimax.IMAGE_BATCH_NODE_NAME,
                        "refresh": minimax.REFRESH_CONDITIONING_NODE_NAME,
                    }[workflow_kind]
                    _, destination = minimax.find_workflow_node(
                        workflow,
                        destination_name,
                        f"{workflow_kind} test workflow",
                    )
                    if workflow_kind == "append":
                        for packed_slot, canonical_picture in enumerate(
                            (1, 3, 5),
                            start=1,
                        ):
                            source_id, _ = minimax.find_workflow_node(
                                workflow,
                                f"Reference Image {canonical_picture}",
                                "append test workflow",
                                "LoadImage",
                            )
                            self.assertEqual(
                                destination["inputs"][f"image_{packed_slot}"],
                                [source_id, 0],
                            )
                        self.assertNotIn("image_4", destination["inputs"])
                        continue
                    for image_number in range(1, 7):
                        input_name = f"ref_images.ref_image_{image_number - 1}"
                        self.assertEqual(
                            input_name in destination["inputs"],
                            image_number in {1, 3, 5},
                        )

    def test_absolute_existing_image_and_comfy_suffix_are_accepted(self):
        with tempfile.TemporaryDirectory() as input_directory:
            image_path = os.path.join(input_directory, "outside.png")
            with open(image_path, "wb") as image:
                image.write(VALID_PNG)
            workflow = copy.deepcopy(self.workflows["initial"])
            for image_number in range(1, 7):
                _, image_node = minimax.find_workflow_node(
                    workflow,
                    f"Reference Image {image_number}",
                    "initial test workflow",
                    "LoadImage",
                )
                image_node["inputs"]["image"] = f"{image_path} [input]"

            removed = minimax.prune_missing_reference_images(
                workflow,
                "initial test workflow",
                "initial",
                input_directory=input_directory,
            )

            self.assertEqual(removed, [])

    def test_valid_images_are_reconnected_to_their_exact_numbered_inputs(self):
        with tempfile.TemporaryDirectory() as input_directory:
            image_path = os.path.join(input_directory, "valid.png")
            with open(image_path, "wb") as image:
                image.write(VALID_PNG)

            for workflow_kind, source in self.workflows.items():
                with self.subTest(workflow=workflow_kind):
                    workflow = copy.deepcopy(source)
                    _, destination, input_names = minimax._reference_destination(
                        workflow,
                        f"{workflow_kind} test workflow",
                        workflow_kind,
                    )
                    for image_number, input_name in enumerate(input_names, start=1):
                        node_id, image_node = minimax.find_workflow_node(
                            workflow,
                            f"Reference Image {image_number}",
                            f"{workflow_kind} test workflow",
                            "LoadImage",
                        )
                        image_node["inputs"]["image"] = "valid.png"
                        destination["inputs"].pop(input_name, None)

                        minimax.prune_missing_reference_images(
                            workflow,
                            f"{workflow_kind} test workflow",
                            workflow_kind,
                            input_directory=input_directory,
                        )

                        self.assertEqual(
                            destination["inputs"][input_name],
                            [node_id, 0],
                        )

    def test_existing_but_undecodable_image_is_disconnected(self):
        with tempfile.TemporaryDirectory() as input_directory:
            image_path = os.path.join(input_directory, "corrupt.png")
            with open(image_path, "wb") as image:
                image.write(b"not an image")
            workflow = copy.deepcopy(self.workflows["initial"])
            for image_number in range(1, 7):
                _, image_node = minimax.find_workflow_node(
                    workflow,
                    f"Reference Image {image_number}",
                    "initial test workflow",
                    "LoadImage",
                )
                image_node["inputs"]["image"] = "corrupt.png"

            removed = minimax.prune_missing_reference_images(
                workflow,
                "initial test workflow",
                "initial",
                input_directory=input_directory,
            )

            self.assertEqual(removed, [1, 2, 3, 4, 5, 6])

    def test_append_batch_packs_valid_pictures_across_a_missing_slot(self):
        with tempfile.TemporaryDirectory() as input_directory:
            for image_number in (1, 3):
                with open(
                    os.path.join(input_directory, f"reference_{image_number}.png"),
                    "wb",
                ) as image:
                    image.write(VALID_PNG)
            workflow = copy.deepcopy(self.workflows["append"])
            for image_number in range(1, 7):
                _, image_node = minimax.find_workflow_node(
                    workflow,
                    f"Reference Image {image_number}",
                    "append test workflow",
                    "LoadImage",
                )
                image_node["inputs"]["image"] = f"reference_{image_number}.png"

            minimax.prune_missing_reference_images(
                workflow,
                "append test workflow",
                "append",
                input_directory=input_directory,
            )

            _, extender = minimax.find_workflow_node(
                workflow,
                minimax.VIDEO_EXTEND_NODE_NAME,
                "append test workflow",
            )
            batch_id, batch = minimax.find_workflow_node(
                workflow,
                minimax.IMAGE_BATCH_NODE_NAME,
                "append test workflow",
            )
            picture_1_id, _ = minimax.find_workflow_node(
                workflow,
                "Reference Image 1",
                "append test workflow",
                "LoadImage",
            )
            picture_3_id, _ = minimax.find_workflow_node(
                workflow,
                "Reference Image 3",
                "append test workflow",
                "LoadImage",
            )
            self.assertEqual(batch["inputs"]["image_1"], [picture_1_id, 0])
            self.assertEqual(batch["inputs"]["image_2"], [picture_3_id, 0])
            self.assertNotIn("image_3", batch["inputs"])
            self.assertEqual(extender["inputs"]["ref_images"], [batch_id, 0])

    def test_append_batch_packs_first_and_middle_picture_exclusions(self):
        with tempfile.TemporaryDirectory() as input_directory:
            for image_number in range(1, 7):
                with open(
                    os.path.join(input_directory, f"reference_{image_number}.png"),
                    "wb",
                ) as image:
                    image.write(VALID_PNG)

            for excluded, expected_canonical_order in (
                ({1}, (2, 3, 4, 5, 6)),
                ({2}, (1, 3, 4, 5, 6)),
            ):
                with self.subTest(excluded=excluded):
                    workflow = copy.deepcopy(self.workflows["append"])
                    canonical_node_ids = {}
                    for image_number in range(1, 7):
                        node_id, image_node = minimax.find_workflow_node(
                            workflow,
                            f"Reference Image {image_number}",
                            "append test workflow",
                            "LoadImage",
                        )
                        canonical_node_ids[image_number] = node_id
                        image_node["inputs"]["image"] = (
                            f"reference_{image_number}.png"
                        )

                    removed, picture_slot_map = (
                        minimax.prune_missing_reference_images(
                            workflow,
                            "append test workflow",
                            "append",
                            input_directory=input_directory,
                            excluded_picture_ids=excluded,
                            return_picture_slot_map=True,
                        )
                    )

                    _, batch = minimax.find_workflow_node(
                        workflow,
                        minimax.IMAGE_BATCH_NODE_NAME,
                        "append test workflow",
                    )
                    self.assertEqual(removed, sorted(excluded))
                    self.assertEqual(
                        picture_slot_map,
                        {
                            canonical: packed
                            for packed, canonical in enumerate(
                                expected_canonical_order,
                                start=1,
                            )
                        },
                    )
                    for packed, canonical in enumerate(
                        expected_canonical_order,
                        start=1,
                    ):
                        self.assertEqual(
                            batch["inputs"][f"image_{packed}"],
                            [canonical_node_ids[canonical], 0],
                        )

    def test_append_disconnects_optional_batch_when_no_picture_remains(self):
        with tempfile.TemporaryDirectory() as input_directory:
            workflow = copy.deepcopy(self.workflows["append"])
            for image_number in range(1, 7):
                image_path = os.path.join(
                    input_directory,
                    f"reference_{image_number}.png",
                )
                with open(image_path, "wb") as image:
                    image.write(VALID_PNG)
                _, image_node = minimax.find_workflow_node(
                    workflow,
                    f"Reference Image {image_number}",
                    "append test workflow",
                    "LoadImage",
                )
                image_node["inputs"]["image"] = os.path.basename(image_path)

            removed, picture_slot_map = minimax.prune_missing_reference_images(
                workflow,
                "append test workflow",
                "append",
                input_directory=input_directory,
                excluded_picture_ids=set(range(1, 7)),
                return_picture_slot_map=True,
            )

            _, extender = minimax.find_workflow_node(
                workflow,
                minimax.VIDEO_EXTEND_NODE_NAME,
                "append test workflow",
            )
            self.assertEqual(removed, list(range(1, 7)))
            self.assertEqual(picture_slot_map, {})
            self.assertNotIn("ref_images", extender["inputs"])


if __name__ == "__main__":
    unittest.main()
