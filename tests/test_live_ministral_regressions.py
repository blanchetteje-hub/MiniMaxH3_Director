"""Regression tests distilled from malformed live Ministral responses.

These tests intentionally exercise only the deterministic formatter and its
Python validator.  They must never import the runtime scheduler or contact LM
Studio/ComfyUI.
"""

from __future__ import annotations

import re
import unittest

import ministral_formatter as formatter
from ministral_formatter import format_ministral_prompt, validate_ministral_prompt


DESCRIPTION = "integrated_multimodal_description"
SOUNDSCAPE = "overall_soundscape"
MUSIC = "non_diegetic_music"
COMPLETIONS = "completed_beat_ids"

SUBJECT_DEFINITIONS = (
    "<Subject 1> is Mark, a 40-year-old man referenced in <Picture 1>.\n"
    "<Subject 2> is Jill, a 35-year-old woman referenced in <Picture 2>."
)


def context_for(segment_number: int = 3, **overrides: object) -> dict:
    context = {
        "segment_number": segment_number,
        "segment_duration": 6.0,
        "subject_definitions": SUBJECT_DEFINITIONS,
        "known_subjects": {"Mark": 1, "Jill": 2},
        "completed_beat_ids": list(range(1, segment_number)),
        "next_beat_id": segment_number,
        "current_beat_text": (
            "Show Mark and Jill talking and trying to figure out what is happening."
        ),
        "later_beat_texts": [],
        "beat_deadline_required": False,
        "allow_silence": False,
        "hard_cut_required": False,
    }
    context.update(overrides)
    return context


def response(
    description: str,
    *,
    soundscape: str = "Crowds murmur while footsteps cross the pavement.",
    music: str = "N/A",
    completed: list[int] | None = None,
) -> dict:
    return {
        DESCRIPTION: description,
        SOUNDSCAPE: soundscape,
        MUSIC: music,
        COMPLETIONS: [] if completed is None else completed,
    }


