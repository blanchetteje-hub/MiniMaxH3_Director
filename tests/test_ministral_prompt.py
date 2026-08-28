"""Unit tests for deterministic Ministral-to-MiniMax H3 formatting.

The tests deliberately use only the standard library.  They describe the
public contract of ``ministral_formatter`` and avoid importing or contacting
LM Studio, ComfyUI, or any other service.
"""

from __future__ import annotations

import copy
import json
import re
import unittest

from ministral_formatter import format_ministral_prompt, validate_ministral_prompt


CORE_KEYS = (
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
    "completed_beat_ids",
)

SUBJECT_DEFINITIONS = (
    "<Subject 1> is Mark, a 40-year-old man referenced in <Picture 1>.\n"
    "<Subject 2> is Jill, a 35-year-old woman referenced in <Picture 2>."
)

BEATS = (
    "Show Mark, Jill, and his family.",
    "Show flying saucers flying overhead.",
    "Show Mark and Jill talking and trying to figure out what is happening.",
    "Show the saucers abducting Mark's family as they run away.",
)


def context_for(beat_number: int, **overrides: object) -> dict:
    """Build the documented formatter context for one sequential beat."""

    context = {
        "segment_number": beat_number,
        "segment_duration": 6.0,
        "subject_definitions": SUBJECT_DEFINITIONS,
        "completed_beat_ids": list(range(1, beat_number)),
        "next_beat_id": beat_number,
        "current_beat_text": BEATS[beat_number - 1],
        "later_beat_texts": list(BEATS[beat_number:]),
        "beat_deadline_required": True,
        "allow_silence": False,
        "hard_cut_required": beat_number % 3 == 0,
    }
    context.update(overrides)
    return context


def result(
    description: str,
    *,
    soundscape: str = "Theme-park crowds murmur as footsteps cross the pavement.",
    music: str = "N/A",
    completed: list[int] | None = None,
) -> dict:
    return {
        "detailed_description": description,
        "overall_soundscape": soundscape,
        "non_diegetic_music": music,
        "completed_beat_ids": [] if completed is None else completed,
    }


