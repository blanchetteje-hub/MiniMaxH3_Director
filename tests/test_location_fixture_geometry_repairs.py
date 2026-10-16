import copy
import unittest
from unittest.mock import patch
import minimax
from world_state import empty_world_state, seed_canonical_static_location_state


class FixtureGeometryRepairs(unittest.TestCase):
    def test_spatial_refinement_preserves_source_sizes_without_demanding_invented_measurements(self):
        messages = minimax.build_story_setting_spatial_refinement_messages(
            "An accessible passage.", neighboring_location_context="A neighboring courtyard.")
        self.assertIn("Preserve explicit source measurements", messages[0]["content"])
        self.assertIn("do not invent precise numeric measurements", messages[0]["content"])
        self.assertIn("only neighboring details necessary", messages[0]["content"])
        self.assertIn("A neighboring courtyard.", messages[1]["content"])

    def fixture(self, name="wooden post"):
        return {"name": name, "type": "post", "world_state_role": "fixture", "mobility": "fixed"}

    def registry(self, name="wooden post"):
        return {"locations": {"house": {"name": "old house"}}, "props": {
            "post": {"name": name, "placement": {"kind": "located", "location_id": "house"},
                     "provenance": {"registration": {"authority": "canonical_location_state", "source_type": "post"}}}}}

    def test_neighbor_fixture_keeps_one_owner(self):
        world = self.registry()
        before = copy.deepcopy(world)
        location = {"location": {"name": "meadow"}, "anchors": [self.fixture()], "objects": []}
        result = minimax.reconcile_neighboring_location_fixtures(location, world,
            "The wooden post at the old house is visible beyond the meadow entrance.")
        self.assertEqual(result["anchors"], [])
        self.assertEqual(world, before)
        self.assertEqual(len(location["anchors"]), 1)

    def test_extraction_then_seeding_keeps_one_canonical_fixture_in_h3(self):
        state, owner = seed_canonical_static_location_state(
            empty_world_state("neighbor-regression"),
            {"location": {"name": "old house"}, "anchors": [self.fixture()], "objects": []})
        response = {"location": {"name": "meadow"}, "anchors": [self.fixture()], "objects": []}
        request = unittest.mock.Mock(side_effect=[
            "The old house wooden post is visible beyond the meadow entrance.", response])
        extracted = minimax.extract_story_setting_description(
            "A meadow", location_name="meadow", world_state=state, llm_request=request)
        state, destination = seed_canonical_static_location_state(state, extracted["location_state"])
        self.assertNotEqual(owner, destination)
        self.assertEqual(len(state["props"]), 1)
        self.assertEqual(next(iter(state["props"].values()))["placement"]["location_id"], owner)
        prompt = minimax.build_h3_prompt(
            {"detailed_description": "[Shot 1] The meadow entrance remains empty.",
             "overall_soundscape": "Wind.", "non_diegetic_music": "N/A"},
            "", segment_number=1, world_state=state)
        self.assertEqual(prompt.count("Prop wooden post:"), 1)

    def test_indistinguishable_neighbor_requires_owner(self):
        location = {"location": {"name": "meadow"}, "anchors": [self.fixture()], "objects": []}
        with self.assertRaisesRegex(ValueError, "Ambiguous neighboring fixture"):
            minimax.reconcile_neighboring_location_fixtures(location, self.registry(), "A wooden post stands here.")

    def test_distinct_fixture_is_preserved(self):
        location = {"location": {"name": "meadow"}, "anchors": [self.fixture("stone post")], "objects": []}
        self.assertEqual(minimax.reconcile_neighboring_location_fixtures(location, self.registry()), location)
        location["anchors"] = [self.fixture("石门")]
        self.assertEqual(minimax.reconcile_neighboring_location_fixtures(location, self.registry("木柱")), location)

    def test_impossible_passage_rejected_before_json(self):
        responses = iter(["The entrance is 30 cm wide, narrowing to 15 cm."])
        calls = []
        def llm(messages, **kwargs):
            calls.append(kwargs["history_metadata"]["purpose"])
            return next(responses)
        with self.assertRaisesRegex(ValueError, "cannot accommodate"):
            minimax.extract_story_setting_description("A tunnel", source_text="An adult human walks through the tunnel.",
                llm_request=llm, repair_attempts=0)
        self.assertEqual(calls, ["story_setting_extract"])

    def test_source_conflict_is_flagged(self):
        issues = minimax.validate_traversal_geometry("The opening is 15 cm wide.",
            source_text="An adult human passes through an opening 15 cm wide.")
        self.assertIn("Explicit source measurement conflicts", issues[0])

    def test_fantasy_explicit_body_size(self):
        self.assertTrue(minimax.validate_traversal_geometry("The passage is 1 m wide.",
            source_text="The dragon's body is 3 m wide. It walks through the passage."))
        self.assertEqual(minimax.validate_traversal_geometry("The passage is 15 cm wide.",
            source_text="The tiny creature's body is 5 cm wide. It walks through the passage."), [])
        self.assertEqual(minimax.validate_traversal_geometry("The passage is 15 cm wide.",
            source_text="An adult human has a body 5 cm wide in this fictional world. She walks through the passage."), [])

    def test_passage_width_is_not_mistaken_for_body_width(self):
        self.assertEqual(minimax.validate_traversal_geometry("The passage is 1 m wide.",
            source_text="Pip has a body 10 cm wide and enters a passage 3 m wide.",
            traversal_text="Pip enters the passage.", location_name="Passage"), [])

    def test_unknown_size_and_unmeasured_geometry_are_not_invented(self):
        self.assertEqual(minimax.validate_traversal_geometry("The tunnel is narrow.", source_text="An adult human enters."), [])
        self.assertEqual(minimax.validate_traversal_geometry("The tunnel is 15 cm wide.", source_text="A fairy enters."), [])

    def test_decimal_bottleneck_and_other_actor_are_handled(self):
        self.assertTrue(minimax.validate_traversal_geometry("The passage is 0.15 m wide.",
            source_text="Mara is an adult human. Mara enters the passage.", traversal_text="Mara enters the passage."))
        self.assertEqual(minimax.validate_traversal_geometry("The passage is 0.15 m wide.",
            source_text="Mara is an adult human. Pip is a tiny fairy.", traversal_text="Pip enters the passage."), [])

    def test_same_owner_keeps_fixture(self):
        location = {"location": {"name": "old house"}, "anchors": [self.fixture()], "objects": []}
        self.assertEqual(minimax.reconcile_neighboring_location_fixtures(location, self.registry()), location)

    def test_authored_conflict_cannot_be_omitted_by_repair(self):
        llm = unittest.mock.Mock(return_value="The opening is broad and accessible.")
        with self.assertRaisesRegex(ValueError, "Authored physical conflict"):
            minimax.extract_story_setting_description("An opening", source_text=
                "Mara is an adult human. The opening is 15 cm wide. Mara walks through the opening.",
                llm_request=llm)
        llm.assert_not_called()

    def test_neighbor_declared_local_requires_prose_repair(self):
        llm = unittest.mock.Mock(return_value="The meadow contains the old house wooden post.")
        with self.assertRaisesRegex(ValueError, "Neighbor fixture"):
            minimax.extract_story_setting_description("A meadow", location_name="meadow",
                world_state=self.registry(), llm_request=llm, repair_attempts=0)
        self.assertEqual(llm.call_count, 1)

    def test_neighbor_orientation_is_permitted(self):
        description = "The old house wooden post is visible beyond the meadow entrance."
        llm = unittest.mock.Mock(side_effect=[description,
            {"location": {"name": "meadow"}, "anchors": [self.fixture()], "objects": []}])
        result = minimax.extract_story_setting_description("A meadow", location_name="meadow",
            world_state=self.registry(), llm_request=llm, repair_attempts=0)
        self.assertEqual(result["text_description"], description)
        self.assertEqual(result["location_state"]["anchors"], [])

    def test_untraversed_tiny_mouse_hole_is_not_a_source_conflict(self):
        source = "Mara is an adult human. A mouse hole is 2 cm wide. Mara walks across the room."
        self.assertEqual(minimax.validate_traversal_geometry(source, source_text=source,
            traversal_text="Mara walks across the room."), [])

    def test_separate_source_tunnel_measurement_remains_binding(self):
        source = "Mara is an adult human. The tunnel is 15 cm wide. Mara crawls through the tunnel."
        self.assertTrue(minimax.validate_traversal_geometry(source, source_text=source,
            traversal_text="Mara crawls through the tunnel."))

    def test_passage_length_is_not_width(self):
        self.assertEqual(minimax.validate_traversal_geometry("The passage is 15 cm long and 2 m wide.",
            source_text="Mara is an adult human. Mara walks through the passage."), [])

    def test_explicit_upright_height_and_crawling(self):
        source = "Mara is 2 m tall. Mara walks through the doorway."
        self.assertTrue(minimax.validate_traversal_geometry("The doorway is 1 m high.", source_text=source))
        self.assertEqual(minimax.validate_traversal_geometry("The doorway is 1 m high.", source_text=source,
            traversal_text="Mara crawls through the doorway."), [])
        self.assertEqual(minimax.validate_traversal_geometry("The doorway is 2 m high.",
            source_text="Mara is 1.5 m tall beside a 3 m tall statue. Mara walks through the doorway.",
            traversal_text="Mara walks through the doorway."), [])

    def test_explicit_shoulder_width_phrasings(self):
        for anatomy in ("Mara's shoulders are 50 cm wide.", "Mara has shoulder width 50 cm."):
            self.assertTrue(minimax.validate_traversal_geometry("The passage width is 30 cm.",
                source_text=anatomy + " Mara walks through the passage."))
