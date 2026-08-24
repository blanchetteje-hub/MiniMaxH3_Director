import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import minimax


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def renumber_workflow(workflow):
    """Return the same graph with unrelated, non-sequential node IDs."""

    old_ids = list(workflow)
    mapping = {
        old_id: str(9000 + (index * 37))
        for index, old_id in enumerate(reversed(old_ids), start=1)
    }
    renumbered = {
        mapping[old_id]: copy.deepcopy(node)
        for old_id, node in workflow.items()
    }
    for node in renumbered.values():
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for name, value in inputs.items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and str(value[0]) in mapping
            ):
                inputs[name] = [mapping[str(value[0])], value[1]]
    return renumbered


class WorkflowNameResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = load_json(minimax.INITIAL_WORKFLOW_FILE)
        cls.append = load_json(minimax.APPEND_WORKFLOW_FILE)

    def test_initial_validation_is_independent_of_exported_node_ids(self):
        workflow = renumber_workflow(self.initial)

        minimax.validate_workflow(
            workflow,
            "renumbered initial workflow",
            is_append=False
        )

    def test_append_validation_is_independent_of_exported_node_ids(self):
        workflow = renumber_workflow(self.append)

        minimax.validate_workflow(
            workflow,
            "renumbered append workflow",
            is_append=True
        )

    def test_append_validation_allows_any_number_of_reference_images(self):
        workflow = copy.deepcopy(self.append)
        reference_node_ids = {
            node_id
            for node_id, node in workflow.items()
            if node.get("_meta", {}).get("title", "").startswith(
                "Reference Image "
            )
        }
        for node_id in reference_node_ids:
            del workflow[node_id]

        _, image_batch = minimax.find_workflow_node(
            workflow,
            minimax.IMAGE_BATCH_NODE_NAME,
            "workflow without reference images",
            "ImageBatchMulti",
        )
        image_batch["inputs"] = {
            key: value
            for key, value in image_batch["inputs"].items()
            if not (
                isinstance(value, list)
                and len(value) == 2
                and str(value[0]) in reference_node_ids
            )
        }

        minimax.validate_workflow(
            workflow,
            "append workflow without reference images",
            is_append=True,
        )

    def test_initial_preparation_updates_nodes_by_title_after_renumbering(self):
        workflow = renumber_workflow(self.initial)
        with mock.patch("minimax.load_workflow", return_value=workflow), mock.patch(
            "minimax.secrets.randbelow", return_value=123456
        ):
            prepared = minimax.prepare_initial_workflow(
                6.0, 0.5, "prompt", 4, steps=12
            )

        _, prompt = minimax.find_workflow_node(
            prepared,
            minimax.PROMPT_NODE_NAME,
            "prepared initial"
        )
        _, duration = minimax.find_workflow_node(
            prepared,
            minimax.DURATION_NODE_NAME,
            "prepared initial"
        )
        _, noise = minimax.find_workflow_node(
            prepared,
            minimax.NOISE_NODE_NAME,
            "prepared initial"
        )
        self.assertEqual(prompt["inputs"]["text"], "prompt")
        self.assertEqual(duration["inputs"]["value"], 6.0)
        self.assertEqual(noise["inputs"]["noise_seed"], 123457)
        _, scheduler = minimax.find_workflow_node(
            prepared,
            minimax.SCHEDULER_NODE_NAME,
            "prepared initial",
        )
        self.assertEqual(scheduler["inputs"]["steps"], 12)

    def test_append_preparation_updates_nodes_by_title_after_renumbering(self):
        workflow = renumber_workflow(self.append)
        with mock.patch("minimax.load_workflow", return_value=workflow), mock.patch(
            "minimax.os.path.exists", return_value=True
        ), mock.patch("minimax.secrets.randbelow", return_value=654321):
            prepared = minimax.prepare_append_workflow(
                6.0,
                "prompt",
                "previous.mp4",
                7,
                steps=10,
            )

        _, video = minimax.find_workflow_node(
            prepared,
            minimax.LOAD_VIDEO_NODE_NAME,
            "prepared append"
        )
        _, save = minimax.find_workflow_node(
            prepared,
            minimax.SAVE_VIDEO_NODE_NAME,
            "prepared append"
        )
        self.assertTrue(video["inputs"]["video"].endswith("previous.mp4"))
        self.assertEqual(
            save["inputs"]["filename_prefix"],
            "video/segment_0007"
        )
        _, noise = minimax.find_workflow_node(
            prepared,
            minimax.NOISE_NODE_NAME,
            "prepared append",
        )
        self.assertEqual(noise["inputs"]["noise_seed"], 654322)
        _, scheduler = minimax.find_workflow_node(
            prepared,
            minimax.SCHEDULER_NODE_NAME,
            "prepared append",
        )
        self.assertEqual(scheduler["inputs"]["steps"], 10)

    def test_history_output_uses_save_video_title_after_renumbering(self):
        workflow = renumber_workflow(self.initial)
        save_id, _ = minimax.find_workflow_node(
            workflow,
            minimax.SAVE_VIDEO_NODE_NAME,
            "renumbered workflow"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = "segment.mp4"
            open(os.path.join(temp_dir, filename), "wb").close()
            result = {
                "outputs": {
                    save_id: {
                        "images": [{"filename": filename, "subfolder": ""}]
                    }
                }
            }
            with mock.patch("minimax.COMFY_OUTPUT", temp_dir):
                path = minimax.get_video_path(result, workflow)

        self.assertTrue(path.endswith(filename))


if __name__ == "__main__":
    unittest.main()