class FieldAndFixedPointTests(unittest.TestCase):
    def test_every_asterisk_is_removed_from_prompt_text(self) -> None:
        raw = result(
            "*[Shot 1]* Live-action, cinematic, **Mark**, Jill, and Mark's "
            "family stand together at a busy theme park.*",
            soundscape="*Crowds* murmur and **footsteps** cross the pavement.",
            music="*N/A*",
            completed=[1],
        )

        formatted = format_ministral_prompt(raw, context_for(1))

        for field in (
            "detailed_description",
            "overall_soundscape",
            "non_diegetic_music",
        ):
            self.assertNotIn("*", formatted[field])

    def test_legacy_description_field_is_migrated_to_detailed_description(self) -> None:
        raw = {
            "integrated_multimodal_description": (
                "[Shot 1] Live-action, cinematic, Mark, Jill, and Mark's "
                "family stand together in a busy theme park."
            ),
            "overall_soundscape": "Crowd chatter fills the park.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [1],
        }

        formatted = format_ministral_prompt(raw, context_for(1))

        self.assertIn("detailed_description", formatted)
        self.assertNotIn("integrated_multimodal_description", formatted)

    def test_plain_labeled_response_is_parsed_without_markdown(self) -> None:
        raw = """detailed_description: [Shot 1] Live-action, cinematic, Mark, Jill, and Mark's family stand together in a busy theme park.

overall_soundscape: Crowd chatter and footsteps fill the park.

non_diegetic_music: N/A

completed_beat_ids: [1]"""

        formatted = format_ministral_prompt(raw, context_for(1))

        self.assertEqual(tuple(formatted), CORE_KEYS)
        self.assertEqual(formatted["completed_beat_ids"], [1])
        self.assertEqual(validate_ministral_prompt(formatted, context_for(1)), [])

    def test_code_fenced_json_and_decorated_duplicate_labels_are_cleaned(self) -> None:
        raw = {
            "detailed_description": (
                "**detailed_description:** [Shot 1] Live-action, cinematic, "
                "a medium-wide shot shows Mark, Jill, and Mark's family together at a busy "
                "theme park."
            ),
            "overall_soundscape": (
                "### overall_soundscape: Crowd chatter and footsteps fill the park."
            ),
            "non_diegetic_music": "non_diegetic_music: none",
            "completed_beat_ids": ["B001"],
        }
        fenced = "```json\n" + json.dumps(raw) + "\n```"

        formatted = format_ministral_prompt(fenced, context_for(1))

        self.assertEqual(tuple(formatted), CORE_KEYS)
        self.assertTrue(formatted["detailed_description"].startswith("[Shot 1]"))
        for value in formatted.values():
            if isinstance(value, str):
                self.assertNotIn("```", value)
                self.assertNotIn("**", value)
                self.assertNotIn("###", value)
        self.assertEqual(formatted["non_diegetic_music"], "N/A")
        self.assertEqual(formatted["completed_beat_ids"], [1])

    def test_valid_prompt_is_idempotent(self) -> None:
        valid = result(
            "[Shot 1] Live-action, cinematic, a medium-wide shot shows Mark, Jill, and "
            "Mark's family enjoying a busy theme park together.",
            completed=[1],
        )

        first = format_ministral_prompt(copy.deepcopy(valid), context_for(1))
        second = format_ministral_prompt(copy.deepcopy(first), context_for(1))

        self.assertEqual(first, second)
        self.assertEqual(validate_ministral_prompt(first, context_for(1)), [])

    def test_formatter_and_validator_do_not_mutate_their_inputs(self) -> None:
        original = result(
            "[Shot 1] At 00:00.000, Live-action, cinematic, Mark, Jill, and Mark's family "
            "stand together at a theme park.",
            music="none",
            completed=["B001"],
        )
        context = context_for(1)
        original_snapshot = copy.deepcopy(original)
        context_snapshot = copy.deepcopy(context)

        formatted = format_ministral_prompt(original, context)
        validate_ministral_prompt(formatted, context)

        self.assertEqual(original, original_snapshot)
        self.assertEqual(context, context_snapshot)

    def test_repair_loop_reaches_a_fixed_point_on_repeated_noise(self) -> None:
        noisy = result(
            "**detailed_description:** " * 12
            + "[Shot 1] At 00:00.000, Live-action, cinematic, Mark, Jill, and Mark's family "
            "stand together in the theme park.",
            music="NONE.",
            completed=[1],
        )

        repaired = format_ministral_prompt(noisy, context_for(1))

        self.assertEqual(
            repaired,
            format_ministral_prompt(copy.deepcopy(repaired), context_for(1)),
        )


