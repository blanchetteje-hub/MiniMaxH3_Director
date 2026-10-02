import base64
import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import minimax


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def enable_all_references(workflow, kind):
    _, destination, names = minimax._reference_destination(workflow, "test", kind)
    for number, name in enumerate(names, start=1):
        node_id, _ = minimax.find_workflow_node(workflow, f"Reference Image {number}", "test", "LoadImage")
        container, key = minimax._reference_input_container(destination, name)
        container[key] = [node_id, 0]


class MissingReferenceImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            "initial": load_json(minimax.INITIAL_WORKFLOW_FILE),
            "append": load_json(minimax.APPEND_WORKFLOW_FILE),
            "refresh": load_json(minimax.REFRESH_WORKFLOW_FILE),
            "repair": load_json(minimax.REPAIR_WORKFLOW_FILE),
        }
        for kind, workflow in cls.workflows.items():
            enable_all_references(workflow, kind)

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
                    if workflow_kind == "refresh":
                        _, destination = minimax.find_workflow_node(
                            workflow,
                            minimax.REFRESH_REFERENCE_BATCH_NODE_NAME,
                            f"{workflow_kind} test workflow",
                            "ImageBatchMulti",
                        )
                        self.assertEqual(destination["inputs"]["inputcount"], 3)
                        self.assertTrue(all(
                            f"image_{slot}" in destination["inputs"]
                            for slot in (1, 2, 3)
                        ))
                        self.assertNotIn("image_4", destination["inputs"])
                    else:
                        _, destination, _ = minimax._reference_destination(
                            workflow,
                            f"{workflow_kind} test workflow",
                            workflow_kind,
                        )
                        for image_number in range(1, 7):
                            input_name = f"ref_images.ref_image_{image_number - 1}"
                            container, leaf_name = minimax._reference_input_container(
                                destination,
                                input_name,
                            )
                            self.assertEqual(
                                leaf_name in container,
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

                        with mock.patch.dict(minimax.REFERENCE_IMAGE_OVERRIDES, {image_number: "valid.png"}, clear=True):
                            minimax.apply_reference_image_overrides(workflow, "test")
                        minimax.prune_missing_reference_images(
                            workflow,
                            f"{workflow_kind} test workflow",
                            workflow_kind,
                            input_directory=input_directory,
                        )

                        if workflow_kind == "refresh":
                            self.assertIn(
                                [node_id, 0],
                                [
                                    value
                                    for key, value in destination["inputs"].items()
                                    if key.startswith("image_")
                                ],
                            )
                        else:
                            self.assertEqual(
                                destination["inputs"][input_name],
                                [node_id, 0],
                            )

    def test_disconnected_valid_caterpillar_is_not_reconnected(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "caterpillar1.webp"), "wb") as image:
                image.write(VALID_PNG)
            for kind, source in self.workflows.items():
                with self.subTest(workflow=kind):
                    workflow = copy.deepcopy(source)
                    _, node = minimax.find_workflow_node(workflow, "Reference Image 3", "test", "LoadImage")
                    node["inputs"]["image"] = "caterpillar1.webp"
                    _, destination, names = minimax._reference_destination(workflow, "test", kind)
                    container, key = minimax._reference_input_container(destination, names[2])
                    container.pop(key, None)
                    removed = minimax.prune_missing_reference_images(workflow, "test", kind, input_directory=directory)
                    self.assertIn(3, removed)
                    if kind == "refresh":
                        self.assertEqual(destination["inputs"]["inputcount"], 0)
                    else:
                        self.assertNotIn(key, container)

    def test_copy_preserves_source_selection_across_workflows(self):
        source = copy.deepcopy(self.workflows["initial"])
        _, destination, names = minimax._reference_destination(source, "test", "initial")
        for name in names[1:]:
            container, key = minimax._reference_input_container(destination, name)
            container.pop(key, None)
        _, stale = minimax.find_workflow_node(source, "Reference Image 3", "test", "LoadImage")
        stale["inputs"]["image"] = "caterpillar1.webp"
        for kind in ("append", "refresh", "repair"):
            with self.subTest(workflow=kind):
                target = copy.deepcopy(self.workflows[kind])
                minimax.copy_reference_image_inputs(source, target, "test")
                _, destination, names = minimax._reference_destination(target, "test", kind)
                for number, name in enumerate(names, start=1):
                    container, key = minimax._reference_input_container(destination, name)
                    self.assertEqual(key in container, number == 1)

    def test_sparse_cli_override_enables_only_requested_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "chosen.png"), "wb") as image:
                image.write(VALID_PNG)
            for kind in self.workflows:
                with self.subTest(workflow=kind):
                    path = {"initial": minimax.INITIAL_WORKFLOW_FILE, "append": minimax.APPEND_WORKFLOW_FILE,
                            "refresh": minimax.REFRESH_WORKFLOW_FILE, "repair": minimax.REPAIR_WORKFLOW_FILE}[kind]
                    workflow = load_json(path)
                    with mock.patch.dict(minimax.REFERENCE_IMAGE_OVERRIDES, {3: "chosen.png"}, clear=True):
                        minimax.apply_reference_image_overrides(workflow, "test")
                    removed, mapping = minimax.prune_missing_reference_images(
                        workflow, "test", kind, input_directory=directory, return_picture_slot_map=True)
                    self.assertEqual(removed, [1, 2, 4, 5, 6])
                    self.assertEqual(mapping, {3: 1 if kind == "refresh" else 3})

    def test_existing_placeholder_is_never_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "0.jpg"), "wb") as image:
                image.write(VALID_PNG)
            for kind, source in self.workflows.items():
                with self.subTest(workflow=kind):
                    removed = minimax.prune_missing_reference_images(copy.deepcopy(source), "test", kind, input_directory=directory)
                    self.assertEqual(removed, list(range(1, 7)))

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


if __name__ == "__main__":
    unittest.main()
