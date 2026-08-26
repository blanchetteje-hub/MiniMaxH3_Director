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

    def test_picture_sentence_assigns_subject_number_from_picture_number(self):
        definitions = (
            "Picture 1 (from Shot 1) is Amy and aligns with the "
            "0.00-second mark of the target video."
        )

        self.assertEqual(
            minimax.parse_subject_registry(definitions),
            {
                1: {
                    "name": "Amy",
                    "picture_ids": [1],
                    "picture_id": 1,
                    "speaker_id": "S1",
                }
            },
        )
        self.assertEqual(
            minimax.parse_defined_subjects(definitions),
            [(1, "Amy")],
        )

    def test_short_picture_sentence_assigns_subject_number_from_picture_number(self):
        definitions = "Picture 1 (from Shot 1) is Amy."

        self.assertEqual(
            minimax.parse_subject_registry(definitions),
            {
                1: {
                    "name": "Amy",
                    "picture_ids": [1],
                    "picture_id": 1,
                    "speaker_id": "S1",
                }
            },
        )
        self.assertEqual(
            minimax.parse_defined_subjects(definitions),
            [(1, "Amy")],
        )

    def test_angle_bracket_picture_sentence_assigns_subject_and_speaker(self):
        definitions = "<Picture 1> is Amy."

        self.assertEqual(
            minimax.parse_subject_registry(definitions),
            {
                1: {
                    "name": "Amy",
                    "picture_ids": [1],
                    "picture_id": 1,
                    "speaker_id": "S1",
                }
            },
        )
        self.assertEqual(
            minimax.parse_defined_subjects(definitions),
            [(1, "Amy")],
        )

    def test_explicit_subject_definition_remains_authoritative(self):
        definitions = (
            "<Subject 1> is Amy, referenced in <Picture 1>.\n"
            "Picture 2 (from Shot 2) is Bob and aligns with the "
            "0.00-second mark of the target video."
        )

        registry = minimax.parse_subject_registry(definitions)

        self.assertEqual(registry[1]["name"], "Amy")
        self.assertEqual(registry[2]["name"], "Bob")
        self.assertEqual(registry[1]["speaker_id"], "S1")
        self.assertEqual(registry[2]["speaker_id"], "S2")

    def test_video_created_subject_definition_has_no_picture_mapping(self):
        definitions = (
            "<Subject 3> is spider-alien, created in generated video "
            "segment 2 and continued from <Video 1>."
        )

        registry = minimax.parse_subject_registry(definitions)

        self.assertEqual(registry[3]["name"], "spider-alien")
        self.assertEqual(registry[3]["picture_ids"], [])
        self.assertIsNone(registry[3]["picture_id"])
        self.assertEqual(registry[3]["speaker_id"], "S3")
        self.assertEqual(registry[3]["origin_segment"], 2)
        self.assertEqual(
            minimax.parse_defined_subjects(definitions),
            [(3, "spider-alien")],
        )

    def test_new_video_subject_is_registered_internally_once(self):
        definitions = "<Subject 1> is Amy, referenced in <Picture 1>."
        state = minimax.continuity_state_for_registry(definitions)
        state["subjects"]["spider-alien"] = {
            "subject_id": 2,
            "name": "spider-alien",
            "picture_ids": [],
            "picture_id": None,
            "speaker_id": None,
            "origin_segment": 4,
            "position": "above Amy",
            "pose_action": "moving",
            "wardrobe": {
                "upper": "N/A",
                "lower": "N/A",
                "footwear": "N/A",
                "other": "N/A",
            },
            "body_state": "segmented body and eight legs",
            "physical_condition": "N/A",
            "held_props": [],
        }

        additional, added = minimax.collect_additional_subject_definitions(
            definitions,
            [],
            state,
            origin_segment=4,
        )
        updated = minimax.combine_subject_definitions(definitions, additional)
        additional_again, added_again = (
            minimax.collect_additional_subject_definitions(
                definitions,
                additional,
                state,
                origin_segment=5,
            )
        )

        expected = (
            "<Subject 2> is spider-alien, created in generated video "
            "segment 4 and continued from <Video 1>."
        )
        self.assertEqual(added, [expected])
        self.assertEqual(additional, [expected])
        self.assertIn(expected, updated)
        self.assertEqual(additional_again, additional)
        self.assertEqual(added_again, [])
        self.assertEqual(updated.count("<Subject 2>"), 1)

        continuation = minimax.format_authoritative_opening_state(
            state,
            updated,
        )
        prompt = minimax.build_h3_prompt(
            {
                "detailed_description": (
                    "[Shot 5] Camera continues from the previous shot. "
                    "The spider-alien moves above Amy."
                ),
                "overall_soundscape": "Metal machinery hums.",
                "non_diegetic_music": "N/A",
            },
            updated,
            previous_state=continuation,
            segment_number=5,
        )
        self.assertLess(prompt.index(expected), prompt.index("<Video 1>"))
        self.assertIn("<Subject 2>: fully_preserved", prompt)

    def test_append_validation_is_independent_of_exported_node_ids(self):
        workflow = renumber_workflow(self.append)

        minimax.validate_workflow(
            workflow,
            "renumbered append workflow",
            is_append=True
        )

    def test_append_workflow_defaults_to_twenty_two_context_frames_and_pins_last(self):
        _, extender = minimax.find_workflow_node(
            self.append,
            minimax.VIDEO_EXTEND_NODE_NAME,
            "append workflow",
            "MiniMaxH3VideoExtendPatched",
        )

        self.assertEqual(extender["inputs"]["context_frames"], 22)
        self.assertIs(extender["inputs"]["pin_last_frame"], True)

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

    def test_reference_images_match_and_are_verified_in_both_workflows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_name = "opening.png"
            open(os.path.join(temp_dir, image_name), "wb").close()
            initial = copy.deepcopy(self.initial)
            append = copy.deepcopy(self.append)
            for workflow in (initial, append):
                for image_number in range(1, 7):
                    _, node = minimax.find_workflow_node(
                        workflow,
                        f"Reference Image {image_number}",
                        "test workflow",
                        "LoadImage",
                    )
                    node["inputs"]["image"] = image_name

            with mock.patch("builtins.print") as print_mock:
                minimax.verify_reference_images(initial, append, temp_dir)

            self.assertEqual(print_mock.call_count, 6)
            print_mock.assert_any_call("Image opening.png verified.")

    def test_reference_image_mapping_must_match_between_workflows(self):
        initial = copy.deepcopy(self.initial)
        append = copy.deepcopy(self.append)
        _, node = minimax.find_workflow_node(
            append,
            "Reference Image 1",
            "append workflow",
            "LoadImage",
        )
        node["inputs"]["image"] = "different.png"

        with mock.patch("builtins.print") as print_mock:
            minimax.verify_reference_images(initial, append, tempfile.gettempdir())
        print_mock.assert_any_call(
            "WARNING: Reference Image 1 differs between workflows: "
            "'0.png' vs 'different.png'."
        )

    def test_unconnected_reference_image_slot_is_skipped(self):
        initial = copy.deepcopy(self.initial)
        append = copy.deepcopy(self.append)
        _, initial_target = minimax.find_workflow_node(
            initial,
            "MiniMax H3 Reference to Video",
            "initial workflow",
        )
        del initial_target["inputs"]["ref_images.ref_image_3"]

        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, "0.png"), "wb").close()
            with mock.patch("builtins.print") as print_mock:
                minimax.verify_reference_images(initial, append, temp_dir)

        print_mock.assert_any_call("Image 0.png verified.")
        self.assertFalse(
            any(
                "ref_images.ref_image_3" in call.args[0]
                for call in print_mock.call_args_list
            )
        )

    def test_initial_preparation_updates_nodes_by_title_after_renumbering(self):
        workflow = renumber_workflow(self.initial)
        with mock.patch("minimax.load_workflow", return_value=workflow), mock.patch(
            "minimax.secrets.randbelow", return_value=123456
        ):
            prepared = minimax.prepare_initial_workflow(
                6.0, 0.5, "prompt", 4, steps=12,
                lora_override=("beat.safetensors", 0.42),
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
        _, lora = minimax.find_workflow_node(
            prepared,
            minimax.LORA_NODE_NAME,
            "prepared initial",
        )
        self.assertEqual(lora["inputs"]["lora_name"], "beat.safetensors")
        self.assertEqual(lora["inputs"]["strength_model"], 0.42)
        _, scheduler = minimax.find_workflow_node(
            prepared,
            minimax.SCHEDULER_NODE_NAME,
            "prepared initial",
        )
        self.assertEqual(scheduler["inputs"]["steps"], 12)

    def test_zero_loras_remove_placeholder_and_bypass_it_in_both_workflows(self):
        cases = (
            (self.initial, "79"),
            (self.append, "138"),
        )
        for template, consumer_id in cases:
            with self.subTest(consumer=consumer_id):
                workflow = copy.deepcopy(template)
                minimax.configure_lora_chain(workflow, [], "test workflow")

                self.assertFalse(any(
                    node.get("class_type") == "LoraLoaderModelOnly"
                    for node in workflow.values()
                ))
                self.assertEqual(workflow[consumer_id]["inputs"]["model"], ["90", 0])
        self.assertEqual(self.initial["140"]["inputs"]["lora_name"], "")
        self.assertEqual(self.append["149"]["inputs"]["lora_name"], "")

    def test_unlimited_loras_are_chained_in_order_in_both_workflows(self):
        specs = [
            ("global-one.safetensors", 0.4),
            ("global-two.safetensors", 0.8),
            ("beat-one.safetensors", -0.2),
            ("beat-two.safetensors", 1.25),
        ]
        cases = (
            (self.initial, "79"),
            (self.append, "138"),
        )
        for template, consumer_id in cases:
            with self.subTest(consumer=consumer_id):
                workflow = copy.deepcopy(template)
                minimax.configure_lora_chain(workflow, specs, "test workflow")
                loaders = {
                    node_id: node
                    for node_id, node in workflow.items()
                    if node.get("class_type") == "LoraLoaderModelOnly"
                }
                self.assertEqual(len(loaders), len(specs))

                reversed_chain = []
                current_id = workflow[consumer_id]["inputs"]["model"][0]
                while current_id in loaders:
                    loader = loaders[current_id]
                    reversed_chain.append((
                        loader["inputs"]["lora_name"],
                        loader["inputs"]["strength_model"],
                    ))
                    current_id = loader["inputs"]["model"][0]
                self.assertEqual(current_id, "90")
                self.assertEqual(list(reversed(reversed_chain)), specs)

                if consumer_id == "79":
                    self.assertEqual(
                        workflow["80"]["inputs"]["model"],
                        workflow["79"]["inputs"]["model"],
                    )

    def test_append_preparation_updates_nodes_by_title_after_renumbering(self):
        workflow = renumber_workflow(self.append)
        _, extender = minimax.find_workflow_node(
            workflow,
            minimax.VIDEO_EXTEND_NODE_NAME,
            "renumbered append",
            "MiniMaxH3VideoExtendPatched",
        )
        extender["inputs"]["context_frames"] = 2
        extender["inputs"]["pin_last_frame"] = False
        with mock.patch("minimax.load_workflow", return_value=workflow), mock.patch(
            "minimax.os.path.exists", return_value=True
        ), mock.patch("minimax.secrets.randbelow", return_value=654321):
            prepared = minimax.prepare_append_workflow(
                6.0,
                "prompt",
                "previous.mp4",
                7,
                steps=10,
                context_frames=12,
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
        _, extender = minimax.find_workflow_node(
            prepared,
            minimax.VIDEO_EXTEND_NODE_NAME,
            "prepared append",
            "MiniMaxH3VideoExtendPatched",
        )
        self.assertEqual(extender["inputs"]["context_frames"], 12)
        self.assertIs(extender["inputs"]["pin_last_frame"], True)

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
