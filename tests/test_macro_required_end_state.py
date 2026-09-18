import unittest

import minimax


class MacroRequiredEndStateTests(unittest.TestCase):
    def make_phase(self, events):
        return {
            "phase_number": 1,
            "beat_start": 1,
            "beat_end": 5,
            "narrative_purpose": "Setup",
            "broad_progression": "Establish the situation.",
            "characters_introduced": ["Amy"],
            "location": "Basement",
            "required_end_state": "The action is complete.",
            "required_events": events,
        }

    def test_macro_schema_accepts_atomic_required_events(self):
        parsed = minimax.parse_beat_arc_plan(
            {"phases": [self.make_phase([
                {"id": "E1", "event": "Amy enters the basement."},
                {"id": "E2", "event": "Amy locks the door."},
            ])]},
            5,
        )
        self.assertEqual(
            parsed["phases"][0]["required_events"][1],
            {"id": "E2", "event": "Amy locks the door."},
        )

    def test_required_event_state_effects_are_preserved_and_applied(self):
        arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 2,
                "narrative_purpose": "Resolution",
                "broad_progression": "Defeat the pursuers.",
                "characters_introduced": ["Amy"],
                "location": "House",
                "required_end_state": "The pursuit is over.",
                "required_events": [{
                    "id": "E1",
                    "event": "All active pursuers are defeated.",
                    "state_effects": {
                        "story": {
                            "terminal_states": {"active_pursuit": True},
                        },
                    },
                }],
            }],
        }
        parsed = minimax.parse_beat_arc_plan(arc, 2)
        event = parsed["phases"][0]["required_events"][0]
        state = minimax._apply_required_event_state_effects(
            minimax.new_beat_canonical_state(), [event]
        )
        self.assertTrue(state["story"]["terminal_states"]["active_pursuit"])
        changed = minimax.apply_state_patch(
            state,
            {"story": {"terminal_states": {"active_pursuit": False}}},
        )
        self.assertTrue(changed["story"]["terminal_states"]["active_pursuit"])

    def test_required_event_threat_effects_require_object_records(self):
        with self.assertRaisesRegex(ValueError, "state patch entity threats.zombies"):
            minimax.parse_beat_arc_plan({
                "phases": [self.make_phase([{
                    "id": "E1",
                    "event": "The zombies are defeated.",
                    "beat_number": 1,
                    "state_effects": {
                        "threats": {"zombies": "dead"},
                    },
                }])],
            }, 5)

    def test_macro_response_schema_requires_required_events(self):
        schema = minimax.build_beat_arc_response_format(5)["json_schema"]["schema"]
        phase_schema = schema["properties"]["phases"]["items"]
        self.assertIn("required_events", phase_schema["required"])

    def test_macro_schema_rejects_duplicate_required_event_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate macro required event ID"):
            minimax.parse_beat_arc_plan(
                {"phases": [self.make_phase([
                    {"id": "E1", "event": "Amy enters the basement."},
                    {"id": "E1", "event": "Amy locks the door."},
                ])]},
                5,
            )

    def test_required_events_are_in_generation_prompt(self):
        phase = self.make_phase([
            {"id": "E1", "event": "Amy enters the basement."},
            {"id": "E2", "event": "Amy locks the door."},
        ])
        prompt = minimax.build_beat_generation_messages(
            "Amy enters and locks the basement.",
            5,
            macro_arc={"phases": [phase]},
            current_phase=phase,
        )[1]["content"]
        self.assertIn("REQUIRED EVENTS FOR THIS PHASE", prompt)
        self.assertIn("Amy locks the door.", prompt)

    def test_later_phase_receives_previous_final_beat_as_continuity_boundary(self):
        previous_phase = self.make_phase([])
        current_phase = self.make_phase([
            {"id": "E3", "event": "Amy leaves the basement."},
        ])
        current_phase["phase_number"] = 2
        current_phase["beat_start"] = 6
        current_phase["beat_end"] = 10
        messages = minimax.build_beat_generation_messages(
            "Amy leaves the basement.",
            10,
            batch_start=6,
            batch_end=10,
            previous_beats=["Amy closes the basement door."],
            macro_arc={"phases": [previous_phase, current_phase]},
            current_phase=current_phase,
        )
        user = messages[1]["content"]
        self.assertIn("PREVIOUS PHASE FINAL BEAT — CONTINUITY ONLY", user)
        self.assertIn("Beat 5: Amy closes the basement door.", user)
        self.assertIn("Do not repeat that beat.", user)

    def test_generation_prompt_rejects_optional_end_state_details(self):
        messages = minimax.build_beat_arc_plan_messages(
            "She defeats the intruders and releases her family.",
            5,
            beat_instructions="Beat 4 must show the family entering the safe room.",
        )
        prompt = messages[0]["content"]
        self.assertIn("only states explicitly required", prompt)
        self.assertIn("optional injuries", prompt)
        self.assertIn("logically necessary", prompt)
        self.assertIn("family entering the safe room", messages[1]["content"])

    def test_fidelity_prompt_checks_end_state_authorization(self):
        arc = {
            "phases": [{
                "phase_number": 1,
                "beat_start": 1,
                "beat_end": 5,
                "narrative_purpose": "Conflict",
                "broad_progression": "Defeat the intruders",
                "characters_introduced": [],
                "location": "House",
                "required_end_state": "The protagonist is injured and the furniture is destroyed.",
            }]
        }
        messages = minimax.build_beat_arc_fidelity_messages(
            "She defeats the intruders and releases her family.", arc
        )
        prompt = messages[1]["content"]
        self.assertIn("required_end_state clause", prompt)
        self.assertIn("not explicitly authorized", prompt)
        self.assertIn("environmental damage", prompt)

    def test_fidelity_parser_accepts_a_valid_authorized_arc_result(self):
        parsed = minimax.parse_beat_arc_fidelity({"valid": True, "issues": []})
        self.assertTrue(parsed["valid"])

    def test_fidelity_parser_preserves_rejection_for_optional_state(self):
        parsed = minimax.parse_beat_arc_fidelity({
            "valid": False,
            "issues": ["required_end_state invents an optional injury"],
        })
        self.assertFalse(parsed["valid"])
        self.assertIn("optional injury", parsed["issues"][0])

    def test_fidelity_prompt_allows_source_authorized_specificity(self):
        messages = minimax.build_beat_arc_fidelity_messages(
            (
                "The house is soaked in blood. Amy equips the pistol and AR-15, "
                "dismembers the zombies, and lets the children out of the locked basement."
            ),
            {"phases": []},
        )
        prompt = messages[1]["content"]
        self.assertIn("source-authorized paraphrase", prompt)
        self.assertIn("dismemberment/decapitation", prompt)
        self.assertIn("unlocking or opening a locked basement door", prompt)
        self.assertIn("Do not require optional choreography", prompt)

    def test_macro_plan_prompt_keeps_required_events_semantic(self):
        messages = minimax.build_beat_arc_plan_messages(
            "Amy retrieves weapons and fights the zombies.",
            8,
        )
        prompt = messages[0]["content"]
        self.assertIn("WHAT must happen, not optional choreography", prompt)
        self.assertIn("Amy reloads during a lull", prompt)
        self.assertIn("unlocking/opening a locked", prompt)
        self.assertIn("Every hard fact in required_end_state", prompt)


if __name__ == "__main__":
    unittest.main()