class LiveDialogueRegressionTests(unittest.TestCase):
    def test_parenthetical_subject_annotation_is_removed(self) -> None:
        context = context_for(
            1,
            subject_definitions=(
                "<Subject 1> is Connie, referenced in <Picture 1>."
            ),
            current_beat_text="Show Connie walking down the road.",
            next_beat_id=1,
            beat_deadline_required=False,
        )
        for annotation in ("(Subject 1)", "(subject 9)"):
            with self.subTest(annotation=annotation):
                malformed = response(
                    f"[Shot 1] <Subject 1> Connie {annotation} walks down the road."
                )

                formatted = format_ministral_prompt(malformed, context)
                description = formatted[DESCRIPTION]

                self.assertIn("<Subject 1> Connie", description)
                self.assertNotRegex(description, r"(?i)\(\s*Subject\s+\d+\s*\)")
                self.assertEqual(validate_ministral_prompt(formatted, context), [])

    def test_visual_subject_definitions_do_not_use_speaker_ids(self) -> None:
        context = context_for(
            1,
            subject_definitions=(
                "<Subject 1> is Jim, referenced in <Picture 1>.\n"
                "<Subject 2> is Frank, referenced in <Picture 2>."
            ),
            current_beat_text="Show Jim and Frank walking down the road.",
            next_beat_id=1,
            beat_deadline_required=False,
        )
        malformed = response(
            "[Shot 1] On the road are two men—Jim (S2) and Frank (S1)—walking "
            "down the road."
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted[DESCRIPTION]

        self.assertNotIn("—", description)
        self.assertNotRegex(description, r"\(S\d+\)")
        self.assertIn("<Subject 1> Jim", description)
        self.assertIn("<Subject 2> Frank", description)
        self.assertEqual(validate_ministral_prompt(formatted, context), [])

    def test_actual_jim_dialogue_keeps_canonical_speaker_id(self) -> None:
        context = context_for(
            1,
            subject_definitions=(
                "<Subject 1> is Jim, referenced in <Picture 1>.\n"
                "<Subject 2> is Frank, referenced in <Picture 2>."
            ),
            current_beat_text="Show Jim speaking to Frank.",
            next_beat_id=1,
            beat_deadline_required=False,
        )
        malformed = response(
            "[Shot 1] Jim (S8) says: <d>Keep walking.</d> while Frank listens."
        )

        description = format_ministral_prompt(malformed, context)[DESCRIPTION]

        self.assertIn("Jim <Picture 1> (S1) says:", description)
        self.assertIn("<d>[English] Keep walking.</d>", description)

    def test_missing_dialogue_speaker_id_is_inserted_from_subject_definition(self) -> None:
        context = context_for(
            1,
            subject_definitions=(
                "<Subject 1> is Jim, referenced in <Picture 1>.\n"
                "<Subject 2> is Frank, referenced in <Picture 2>."
            ),
            current_beat_text="Show Jim speaking to Frank.",
            next_beat_id=1,
            beat_deadline_required=False,
        )
        malformed = response(
            "[Shot 1] Jim <Picture 1> says: <d>[English] Keep walking.</d> "
            "Frank watches him."
        )

        formatted = format_ministral_prompt(malformed, context)
        description = formatted[DESCRIPTION]

        self.assertIn("Jim <Picture 1> (S1) says:", description)
        self.assertNotIn("Dialogue block is missing an attributed speaker ID.", " ".join(
            validate_ministral_prompt(formatted, context)
        ))

    def test_subject_keeps_multiple_picture_references(self) -> None:
        context = context_for(
            1,
            subject_definitions=(
                "<Subject 1> is Mark, referenced in <Picture 1> and "
                "<Picture 2>."
            ),
            current_beat_text="Show Mark walking.",
            next_beat_id=1,
            beat_deadline_required=False,
        )
        formatted = format_ministral_prompt(
            response(
                "[Shot 1] Mark <Picture 1> walks down the road."
            ),
            context,
        )

        description = formatted[DESCRIPTION]
        self.assertIn("Mark <Picture 1> <Picture 2>", description)

    def test_delivery_tags_move_outside_dialogue_without_rewriting_words(self) -> None:
        cases = (
            ("Tense", "Those aren't airplanes!", "Those aren't airplanes!"),
            ("Sharp breath", "Mark, look up\u2014now!", "Mark, look up, now!"),
            ("Panicked", "Where did they come from?", "Where did they come from?"),
            ("Laughs", "This cannot be real.", "This cannot be real."),
        )

        for delivery, spoken_words, expected_words in cases:
            with self.subTest(delivery=delivery):
                malformed = response(
                    f"[Shot 3] Mark (S5) says: <d>[{delivery}] [English] "
                    f"{spoken_words}</d> Jill watches him."
                )

                description = format_ministral_prompt(
                    malformed, context_for(3)
                )[DESCRIPTION]

                block = f"<d>[English] {expected_words}</d>"
                self.assertIn(block, description)
                self.assertEqual(description.count(expected_words), 1)
                self.assertNotIn(f"<d>[{delivery}]", description)
                before_dialogue = description[: description.index(block)].lower()
                self.assertIn(delivery.lower(), before_dialogue)

        def test_subject_maps_do_not_fabricate_mark_or_jill(self):
            names, subjects, pictures = formatter._subject_maps({
                "subject_definitions": (
                    "<Subject 7> is Connie, referenced in <Picture 4>."
                )
            })

            self.assertEqual(names, {"Connie": 7})
            self.assertEqual(subjects, {7})
            self.assertEqual(pictures, {4})

    def test_redundant_period_after_dialogue_close_is_removed(self) -> None:
        spoken_words = "We have to get out of here!"
        malformed = response(
            "[Shot 3] Mark (S5) shouts: "
            f"<d>[English] {spoken_words}</d>. Jill turns toward him."
        )

        description = format_ministral_prompt(malformed, context_for(3))[DESCRIPTION]

        self.assertIn(f"<d>[English] {spoken_words}</d>", description)
        self.assertNotIn("</d>.", description)
        self.assertEqual(description.count(spoken_words), 1)

    def test_arbitrary_sequential_speaker_drift_is_identity_mapped(self) -> None:
        for segment, mark_id, jill_id in ((4, 7, 8), (11, 21, 22)):
            with self.subTest(segment=segment, ids=(mark_id, jill_id)):
                malformed = response(
                    f"[Shot {segment}] Mark (S{mark_id}) asks Jill (S{jill_id}): "
                    "<d>What is happening?</d> "
                    f"Jill (S{jill_id}) replies to Mark (S{mark_id}): "
                    "<d>Those objects are following us.</d> "
                    f"Mark and Jill (S{mark_id},S{jill_id}) shout together: "
                    "<d>Run!</d>"
                )

                description = format_ministral_prompt(
                    malformed, context_for(segment)
                )[DESCRIPTION]

                self.assertRegex(description, r"Mark(?: <Subject 1>)? \(S1\)")
                self.assertRegex(description, r"Jill(?: <Subject 2>)? \(S2\)")
                self.assertRegex(
                    description,
                    r"(?:<Subject 1> )?Mark and (?:<Subject 2> )?Jill \(S1,S2\)",
                )
                self.assertNotRegex(
                    description,
                    rf"\bS(?:{mark_id}|{jill_id})\b",
                )
                self.assertIn("<d>[English] What is happening?</d>", description)
                self.assertIn(
                    "<d>[English] Those objects are following us.</d>", description
                )
                self.assertIn("<d>[English] Run!</d>", description)

    def test_prefix_positioned_speaker_drift_is_identity_mapped(self) -> None:
        malformed = response(
            "[Shot 3] (S5) Mark says: <d>Look at the sky!</d> "
            "(S6) Jill replies: <d>I see them.</d> "
            "(S5,S6) Mark and Jill shout together: <d>Run!</d>"
        )

        description = format_ministral_prompt(malformed, context_for(3))[DESCRIPTION]

        self.assertRegex(description, r"Mark(?: <Subject 1>)? \(S1\)")
        self.assertRegex(description, r"Jill(?: <Subject 2>)? \(S2\)")
        self.assertRegex(
            description,
            r"(?:<Subject 1> )?Mark and (?:<Subject 2> )?Jill \(S1,S2\)",
        )
        self.assertNotRegex(description, r"\bS[56]\b")

    def test_speaking_undefined_son_requires_content_correction(self) -> None:
        malformed = response(
            "[Shot 3] Mark's unidentified son shouts: "
            "<d>[English] They're right above us!</d> while Mark and Jill turn around."
        )

        formatted = format_ministral_prompt(malformed, context_for(3))
        issues = validate_ministral_prompt(formatted, context_for(3))

        self.assertTrue(issues)
        self.assertTrue(
            any(re.search(r"(?i)(son|undefined|unknown|stable speaker|S3)", issue) for issue in issues),
            issues,
        )

    def test_stray_closed_lips_clause_without_voiceover_is_rejected(self) -> None:
        malformed = response(
            "[Shot 3] Jill (S6) says: <d>[English] I can see them now.</d> "
            "while her lips remain completely closed as Mark watches her."
        )

        formatted = format_ministral_prompt(malformed, context_for(3))
        issues = validate_ministral_prompt(formatted, context_for(3))

        self.assertTrue(issues)
        self.assertTrue(
            any(re.search(r"(?i)(lips|voiceover)", issue) for issue in issues), issues
        )

    def test_quoted_spoken_line_without_dialogue_tags_is_rejected(self) -> None:
        malformed = response(
            '[Shot 3] Mark (S5) says, "Those are not airplanes!" as Jill watches.'
        )

        formatted = format_ministral_prompt(malformed, context_for(3))
        issues = validate_ministral_prompt(formatted, context_for(3))

        self.assertTrue(issues)
        self.assertTrue(any(re.search(r"(?i)(dialogue|<d>|spoken)", issue) for issue in issues), issues)

    def test_orphan_dialogue_tag_is_rejected(self) -> None:
        malformed = response(
            "[Shot 3] Mark (S5) says: <d>[English] Look out! Jill turns toward him."
        )

        formatted = format_ministral_prompt(malformed, context_for(3))
        issues = validate_ministral_prompt(formatted, context_for(3))

        self.assertTrue(any("unbalanced" in issue.lower() for issue in issues), issues)

    def test_guard_dialogue_does_not_satisfy_mark_and_jill_exchange(self) -> None:
        context = context_for(3, beat_deadline_required=True, next_beat_id=3)
        malformed = response(
            "[Shot 3] Mark and Jill silently watch two security guards. "
            "A guard (S5) shouts: <d>[English] Clear the midway!</d> "
            "Another guard (S6) replies: <d>[English] Move toward the exit!</d>",
            completed=[3],
        )

        formatted = format_ministral_prompt(malformed, context)
        issues = validate_ministral_prompt(formatted, context)

        self.assertTrue(issues)
        self.assertTrue(
            any(re.search(r"(?i)(Mark/Jill|exchange|talk|attributed)", issue) for issue in issues),
            issues,
        )


class LiveVisualFormattingRegressionTests(unittest.TestCase):
    def test_decimal_seconds_opening_timestamp_is_normalized(self) -> None:
        malformed = response(
            "[Shot 2] At 0.00 seconds, several flying saucers cross overhead."
        )

        description = format_ministral_prompt(malformed, context_for(2))[DESCRIPTION]

        self.assertTrue(description.startswith("[Shot 2]"))
        self.assertIn("At 00:00.000 seconds,", description)

    def test_markdown_emphasis_is_stripped_from_every_prompt_field(self) -> None:
        malformed = response(
            "[Shot 2] **Live-action**, *cinematic*, several saucers fly "
            "**overhead** above the park.",
            soundscape="*Crowds murmur* while **footsteps scrape** the pavement.",
            music="**N/A**",
            completed=[2],
        )

        formatted = format_ministral_prompt(
            malformed,
            context_for(
                2,
                current_beat_text="Show flying saucers flying overhead.",
                next_beat_id=2,
            ),
        )

        for field in (DESCRIPTION, SOUNDSCAPE, MUSIC):
            self.assertNotIn("*", formatted[field], (field, formatted[field]))
        self.assertIn("Live-action, cinematic", formatted[DESCRIPTION])
        self.assertEqual(formatted[MUSIC], "N/A")

    def test_live_camera_fragments_are_naturalized(self) -> None:
        cases = (
            (
                "Arc Shot around Mark and Jill as they stare upward.",
                    r"(?i)camera moves in an arc around (?:<Subject 1> )?Mark and "
                    r"(?:<Subject 2> )?Jill",
                r"(?i)\bArc Shot\b",
            ),
            (
                "Static medium close-up of Jill watching the lights.",
                    r"(?i)camera holds a static medium close-up of (?:<Subject 2> )?Jill",
                r"(?i)(?:^|[.!?]\s+)Static medium close-up",
            ),
            (
                "Tilt Down from the saucers to the fleeing crowd.",
                r"(?i)camera tilts down from the saucers",
                r"(?i)\bTilt Down\b",
            ),
        )

        for fragment, expected, forbidden in cases:
            with self.subTest(fragment=fragment):
                malformed = response(f"[Shot 2] Live-action, cinematic. {fragment}")
                description = format_ministral_prompt(
                    malformed,
                    context_for(
                        2,
                        current_beat_text="Show flying saucers flying overhead.",
                        next_beat_id=2,
                    ),
                )[DESCRIPTION]

                self.assertRegex(description, expected)
                self.assertNotRegex(description, forbidden)

    def test_unidentified_annotations_are_removed(self) -> None:
        malformed = response(
            "[Shot 1] Mark (unidentified) and Jill (unidentified) stand beside "
            "Mark's son (unidentified) and the rest of the family."
        )

        description = format_ministral_prompt(
            malformed,
            context_for(
                1,
                current_beat_text="Show Mark, Jill, and his family.",
                next_beat_id=1,
            ),
        )[DESCRIPTION]

        self.assertNotRegex(description, r"(?i)\(\s*unidentified\s*\)")
        self.assertIn("Mark's son", description)


class LiveSoundscapeRegressionTests(unittest.TestCase):
    def test_quoted_dialogue_pa_and_diegetic_music_are_removed(self) -> None:
        malformed = response(
            "[Shot 2] At 00:01.000, several saucers fly overhead above the theme park.",
            soundscape=(
                "Crowds gasp and shoes scrape the pavement. "
                'A voice says, "Please proceed to the nearest exit." '
                'The PA announcement "Remain calm" echoes across the midway. '
                "Diegetic carnival music plays from the carousel speakers. "
                "A low mechanical hum grows overhead."
            ),
            completed=[2],
        )
        context = context_for(
            2,
            current_beat_text="Show flying saucers flying overhead.",
            next_beat_id=2,
        )

        formatted = format_ministral_prompt(malformed, context)
        soundscape = formatted[SOUNDSCAPE]

        self.assertIn("Crowds gasp", soundscape)
        self.assertIn("mechanical hum", soundscape)
        self.assertNotIn("Please proceed", soundscape)
        self.assertNotIn("Remain calm", soundscape)
        self.assertNotRegex(soundscape, r"(?i)(PA announcement|carnival music|carousel speakers)")
        self.assertEqual(validate_ministral_prompt(formatted, context), [])

    def test_mixed_spoken_line_and_instrument_sentence_is_removed_whole(self) -> None:
        malformed = response(
            "[Shot 4] Mark's family runs while Mark and Jill watch.",
            soundscape=(
                "Footsteps pound across the pavement. "
                'Jill shouts "Run!" while brass and violins play. '
                "Frightened crowds gasp nearby."
            ),
        )

        soundscape = format_ministral_prompt(malformed, context_for(4))[SOUNDSCAPE]

        self.assertIn("Footsteps pound", soundscape)
        self.assertIn("crowds gasp", soundscape)
        self.assertNotRegex(soundscape, r"(?i)(Run!|Jill shouts|brass|violins)")


class LiveBeatFourSemanticRegressionTests(unittest.TestCase):
    def _b4_context(self) -> dict:
        return context_for(
            4,
            completed_beat_ids=[1, 2, 3],
            next_beat_id=4,
            current_beat_text=(
                "Show the saucers abducting Mark's family as they run away."
            ),
            beat_deadline_required=True,
            later_beat_texts=[],
        )

    def test_unseen_family_does_not_satisfy_visible_b4_abduction(self) -> None:
        malformed = response(
            "[Shot 4] Mark and Jill look toward a building while Mark's family "
            "remains unseen behind it. Off-screen figures run as a beam lifts them "
            "into the craft, leaving empty pavement beyond the building.",
            completed=[4],
        )

        formatted = format_ministral_prompt(malformed, self._b4_context())
        issues = validate_ministral_prompt(formatted, self._b4_context())

        self.assertTrue(issues, "An unseen/off-screen abduction must require an LLM correction.")
        self.assertTrue(
            any(re.search(r"(?i)(visible|unseen|off-screen|family)", issue) for issue in issues),
            issues,
        )

    def test_frozen_family_does_not_satisfy_running_away_requirement(self) -> None:
        malformed = response(
            "[Shot 4] Mark's family stands frozen and motionless beneath the saucers. "
            "A beam seizes and lifts the whole family into the craft until Mark and "
            "Jill face the empty pavement after the completed abduction.",
            completed=[4],
        )

        formatted = format_ministral_prompt(malformed, self._b4_context())
        issues = validate_ministral_prompt(formatted, self._b4_context())

        self.assertTrue(issues, "A frozen family must not count as visibly running away.")
        self.assertTrue(
            any(re.search(r"(?i)(run|flee|frozen|motionless)", issue) for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
