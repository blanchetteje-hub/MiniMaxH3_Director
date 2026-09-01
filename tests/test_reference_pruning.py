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
                    for image_number in range(1, 7):
                        input_name = (
                            f"image_{image_number}"
                            if workflow_kind == "append"
                            else f"ref_images.ref_image_{image_number - 1}"
                        )
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

    def test_append_batch_is_disconnected_when_valid_slots_have_a_gap(self):
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
            self.assertNotIn("ref_images", extender["inputs"])


if __name__ == "__main__":
    unittest.main()
