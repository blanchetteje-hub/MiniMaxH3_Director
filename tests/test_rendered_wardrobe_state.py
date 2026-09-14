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

    def test_rendered_wardrobe_updates_only_positive_observations(self):
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
                "upper": "torn blue jacket",
                "lower": "requested black jeans",
                "footwear": "white sneakers",
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

    def test_duplicate_rendered_wardrobe_slots_are_removed(self):
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
        self.assertEqual(wardrobe["lower"], "blue jeans")
        self.assertEqual(wardrobe["footwear"], "requested boots")

    def test_new_rendered_wardrobe_replaces_older_state(self):
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

        self.assertEqual(
            second["subjects"]["Mark"]["wardrobe"]["upper"],
            "torn red dress",
        )
        self.assertNotIn("red dress", second["subjects"]["Mark"]["wardrobe"].values())
        self.assertEqual(
            second["subjects"]["Mark"]["wardrobe"]["footwear"],
            "black boots",
        )

    def test_explicit_none_clears_wardrobe_slot(self):
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
        self.assertEqual(wardrobe["upper"], "N/A")
        self.assertEqual(wardrobe["lower"], "N/A")
        self.assertEqual(wardrobe["footwear"], "requested boots")

    def test_subjects_keep_independent_rendered_wardrobe_state(self):
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

        self.assertEqual(
            merged["subjects"]["Mark"]["wardrobe"]["upper"],
            "green coat",
        )
        self.assertEqual(
            merged["subjects"]["Amy"]["wardrobe"]["upper"],
            "white blouse",
        )
        self.assertEqual(
            merged["subjects"]["Amy"]["wardrobe"]["footwear"],
            "requested sandals",
        )

    def test_unseen_subject_prompt_wardrobe_is_cleared_without_visual_evidence(self):
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

        self.assertNotIn("wardrobe", merged["subjects"]["Amy"])

    def test_prompt_only_clears_wardrobe_aliases_but_preserves_body_state(self):
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

        for field in ("wardrobe", "clothing", "clothing_condition"):
            self.assertNotIn(field, subject)
        self.assertNotIn("clothing", subject["body_state"])
        self.assertEqual(subject["body_state"]["injuries"], ["scraped palm"])
        self.assertEqual(subject["body_state"]["topology"], "intact")
        self.assertEqual(subject["persistent_effects"], ["the garage door is damaged"])
        self.assertEqual(state, before)

    def test_malformed_wrapped_subject_cannot_bypass_prompt_only_clearing(self):
        state = {
            "subjects": [
                {"Mark": {
                    "name": "Mark",
                    "wardrobe": {"upper": "invented shirt"},
                }}
            ]
        }

        cleared = minimax.clear_unrendered_wardrobes(state)

        self.assertNotIn("wardrobe", cleared["subjects"][0]["Mark"])

    def test_malformed_wrapped_subject_cannot_bypass_visual_merge_clearing(self):
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
        self.assertNotIn("wardrobe", subject)
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

    def test_legacy_clothing_shape_is_canonicalized_to_wardrobe(self):
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

        self.assertEqual(
            merged["subjects"]["Mark"]["wardrobe"]["upper"],
            "gray coat",
        )
        self.assertNotIn("clothing", merged["subjects"]["Mark"])


if __name__ == "__main__":
    unittest.main()
