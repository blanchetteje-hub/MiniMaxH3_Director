import copy
import json
import os
import tempfile
import unittest

import minimax


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
                    image.write(b"present")

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
                image.write(b"present")
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


if __name__ == "__main__":
    unittest.main()
