import copy
import unittest

import minimax


class RenderedWardrobeStateTests(unittest.TestCase):
    def prompt_state(self):
        return {
            "subjects": {
                "Mark": {
                    "name": "Mark",
                    "body_state": "tall man with a distinctive scar",
                    "wardrobe": {
                        "upper": "requested red shirt",
                        "lower": "requested black jeans",
                        "footwear": "requested boots",
                        "other": "requested watch",
                    },
                },
                "Amy": {
                    "name": "Amy",
                    "wardrobe": {
                        "upper": "requested yellow blouse",
                        "lower": "requested skirt",
                        "footwear": "requested sandals",
                        "other": "requested necklace",
                    },
                },
            }
        }

    def visual_state(self, *subjects):
        return {"subjects": list(subjects)}

    def subject(self, name, wardrobe, visible=True):
        return {
            "name": name,
            "visible": visible,
            "wardrobe": wardrobe,
        }

    def test_rendered_wardrobe_is_diagnostic_not_a_canonical_update(self):
        merged = minimax.merge_prompt_and_visual_end_state(
            self.prompt_state(),
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "torn blue jacket",
                    "lower": "not_visible",
                    "footwear": "white sneakers",
                    "other": "unknown",
                },
            )),
        )

        self.assertEqual(
            merged["subjects"]["Mark"]["wardrobe"],
            {
                "upper": "requested red shirt",
                "lower": "requested black jeans",
                "footwear": "requested boots",
                "other": "requested watch",
            },
        )
        self.assertEqual(
            merged["subjects"]["Mark"]["body_state"],
            "tall man with a distinctive scar",
        )

    def test_unknown_rendered_details_do_not_overwrite_authoritative_wardrobe(self):
        prompt = self.prompt_state()
        prompt["subjects"]["Mark"]["wardrobe"]["upper"] = "previous rendered coat"
        merged = minimax.merge_prompt_and_visual_end_state(
            prompt,
            self.visual_state(self.subject(
                "Mark",
                {field: "unknown" for field in minimax._WARDROBE_FIELDS},
            )),
        )

        self.assertEqual(merged["subjects"]["Mark"]["wardrobe"], prompt["subjects"]["Mark"]["wardrobe"])

    def test_rendered_duplicate_wardrobe_slots_do_not_rewrite_state(self):
        merged = minimax.merge_prompt_and_visual_end_state(
            self.prompt_state(),
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "blue jacket",
                    "lower": "blue jeans",
                    "footwear": "blue jeans",
                    "other": "unknown",
                },
            )),
        )

        wardrobe = merged["subjects"]["Mark"]["wardrobe"]
        self.assertEqual(wardrobe["lower"], "requested black jeans")
        self.assertEqual(wardrobe["footwear"], "requested boots")

    def test_new_rendered_wardrobe_does_not_replace_canonical_state(self):
        first = minimax.merge_prompt_and_visual_end_state(
            self.prompt_state(),
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "red dress",
                    "lower": "N/A",
                    "footwear": "black boots",
                    "other": "N/A",
                },
            )),
        )
        second = minimax.merge_prompt_and_visual_end_state(
            first,
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "torn red dress",
                    "lower": "N/A",
                    "footwear": "N/A",
                    "other": "N/A",
                },
            )),
        )

        self.assertEqual(second["subjects"]["Mark"]["wardrobe"]["upper"], "requested red shirt")
        self.assertEqual(
            second["subjects"]["Mark"]["wardrobe"]["footwear"],
            "requested boots",
        )

    def test_visual_none_does_not_clear_wardrobe_slot(self):
        merged = minimax.merge_prompt_and_visual_end_state(
            self.prompt_state(),
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": None,
                    "lower": "None",
                },
            )),
        )

        wardrobe = merged["subjects"]["Mark"]["wardrobe"]
        self.assertEqual(wardrobe["upper"], "requested red shirt")
        self.assertEqual(wardrobe["lower"], "requested black jeans")
        self.assertEqual(wardrobe["footwear"], "requested boots")

    def test_subjects_keep_independent_canonical_wardrobe_state(self):
        merged = minimax.merge_prompt_and_visual_end_state(
            self.prompt_state(),
            self.visual_state(
                self.subject(
                    "Mark",
                    {
                        "upper": "green coat",
                        "lower": "gray trousers",
                        "footwear": "brown boots",
                        "other": "N/A",
                    },
                ),
                self.subject(
                    "Amy",
                    {
                        "upper": "white blouse",
                        "lower": "blue skirt",
                        "footwear": "not_visible",
                        "other": "N/A",
                    },
                ),
            ),
        )

        self.assertEqual(merged["subjects"]["Mark"]["wardrobe"]["upper"], "requested red shirt")
        self.assertEqual(
            merged["subjects"]["Amy"]["wardrobe"]["upper"],
            "requested yellow blouse",
        )
        self.assertEqual(
            merged["subjects"]["Amy"]["wardrobe"]["footwear"],
            "requested sandals",
        )

    def test_unseen_subject_keeps_wardrobe_when_camera_does_not_show_them(self):
        merged = minimax.merge_prompt_and_visual_end_state(
            self.prompt_state(),
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "green coat",
                    "lower": "gray trousers",
                    "footwear": "brown boots",
                    "other": "N/A",
                },
            )),
        )

        self.assertEqual(
            merged["subjects"]["Amy"]["wardrobe"],
            self.prompt_state()["subjects"]["Amy"]["wardrobe"],
        )

    def test_prompt_only_preserves_wardrobe_and_scrubs_aliases(self):
        state = {
            "subjects": {
                "Mark": {
                    "name": "Mark",
                    "wardrobe": {"upper": "invented shirt"},
                    "clothing": {"lower": "invented jeans"},
                    "clothing_condition": "torn",
                    "body_state": {
                        "clothing": {"footwear": "invented boots"},
                        "injuries": ["scraped palm"],
                        "topology": "intact",
                    },
                    "persistent_effects": [
                        "red shirt remains",
                        "the garage door is damaged",
                    ],
                }
            }
        }
        before = copy.deepcopy(state)

        cleared = minimax.clear_unrendered_wardrobes(state)
        subject = cleared["subjects"]["Mark"]

        self.assertEqual(subject["wardrobe"], {"upper": "invented shirt"})
        for field in ("clothing", "clothing_condition"):
            self.assertNotIn(field, subject)
        self.assertNotIn("clothing", subject["body_state"])
        self.assertEqual(subject["body_state"]["injuries"], ["scraped palm"])
        self.assertEqual(subject["body_state"]["topology"], "intact")
        self.assertEqual(subject["persistent_effects"], ["the garage door is damaged"])
        self.assertEqual(state, before)

    def test_wrapped_subject_wardrobe_survives_prompt_only_processing(self):
        state = {
            "subjects": [
                {"Mark": {
                    "name": "Mark",
                    "wardrobe": {"upper": "invented shirt"},
                }}
            ]
        }

        cleared = minimax.clear_unrendered_wardrobes(state)

        self.assertEqual(
            cleared["subjects"][0]["Mark"]["wardrobe"]["upper"],
            "invented shirt",
        )

    def test_visual_merge_does_not_clear_wrapped_offscreen_wardrobe(self):
        state = {
            "subjects": [
                {"Mark": {
                    "name": "Mark",
                    "wardrobe": {"upper": "invented shirt"},
                    "body_state": {
                        "clothing": {"lower": "invented jeans"},
                        "injuries": ["bruise"],
                    },
                }}
            ]
        }

        merged = minimax.merge_prompt_and_visual_end_state(state, {})

        subject = merged["subjects"][0]["Mark"]
        self.assertEqual(subject["wardrobe"]["upper"], "invented shirt")
        self.assertNotIn("clothing", subject["body_state"])
        self.assertEqual(subject["body_state"]["injuries"], ["bruise"])

    def test_malformed_clothing_alias_cannot_bypass_sanitization(self):
        state = {
            "subjects": {
                "Mark": {
                    "name": "Mark",
                    "body_state": {
                        "clothing": {"upper": "invented jacket"},
                        "wardrobe": {"lower": "invented jeans"},
                        "physical_condition": "wet clothing",
                        "injuries": ["bruise"],
                    },
                    "clothing_state": "clean",
                }
            }
        }

        sanitized = minimax.sanitize_prompt_derived_continuity_state(state)
        subject = sanitized["subjects"]["Mark"]

        self.assertNotIn("clothing_state", subject)
        self.assertNotIn("clothing", subject["body_state"])
        self.assertNotIn("wardrobe", subject["body_state"])
        self.assertNotIn("physical_condition", subject["body_state"])
        self.assertEqual(subject["body_state"]["injuries"], ["bruise"])

    def test_identity_is_not_copied_into_wardrobe(self):
        prompt = self.prompt_state()
        before_identity = copy.deepcopy(prompt["subjects"]["Mark"]["body_state"])
        merged = minimax.merge_prompt_and_visual_end_state(
            prompt,
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "black sweater",
                    "lower": "N/A",
                    "footwear": "N/A",
                    "other": "N/A",
                },
            )),
        )

        self.assertEqual(merged["subjects"]["Mark"]["body_state"], before_identity)
        self.assertNotIn(before_identity, merged["subjects"]["Mark"]["wardrobe"].values())

    def test_rendered_clothing_does_not_promote_legacy_shape_to_canonical(self):
        prompt = {
            "subjects": {
                "Mark": {
                    "name": "Mark",
                    "clothing": {"upper": "requested shirt"},
                }
            }
        }
        merged = minimax.merge_prompt_and_visual_end_state(
            prompt,
            self.visual_state(self.subject(
                "Mark",
                {
                    "upper": "gray coat",
                    "lower": "N/A",
                    "footwear": "N/A",
                    "other": "N/A",
                },
            )),
        )

        self.assertNotIn("wardrobe", merged["subjects"]["Mark"])
        self.assertNotIn("clothing", merged["subjects"]["Mark"])


if __name__ == "__main__":
    unittest.main()