class VisualFormattingTests(unittest.TestCase):
    def test_duplicate_registered_picture_ids_are_emitted_once(self) -> None:
        context = context_for(
            1,
            subject_definitions=(
                "<Subject 2> is Ben, referenced in <Picture 2>, "
                "<Picture 2>, and <Picture 2>."
            ),
            next_beat_id=None,
            current_beat_text="",
            later_beat_texts=[],
            beat_deadline_required=False,
        )
        malformed = result(
            "[Shot 1] A close-up shows Ben doing something.",
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted["detailed_description"]

        self.assertEqual(description.count("<Picture 2>"), 1)
        self.assertIn("Ben <Picture 2> doing something.", description)

    def test_multi_word_subject_gets_registered_picture_tag_once(self) -> None:
        context = context_for(
            2,
            subject_definitions=(
                "<Subject 1> is Mary Jane Watson, referenced in <Picture 4>."
            ),
        )
        malformed = result(
            "[Shot 2] Camera continues from the previous shot. Mary Jane Watson "
            "charges forward while an unnamed stranger watches.",
            completed=[2],
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted["detailed_description"]

        self.assertIn("Mary Jane Watson <Picture 4> charges forward", description)
        self.assertEqual(description.count("<Picture 4>"), 1)
        self.assertEqual(validate_ministral_prompt(formatted, context), [])

    def test_picture_only_definition_infers_subject_and_speaker(self) -> None:
        context = context_for(
            1,
            subject_definitions="<Picture 1> is Amy.",
        )
        malformed = result(
            "[Shot 1] Amy says: <d>[English] We need to move now.</d>",
            completed=[1],
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted["detailed_description"]

        self.assertIn("Amy <Picture 1> (S1) says:", description)
        self.assertEqual(validate_ministral_prompt(formatted, context), [])

    def test_stripped_unknown_picture_does_not_leave_spaced_apostrophe(self) -> None:
        malformed = result(
            "[Shot 1] Live-action, cinematic, a close framing highlights "
            "Amy <Picture 1>'s expression while she watches the door."
        )
        context = context_for(
            1,
            subject_definitions="",
            next_beat_id=None,
            current_beat_text="",
            later_beat_texts=[],
            beat_deadline_required=False,
            hard_cut_required=False,
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted["detailed_description"]

        self.assertIn("Amy's expression", description)
        self.assertNotIn("Amy 's", description)

    def test_trailing_parenthesized_timestamp_moves_before_its_action(self) -> None:
        malformed = result(
            "detailed_description: [Shot 17] Camera cuts to a "
            "new shot: Jack’s smirk fades into a mischievous grin as he hooks "
            "both thumbs onto his jeans (00:01.200)."
        )
        context = context_for(
            1,
            segment_number=17,
            subject_definitions="",
            next_beat_id=None,
            current_beat_text="",
            later_beat_texts=[],
            beat_deadline_required=False,
            hard_cut_required=False,
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted["detailed_description"]

        self.assertEqual(
            description,
            "[Shot 17] Camera continues from the previous shot.\nAt 00:01.200, "
            "Jack’s smirk fades into a mischievous grin as he hooks both "
            "thumbs onto his jeans.",
        )
        self.assertNotIn("(00:01.200)", description)
        self.assertEqual(
            formatted,
            format_ministral_prompt(copy.deepcopy(formatted), context),
        )

    def test_required_segment_boundary_uses_exact_hard_cut_opening(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark and Jill discuss the saucers. Mark (S1) "
            "asks: <d>[English] What is happening?</d> Jill (S2) answers: "
            "<d>[English] I don't know.</d>",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertTrue(description.startswith("[Shot 3] Camera cuts to a new shot:"))

    def test_non_hard_cut_converts_model_cut_to_continuation(self) -> None:
        malformed = result(
            "[Shot 2] Camera cuts to a new shot: Mark walks toward Jill."
        )

        description = format_ministral_prompt(
            malformed,
            context_for(2, hard_cut_required=False),
        )["detailed_description"]

        self.assertTrue(
            description.startswith(
                "[Shot 2] Camera continues from the previous shot."
            )
        )
        self.assertNotIn("Camera cuts to a new shot", description)

    def test_hard_cut_removes_conflicting_continuation_opening(self) -> None:
        malformed = result(
            "[Shot 3] Camera cuts to a new shot: At 00:00.000, camera continues "
            "from the previous shot. Mark and Jill face the saucers.",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertTrue(
            description.startswith("[Shot 3] Camera cuts to a new shot:")
        )
        self.assertIn("Mark <Picture 1> and Jill <Picture 2>", description)
        self.assertIn("face the saucers.", description)
        self.assertNotIn("continues from the previous shot", description.lower())

    def test_later_segment_does_not_require_a_local_timestamp(self) -> None:
        malformed = result(
            "[Shot 2] Live-action, cinematic, Mark and Jill walk through the park.",
            completed=[2],
        )

        formatted = format_ministral_prompt(malformed, context_for(2))
        issues = validate_ministral_prompt(formatted, context_for(2))

        self.assertFalse(any("after the first" in issue for issue in issues), issues)

    def test_later_segment_timestamp_satisfies_timestamp_requirement(self) -> None:
        formatted = format_ministral_prompt(
            result(
                "[Shot 2] At 00:01.200, Mark and Jill walk through the park.",
                completed=[2],
            ),
            context_for(2),
        )

        issues = validate_ministral_prompt(formatted, context_for(2))

        self.assertFalse(
            any("after the first" in issue for issue in issues),
            issues,
        )
        self.assertIn("At 00:01.200,", formatted["detailed_description"])

    def test_orphan_timestamp_fragments_are_removed(self) -> None:
        malformed = result(
            "[Shot 2] Camera continues from the previous shot At 00:05.200, and "
            "At 00:06.800, . Mark runs forward.",
            completed=[2],
        )

        description = format_ministral_prompt(
            malformed,
            context_for(2),
        )["detailed_description"]

        self.assertNotIn("At 00:05.200, and", description)
        self.assertNotIn("At 00:06.800, .", description)
        self.assertIn("Mark <Picture 1> runs forward.", description)

    def test_continuation_opening_uses_zero_timestamp_and_h3_sentence_form(self) -> None:
        formatted = format_ministral_prompt(
            result(
                "[Shot 2] Camera continues from the previous shot At 00:01.500, "
                "Mark walks through the park.",
                completed=[2],
            ),
            context_for(
                2,
                current_beat_text="Show Mark walking through the park.",
                next_beat_id=2,
                beat_deadline_required=False,
            ),
        )

        description = formatted["detailed_description"]
        self.assertTrue(
            description.startswith(
                "[Shot 2] Camera continues from the previous shot."
            )
        )
        self.assertNotIn("00:01.500", description)
        self.assertEqual(
            validate_ministral_prompt(
                formatted,
                context_for(
                    2,
                    current_beat_text="Show Mark walking through the park.",
                    next_beat_id=2,
                    beat_deadline_required=False,
                ),
            ),
            [],
        )

    def test_each_later_timestamp_starts_on_its_own_line(self) -> None:
        formatted = format_ministral_prompt(
            result(
                "[Shot 2] At 00:01.000, the camera moves toward the doorway. "
                "At 00:03.500, the camera cuts to the hallway.",
                completed=[2],
            ),
            context_for(2),
        )

        description = formatted["detailed_description"]
        self.assertIn(
            "At 00:01.000, the camera moves toward the doorway.\n"
            "At 00:03.500, the camera cuts to the hallway.",
            description,
        )

    def test_shot_number_opening_timestamp_extra_shot_and_alignment_are_cleaned(self) -> None:
        malformed = result(
            "How the reference pictures align with the target video — <Picture 1> aligns "
            "with 0.00 seconds. [Shot 9] At 00:00.000, live-action saucers fly overhead. "
            "[Shot 10] At 00:03.000, the saucers continue across the sky.",
            completed=[2],
        )

        repaired = format_ministral_prompt(malformed, context_for(2))
        description = repaired["detailed_description"]

        self.assertTrue(description.startswith("[Shot 2]"))
        self.assertEqual(re.findall(r"\[Shot\s+\d+\]", description), ["[Shot 2]"])
        self.assertIn("At 00:00.000,", description)
        self.assertNotIn("reference pictures align", description.lower())

    def test_stacked_camera_labels_become_natural_camera_prose(self) -> None:
        malformed = result(
            "[Shot 2] Live-action, cinematic, several flying saucers cross overhead. "
            "Camera Motion: Push In. Amplitude: small. Speed: slow.",
            completed=[2],
        )

        description = format_ministral_prompt(malformed, context_for(2))[
            "detailed_description"
        ]

        self.assertRegex(
            description.lower(),
            r"camera push(?:es|ing) in with small amplitude at slow speed",
        )
        self.assertNotRegex(description.lower(), r"camera motion\s*:|amplitude\s*:|speed\s*:")

    def test_unknown_subject_and_picture_tags_are_removed_but_known_tags_survive(self) -> None:
        malformed = result(
            "[Shot 1] Live-action, cinematic, Mark <Subject 1> from <Picture 1> and Jill "
            "<Subject 2> from <Picture 2> stand with their son <Subject 3> from <Picture 3> "
            "and the rest of Mark's family.",
            completed=[1],
        )

        description = format_ministral_prompt(malformed, context_for(1))[
            "detailed_description"
        ]

        self.assertIn("Mark <Picture 1>", description)
        self.assertIn("<Picture 1>", description)
        self.assertIn("Jill <Picture 2>", description)
        self.assertIn("<Picture 2>", description)
        self.assertNotIn("<Subject 3>", description)
        self.assertNotIn("<Picture 3>", description)
        self.assertIn("son", description)

    def test_visible_sign_text_is_quoted_without_changing_its_words(self) -> None:
        malformed = result(
            "[Shot 1] Live-action, cinematic, Mark and Jill wait with Mark's family beside "
            "a sign reading ALIEN INVASION while park visitors pass.",
            completed=[1],
        )

        description = format_ministral_prompt(malformed, context_for(1))[
            "detailed_description"
        ]

        self.assertIn('sign reading "ALIEN INVASION"', description)


class DialogueFormattingTests(unittest.TestCase):
    def test_segment_two_wrong_ids_and_joint_id_are_remapped_without_rewording(self) -> None:
        malformed = result(
            "[Shot 2] Live-action, cinematic, saucers fly overhead as Mark (S3) tells Jill "
            "(S4): <d>Those can't be airplanes!</d> Mark and Jill (S3,S4) shout together: "
            "<d>[English] Get down, now!</d>",
            completed=[2],
        )

        description = format_ministral_prompt(malformed, context_for(2))[
            "detailed_description"
        ]

        self.assertIn("Mark <Picture 1> (S1)", description)
        self.assertIn("Jill <Picture 2> (S2)", description)
        self.assertIn("(S1,S2)", description)
        self.assertNotRegex(description, r"\(S[34](?:,S[34])?\)")
        self.assertIn("<d>[English] Those can't be airplanes!</d>", description)
        self.assertIn("<d>[English] Get down, now!</d>", description)

    def test_segment_three_later_id_drift_is_mapped_by_identity(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark (S5) asks Jill (S6): "
            "<d>Where did those saucers come from?</d> Jill (S6) answers Mark (S5): "
            "<d>They appeared above the rides.</d> Mark and Jill (S5,S6) keep talking.",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertNotRegex(description, r"\bS[56]\b")
        self.assertIn("Mark <Picture 1> (S1)", description)
        self.assertIn("Jill <Picture 2> (S2)", description)
        self.assertIn("(S1,S2)", description)
        self.assertIn("<d>[English] Where did those saucers come from?</d>", description)
        self.assertIn("<d>[English] They appeared above the rides.</d>", description)

    def test_mark_and_jill_receive_stable_speaker_ids(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark (S2) turns to Jill (S1). Mark (S2) says: "
            "<d>[English] What is happening?</d> Jill (S1) answers: "
            "<d>[English] I don't know!</d>",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertNotIn("Mark (S2)", description)
        self.assertNotIn("Jill (S1)", description)
        self.assertIn("Mark (S1)", description)
        self.assertIn("Jill (S2)", description)

    def test_dialogue_wrappers_and_english_tags_are_repaired_verbatim(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark (S2): <d>What is happening?!</d> "
            "Jill (S1): <d>I don't know\u2014look up!</d>",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertIn("Mark <Picture 1> (S1)", description)
        self.assertIn("Jill <Picture 2> (S2)", description)
        self.assertIn("<d>[English] What is happening?!</d>", description)
        self.assertIn("<d>[English] I don't know, look up!</d>", description)
        self.assertEqual(description.count("What is happening?!"), 1)
        self.assertEqual(description.count("I don't know, look up!"), 1)

    def test_compound_speaker_id_is_normalized(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark and Jill (S2, S1) shout together: "
            "<d>[English] Run!</d> as they try to understand the chaos.",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertIn("(S1,S2)", description)
        self.assertNotIn("(S2, S1)", description)

    def test_voiceover_uses_exact_phrase_and_closed_lips_clause(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark (S1) narrates: "
            "<d>I knew something was wrong.</d> while he watches Jill and the sky.",
            completed=[3],
        )

        description = format_ministral_prompt(malformed, context_for(3))[
            "detailed_description"
        ]

        self.assertIn("says in an off-screen voiceover", description)
        self.assertIn("<d>[English] I knew something was wrong.</d>", description)
        self.assertRegex(
            description,
            r"I knew something was wrong\.</d> while (?:Mark's|his) lips remain completely closed",
        )


class AudioFormattingTests(unittest.TestCase):
    def test_soundscape_removes_dialogue_music_and_language_suffix(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark (S1) says: "
            "<d>[English] What is happening?</d> Jill (S2) says: "
            "<d>[English] I don't know.</d>",
            soundscape=(
                'Crowds murmur. Mark says "What is happening?" Sparse strings play. '
                "Footsteps scrape the pavement. All language is in English."
            ),
            completed=[3],
        )

        soundscape = format_ministral_prompt(malformed, context_for(3))["overall_soundscape"]

        self.assertIn("Crowds murmur", soundscape)
        self.assertIn("Footsteps scrape", soundscape)
        self.assertNotIn("What is happening", soundscape)
        self.assertNotRegex(soundscape.lower(), r"strings|music|language is in english")
        sentences = [piece for piece in re.split(r"(?<=[.!?])\s+", soundscape) if piece]
        self.assertLessEqual(len(sentences), 4)

    def test_music_none_variants_are_canonical_na(self) -> None:
        for value in ("none", "None.", "n/a", "N.A.", "no non-diegetic music"):
            with self.subTest(value=value):
                malformed = result(
                    "[Shot 2] Live-action, cinematic, flying saucers cross overhead.",
                    music=value,
                    completed=[2],
                )
                repaired = format_ministral_prompt(malformed, context_for(2))
                self.assertEqual(repaired["non_diegetic_music"], "N/A")

    def test_music_is_limited_to_three_sentences(self) -> None:
        malformed = result(
            "[Shot 2] At 00:01.000, live-action, cinematic, flying saucers cross overhead.",
            music=(
                "Low strings sustain at a slow tempo. Brass pulses twice. Drums enter at a "
                "steady rhythm. The instruments fade out. A final cymbal rings."
            ),
            completed=[2],
        )

        music = format_ministral_prompt(malformed, context_for(2))["non_diegetic_music"]
        sentences = [piece for piece in re.split(r"(?<=[.!?])\s+", music) if piece]
        self.assertLessEqual(len(sentences), 3)

    def test_na_soundscape_is_rejected_unless_silence_is_allowed(self) -> None:
        prompt = result(
            "[Shot 2] At 00:01.000, live-action, cinematic, flying saucers cross overhead.",
            soundscape="N/A",
            completed=[2],
        )

        self.assertTrue(validate_ministral_prompt(prompt, context_for(2)))
        self.assertEqual(
            validate_ministral_prompt(prompt, context_for(2, allow_silence=True)),
            [],
        )


class CompletionMetadataTests(unittest.TestCase):
    def test_segment_one_requires_b001_completion_report(self) -> None:
        prompt = result(
            "[Shot 1] Live-action, cinematic, Mark and Jill stand together in "
            "the theme park.",
            completed=[],
        )

        formatted = format_ministral_prompt(prompt, context_for(1))

        self.assertTrue(any(
            issue.startswith("Segment 1 must complete and report active beat B001")
            for issue in validate_ministral_prompt(formatted, context_for(1))
        ))

    def test_completion_ids_are_normalized_to_consecutive_beats(self) -> None:
        malformed = result(
            "[Shot 3] Live-action, cinematic, Mark (S1) asks Jill (S2): "
            "<d>[English] What is happening?</d> Jill answers: "
            "<d>[English] I don't know!</d>",
            completed=[1, "B003", "3", 4, 99],
        )

        repaired = format_ministral_prompt(malformed, context_for(3))

        self.assertEqual(repaired["completed_beat_ids"], [3, 4])

    def test_completion_metadata_is_removed_from_rendered_description(self) -> None:
        malformed = result(
            "[Shot 2] At 00:01.000, live-action, cinematic, flying saucers cross overhead. "
            "completed_beat_ids: [2]",
            completed=[2],
        )

        repaired = format_ministral_prompt(malformed, context_for(2))

        self.assertNotIn(
            "completed_beat_ids",
            repaired["detailed_description"],
        )
        self.assertEqual(repaired["completed_beat_ids"], [2])

    def test_incomplete_current_beat_may_report_no_completion(self) -> None:
        prompt = result(
            "[Shot 4] Live-action, cinematic, Mark's family begins running as the saucers "
            "descend toward them, but they remain on the ground when the shot ends.",
            completed=[],
        )

        repaired = format_ministral_prompt(prompt, context_for(4, beat_deadline_required=False))

        self.assertEqual(repaired["completed_beat_ids"], [])


class BeatFixtureTests(unittest.TestCase):
    def assert_valid_after_formatting(self, malformed: dict, beat_number: int) -> dict:
        formatted = format_ministral_prompt(malformed, context_for(beat_number))
        self.assertEqual(validate_ministral_prompt(formatted, context_for(beat_number)), [])
        return formatted

    def test_b001_malformed_and_valid_fixtures(self) -> None:
        malformed = result(
            "detailed_description: [Shot 7] At 00:00.000, Live-action, "
            "cinematic, Mark <Subject 1>, Jill <Subject 2>, and Mark's family <Subject 3> "
            "stand together amid the theme park crowd.",
            music="none",
            completed=["B001"],
        )
        valid = result(
            "[Shot 1] Live-action, cinematic, a medium-wide shot shows Mark <Picture 1>, "
            "Jill <Picture 2>, and Mark's family enjoying the busy theme park together.",
            completed=[1],
        )

        self.assert_valid_after_formatting(malformed, 1)
        self.assertEqual(format_ministral_prompt(valid, context_for(1)), valid)

    def test_b002_malformed_and_valid_fixtures(self) -> None:
        malformed = result(
            "[Shot 8] At 00:01.000, several flying saucers fly overhead above the park. "
            "Camera Motion: Tilt Up. Amplitude: large. Speed: fast.",
            music="N.A.",
            completed=["B002"],
        )
        valid = result(
            "[Shot 2] Camera continues from the previous shot. Live-action, cinematic, "
            "several flying saucers fly overhead above the "
            "theme park as the camera tilts up with large amplitude at fast speed.",
            completed=[2],
        )

        self.assert_valid_after_formatting(malformed, 2)
        self.assertEqual(format_ministral_prompt(valid, context_for(2)), valid)

    def test_b003_malformed_dialogue_fixture_preserves_every_spoken_character(self) -> None:
        malformed = result(
            "[Shot 11] At 00:01.000, Live-action, cinematic, Mark (S2): "
            "<d>What is happening?!</d> Jill (S1): <d>I don't know—those things aren't planes.</d> "
            "They keep talking and trying to understand the saucers overhead.",
            soundscape=(
                'Crowds gasp. Mark says "What is happening?!" Footsteps shuffle. '
                "All language is in English."
            ),
            completed=["B003"],
        )
        valid = result(
            "[Shot 3] Camera cuts to a new shot: Live-action, cinematic, "
            "Mark <Picture 1> turns to Jill <Picture 2> as they try to "
            "understand the saucers. Mark (S1) asks: <d>[English] What is happening?!</d> "
            "Jill (S2) answers: <d>[English] I don't know, those things aren't planes.</d>",
            soundscape="Crowds gasp while footsteps shuffle across the pavement.",
            completed=[3],
        )

        formatted = self.assert_valid_after_formatting(malformed, 3)
        description = formatted["detailed_description"]
        self.assertIn("<d>[English] What is happening?!</d>", description)
        self.assertIn("<d>[English] I don't know, those things aren't planes.</d>", description)
        self.assertEqual(format_ministral_prompt(valid, context_for(3)), valid)

    def test_b004_malformed_and_valid_fixtures(self) -> None:
        malformed = result(
            "[Shot 12] At 00:01.000, Live-action, cinematic, Mark's family run away while "
            "the flying saucers seize and lift the whole family from the ground, carrying them "
            "into the craft as Mark and Jill watch the now-empty pavement. [Shot 13] The "
            "abduction is visibly complete.",
            soundscape="Running footsteps and frightened gasps give way to an electronic hum.",
            completed=["B004", 5],
        )
        valid = result(
            "[Shot 4] Camera continues from the previous shot. Live-action, cinematic, "
            "Mark <Picture 1>'s family run from the descending saucers. "
            "Beams seize and lift them from the ground, carrying the entire family into the "
            "craft until Mark and Jill <Picture 2> stand beside empty pavement "
            "after the completed abduction.",
            soundscape="Running footsteps and frightened gasps give way to a low electronic hum.",
            completed=[4],
        )

        self.assert_valid_after_formatting(malformed, 4)
        self.assertEqual(format_ministral_prompt(valid, context_for(4)), valid)

    def test_validation_flags_missing_story_content_for_last_resort_requery(self) -> None:
        content_missing = result(
            "[Shot 4] Live-action, cinematic, Mark and Jill look at the sky in the theme park.",
            completed=[4],
        )

        errors = validate_ministral_prompt(content_missing, context_for(4))

        self.assertTrue(errors)
        self.assertTrue(all(isinstance(error, str) and error for error in errors))


if __name__ == "__main__":
    unittest.main()
