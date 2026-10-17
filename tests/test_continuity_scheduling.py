import copy
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import minimax


def _args(**overrides):
    values = {
        "model": "mistral",
        "lora": (),
        "repair": None,
        "generate_beats": None,
        "segment_length": 6.0,
        "total_length": 12.0,
        "megapixels": 0.5,
        "refresh": None,
        "resume": 1,
        "steps": 6,
        "context_frames": minimax.DEFAULT_CONTEXT_FRAMES,
        "ff": False,
        "vision_continuity": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ContinuitySchedulingTests(unittest.TestCase):
    def test_segment_one_allows_initial_continuity(self):
        self.assertEqual(
            minimax.validate_director_continuity({"segment": 1}),
            "initial",
        )

    def test_segment_two_warns_and_accepts_missing_continuity(self):
        formatted = {
            "detailed_description": "[Shot 1] At 00:00.000, Amy looks toward the doorway. At 00:05.000, Amy lowers her hand.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
        }
        with mock.patch(
            "minimax.ask_llm",
            side_effect=[
                {
                    "raw_scene": (
                        "At 00:00.000, Amy looks toward the doorway.\n"
                        "At 00:05.000, Amy lowers her hand.\n"
                        "End continuity state: Amy stands beside the doorway."
                    ),
                    "beat_complete": True,
                },
                formatted,
                {"overall_soundscape": "Room tone."},
                {"non_diegetic_music": "N/A"},
            ],
        ), mock.patch("builtins.print") as printed:
            result = minimax.request_segment_llm(
                {
                    "segment": 2,
                    "current_duration": 6.0,
                    "messages": [],
                },
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertEqual(result["llm_result"], {
            **formatted,
            "reference_alignment": "",
            "subject_genders": {},
        })
        self.assertIn(
            "WARNING: Segment 2 Director continuity is missing or unusable",
            "\n".join(
                str(call.args[0]) for call in printed.call_args_list if call.args
            ),
        )

    def test_segment_two_logs_and_accepts_completed_continuity(self):
        bundle = {
            "segment": 2,
            "active_beat_id": None,
            "current_duration": 6.0,
            "messages": [{"role": "user", "content": "Direct segment 2."}],
            "conditioning_mode": "continuation",
            "opening_state": "Amy is beside the doorway.",
            "h3_opening_summary": "Amy is beside the doorway.",
            "continuity_source": "prompt",
            "opening_state_sha256": "opening-hash",
        }
        formatted = {
            "detailed_description": "[Shot 1] At 00:00.000, Amy looks toward the doorway. At 00:05.000, Amy lowers her hand.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
        }
        with mock.patch(
            "minimax.ask_llm",
            side_effect=[
                {
                    "raw_scene": (
                        "At 00:00.000, Amy looks toward the doorway.\n"
                        "At 00:05.000, Amy lowers her hand.\n"
                        "End continuity state: Amy stands beside the doorway."
                    ),
                    "beat_complete": True,
                },
                formatted,
                {"overall_soundscape": "Room tone."},
                {"non_diegetic_music": "N/A"},
            ],
        ), mock.patch("builtins.print") as printed:
            minimax.request_segment_llm(
                bundle,
                [],
                "run-id",
                {"source_sha256": "source-hash"},
            )

        self.assertIn(
            "Segment 2 Director continuity source: prompt",
            "\n".join(
                str(call.args[0]) for call in printed.call_args_list if call.args
            ),
        )
        bundle["continuity_source"] = "vision"
        self.assertEqual(
            minimax.validate_director_continuity(bundle),
            "vision",
        )

    def test_background_render_handoff_uses_immediately_prior_segment(self):
        args = _args(total_length=18.0)
        segment_two_started = threading.Event()
        release_segment_two = threading.Event()
        segment_three_started = threading.Event()
        render_sources = []

        def load_text(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "Amy walks toward a doorway."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return "<Subject 1> is Amy, referenced in <Picture 1>."
            if path == minimax.CANONICAL_DATA_FILE:
                return "Amy is female and 30-years-old."
            return ""

        def request_segment(bundle, _beats, _run_id, _run_config):
            payload = dict(bundle)
            payload["llm_result"] = {
                "detailed_description": (
                    f"[Shot 1] Segment {bundle['segment']} continues."
                ),
                "overall_soundscape": "Footsteps.",
                "non_diegetic_music": "N/A",
                "completed_beat_ids": [],
            }
            return payload

        def render(segment, *render_args, **kwargs):
            render_sources.append((int(segment), render_args[3]))
            kwargs["render_started_event"].set()
            if int(segment) == 2:
                segment_two_started.set()
                if not release_segment_two.wait(5):
                    raise AssertionError("test did not release Segment 2 render")
            if int(segment) == 3:
                segment_three_started.set()
            return (None, f"segment_{int(segment):04d}.mp4", 1280, 720, 0.5)

        patches = (
            mock.patch("minimax.parse_args", return_value=args),
            mock.patch("minimax.configure_formatter"),
            mock.patch("minimax.configure_reference_image_overrides"),
            mock.patch("minimax.load_text_file", side_effect=load_text),
            mock.patch("minimax.load_or_generate_character_canon", return_value={
                "fields": ["age", "clothing", "gender"],
                "characters": [{"name": "Amy", "age": "30", "clothing": "jeans", "gender": "female"}],
            }),
            mock.patch(
                "minimax.parse_story_beat_instructions",
                return_value=("Amy walks toward a doorway.", []),
            ),
            mock.patch("minimax.os.path.isfile", return_value=False),
            mock.patch("minimax.load_phrase_exclusions", return_value=[]),
            mock.patch("minimax.reset_prompt_history"),
            mock.patch("minimax.load_or_generate_beats", return_value=[]),
            mock.patch("minimax.load_story_arc", return_value={"phases": []}),
            mock.patch("minimax.validate_runtime_environment"),
            mock.patch("minimax.load_workflow", return_value={}),
            mock.patch("minimax.validate_workflow"),
            mock.patch("minimax.verify_reference_images"),
            mock.patch("minimax.verify_global_loras"),
            mock.patch("minimax.save_generation_state"),
            mock.patch("minimax.request_segment_llm", side_effect=request_segment),
            mock.patch(
                "minimax.request_combined_continuity",
                return_value={"reduced_state": {"environment": {"location": "road"}}},
            ),
            mock.patch(
                "minimax.request_continuity_opening_state",
                return_value="Amy is beside the doorway.",
            ),
            mock.patch("minimax.build_h3_prompt", return_value="H3 prompt"),
            mock.patch("minimax.record_completed_segment", return_value={}),
            mock.patch("minimax.render_segment_with_retries", side_effect=render),
            mock.patch("minimax.stitch_videos"),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        with ThreadPoolExecutor(max_workers=1) as summary_executor:
            with ThreadPoolExecutor(max_workers=1) as render_executor:
                with ThreadPoolExecutor(max_workers=1) as main_executor:
                    run = main_executor.submit(
                        minimax._run_main,
                        summary_executor,
                        None,
                        render_executor,
                    )
                    self.assertTrue(segment_two_started.wait(5))
                    self.assertFalse(
                        segment_three_started.is_set(),
                        "Segment 3 started before Segment 2 finished rendering",
                    )
                    release_segment_two.set()
                    run.result(timeout=10)

        self.assertEqual(
            render_sources,
            [
                (1, None),
                (2, os.path.abspath("segment_0001.mp4")),
                (3, os.path.abspath("segment_0002.mp4")),
            ],
        )

    def _run_two_segment_render_schedule(
        self,
        *,
        vision_continuity=0,
        fail_first_render=False,
        fail_speculative_prep=False,
        fail_authoritative_prep=False,
        phase_boundary=False,
    ):
        args = _args(total_length=12.0, vision_continuity=vision_continuity)
        args.test_prompt_generation = False
        args.generate_prompts = None
        args.generate_from_prompts = False
        args.use_prompts = None
        args.director_only = False
        args.retention = False
        args.disable_subject_removal = False
        args.trim_frames = minimax.TRIM_FRAMES_AFTER_FIRST
        args.lora_dir = "/tmp/loras"
        args.capture_h3_fixture = None
        args.capture_h3_segment = None
        render_one_started = threading.Event()
        render_one_completed = threading.Event()
        release_render_one = threading.Event()
        release_render_two = threading.Event()
        visual_started = threading.Event()
        release_visual = threading.Event()
        director_two_started = threading.Event()
        render_two_started = threading.Event()
        stitch_started = threading.Event()
        director_openings = {}
        director_bundles = {}
        director_two_started_during_render = []
        render_sources = []
        durable_snapshots = []
        phase_logs = []
        world_state_prep_calls = {}

        beats_for_run = (
            [
                minimax.BeatDefinition("Amy begins the first action.", phase_number=1),
                minimax.BeatDefinition(
                    "Amy begins the second action.", phase_number=2, phase_start=True
                ),
            ]
            if phase_boundary
            else []
        )
        macro_arc = (
            {
                "phases": [
                    {
                        "phase_number": 1,
                        "beat_start": 1,
                        "beat_end": 1,
                        "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
                        "source_text": "Amy begins the first action.",
                        "required_events": [{
                            "beat_number": 1,
                            "event": "Amy begins the first action.",
                            "state_effects": [],
                        }],
                    },
                    {
                        "phase_number": 2,
                        "beat_start": 2,
                        "beat_end": 2,
                        "narrative_purpose": minimax.SOURCE_SPAN_PHASE_PURPOSE,
                        "source_text": "Amy begins the second action.",
                        "required_events": [{
                            "beat_number": 2,
                            "event": "Amy begins the second action.",
                            "state_effects": [],
                        }],
                    },
                ]
            }
            if phase_boundary
            else {"phases": []}
        )

        location_state = {
            "location": {"name": "Room"},
            "anchors": [{
                "name": "counter",
                "type": "wooden counter",
                "world_state_role": "fixture_support",
                "mobility": "fixed",
            }],
            "objects": [],
        }

        def load_text(path, required=True):
            del required
            if path == minimax.STORY_FILE:
                return "Amy enters the room and climbs onto the counter."
            if path == minimax.EXPANDED_STORY_FILE:
                return "Amy enters the room and climbs onto the counter."
            if path == minimax.SUBJECT_DEFINITIONS_FILE:
                return "<Subject 1> is Amy."
            if path == minimax.CANONICAL_DATA_FILE:
                return "Amy is female and 30-years-old."
            return ""

        def request_segment(bundle, _beats, _run_id, _run_config):
            segment = int(bundle["segment"])
            director_openings[segment] = copy.deepcopy(
                bundle.get("world_state_opening")
            )
            director_bundles[segment] = copy.deepcopy(bundle)
            if segment == 2:
                director_two_started_during_render.append(
                    not render_one_completed.is_set()
                )
                director_two_started.set()
            subject_id = next(iter(bundle["world_state_opening"]["subjects"]))
            counter_id = next(
                prop_id for prop_id, prop in
                bundle["world_state_opening"]["props"].items()
                if prop.get("name") == "counter"
            )
            payload = dict(bundle)
            payload["raw_scene"] = (
                "At 00:00.000, Amy climbs onto the counter.\n"
                "End continuity state: Amy stands on the counter."
            )
            payload["llm_result"] = {
                "detailed_description": "Amy stands on the counter.",
                "reference_alignment": "",
                "overall_soundscape": "Room tone.",
                "non_diegetic_music": "N/A",
                "completed_beat_ids": [],
            }
            payload["request1_result"] = {
                "beat_complete": True,
                "state_actions": ([{
                    "action_id": "support-counter",
                    "op": "set_support",
                    "subject_id": subject_id,
                    "support_id": counter_id,
                }] if segment == 1 else []),
                "state_actions_dry_run_accepted": True,
            }
            payload["loras"] = []
            return payload

        def extract_events(opening, raw_scene, *, segment_number, **_kwargs):
            actions = []
            if int(segment_number) == 1:
                subject_id = next(iter(opening["subjects"]))
                counter_id = next(
                    prop_id for prop_id, prop in opening["props"].items()
                    if prop.get("name") == "counter"
                )
                actions = [{
                    "action_id": "support-counter",
                    "op": "set_support",
                    "subject_id": subject_id,
                    "support_id": counter_id,
                }]
            return {
                "accepted": True,
                "state_actions": actions,
                "raw_scene": minimax._director_strip_camera_instructions(raw_scene),
                "opening_state_sha256": minimax.world_state_sha256(opening),
            }

        def seed_known_presence(state, *_args, **kwargs):
            return minimax.seed_story_start_presence(
                state,
                [{"name": "Amy", "initial_state": "Amy is in the room."}],
                location_id=kwargs["location_id"],
            )

        def render(segment, *_render_args, **kwargs):
            render_sources.append((int(segment), _render_args[3]))
            kwargs["render_started_event"].set()
            if int(segment) == 1:
                render_one_started.set()
                if not release_render_one.wait(5):
                    raise AssertionError("test did not release Segment 1 render")
                if fail_first_render:
                    raise RuntimeError("simulated Segment 1 render failure")
                render_one_completed.set()
            else:
                render_two_started.set()
                if not release_render_one.is_set():
                    raise AssertionError(
                        "Segment 2 render started before Segment 1 completed"
                    )
                if not release_render_two.wait(5):
                    raise AssertionError("test did not release Segment 2 render")
            return (None, f"segment_{int(segment):04d}.mp4", 1280, 720, 0.5)

        def stitch(*_args, **_kwargs):
            stitch_started.set()

        def isfile(path):
            if str(path) == "/tmp/room-location.mp4":
                return True
            return original_isfile(path)

        def getsize(path):
            if str(path) == "/tmp/room-location.mp4":
                return 1
            return original_getsize(path)

        def visual_end_state(*_args, **_kwargs):
            visual_started.set()
            if not release_visual.wait(5):
                raise AssertionError("test did not release visual continuity gate")
            return {
                "raw_end_state": {},
                "end_state": {},
                "frame_paths": [],
            }

        def prepare_world_state(state, segment_number, *_args, **_kwargs):
            segment_number = int(segment_number)
            world_state_prep_calls[segment_number] = (
                world_state_prep_calls.get(segment_number, 0) + 1
            )
            if segment_number == 2 and (
                fail_authoritative_prep
                or (fail_speculative_prep and world_state_prep_calls[2] == 1)
            ):
                raise ValueError("simulated Segment 2 preparation failure")
            return state, []

        original_isfile = os.path.isfile
        original_getsize = os.path.getsize
        patches = (
            mock.patch("minimax.parse_args", return_value=args),
            mock.patch("minimax.configure_formatter"),
            mock.patch("minimax.configure_reference_image_overrides"),
            mock.patch("minimax.copy_reference_image_inputs"),
            mock.patch("minimax.load_text_file", side_effect=load_text),
            mock.patch("minimax.load_or_generate_character_canon", return_value={
                "fields": ["age", "clothing", "gender"],
                "characters": [{"name": "Amy", "age": "30", "clothing": "jeans", "gender": "female"}],
            }),
            mock.patch("minimax.canonicalize_defined_subject_wardrobes", return_value={}),
            mock.patch("minimax.parse_story_beat_instructions", return_value=("A story.", [])),
            mock.patch("minimax.load_beats", return_value=beats_for_run),
            mock.patch("minimax.load_or_generate_beats", return_value=beats_for_run),
            mock.patch("minimax.load_story_arc", return_value=macro_arc),
            mock.patch("minimax.load_canonical_data", return_value={}),
            mock.patch("minimax.load_phrase_exclusions", return_value=[]),
            mock.patch("minimax.reset_prompt_history"),
            mock.patch("minimax.validate_runtime_environment"),
            mock.patch("minimax.load_workflow", return_value={}),
            mock.patch("minimax.validate_workflow"),
            mock.patch("minimax.validate_refresh_workflow"),
            mock.patch(
                "minimax.console_log",
                side_effect=lambda *args, **_kwargs: phase_logs.append(" ".join(
                    str(arg) for arg in args
                )),
            ),
            mock.patch("minimax.verify_reference_images"),
            mock.patch("minimax.verify_global_loras"),
            mock.patch(
                "minimax.save_generation_state",
                side_effect=lambda state: durable_snapshots.append(
                    copy.deepcopy(state)
                ),
            ),
            mock.patch("minimax.save_generated_prompts_file"),
            mock.patch("minimax.active_configured_reference_count", return_value=0),
            mock.patch("minimax.extract_story_locations", return_value={
                "overall_location": "Room",
                "starting_location": "Room",
            }),
            mock.patch("minimax.extract_static_setting", return_value="Static room"),
            mock.patch("minimax.refine_story_setting_spatially", return_value="Spatial room"),
            mock.patch("minimax.extract_story_setting_description", return_value={
                "text_description": "A room with a wooden counter.",
                "location_state": copy.deepcopy(location_state),
            }),
            mock.patch("minimax.render_location_reference_video", return_value="/tmp/room-location.mp4"),
            mock.patch("minimax.extract_initial_location_subjects", return_value=[{
                "name": "Amy", "initial_state": "Amy is in the room."
            }]),
            mock.patch("minimax.extract_registered_subject_story_start_presence", side_effect=seed_known_presence),
            mock.patch(
                "minimax.prepare_segment_world_state_for_director",
                side_effect=prepare_world_state,
            ),
            mock.patch("minimax.os.path.isfile", side_effect=isfile),
            mock.patch("minimax.os.path.getsize", side_effect=getsize),
            mock.patch("minimax.request_segment_llm", side_effect=request_segment),
            mock.patch("minimax.extract_and_dry_run_world_state_events", side_effect=extract_events),
            mock.patch("minimax._resolve_visible_subjects_best_effort", side_effect=lambda raw, **_k: (raw, [], [], True)),
            mock.patch("minimax.ensure_character_reference_images", return_value=({}, [])),
            mock.patch("minimax.build_segment_reference_bindings", side_effect=lambda **kw: (
                {}, kw["subject_definitions"], kw["binding_state"], {
                    "bindings": [], "active_subject_ids": [],
                    "defined_subject_ids": [],
                    "excluded_configured_picture_ids": [],
                }
            )),
            mock.patch("minimax.build_h3_prompt_with_camera_recovery", return_value="H3 prompt"),
            mock.patch(
                "minimax.request_optional_visual_end_state",
                side_effect=visual_end_state,
            ),
            mock.patch("minimax.render_segment_with_retries", side_effect=render),
            mock.patch("minimax.stitch_videos", side_effect=stitch),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        with ThreadPoolExecutor(max_workers=1) as summary_executor:
            with ThreadPoolExecutor(max_workers=1) as prefetch_executor:
                with ThreadPoolExecutor(max_workers=1) as render_executor:
                    with ThreadPoolExecutor(max_workers=1) as main_executor:
                        run = main_executor.submit(
                            minimax._run_main,
                            summary_executor,
                            prefetch_executor,
                            render_executor,
                        )
                        if not render_one_started.wait(5):
                            run.result(timeout=1)
                            self.fail("Segment 1 render did not start")
                        if vision_continuity:
                            self.assertFalse(
                                director_two_started.is_set(),
                                "next Director request started before the visual gate",
                            )
                            release_render_one.set()
                            self.assertTrue(visual_started.wait(5))
                            self.assertFalse(
                                director_two_started.is_set(),
                                "next Director request crossed the visual continuity gate",
                            )
                            release_visual.set()
                        if not vision_continuity and not fail_speculative_prep:
                            self.assertTrue(
                                director_two_started.wait(5),
                                "Segment 2 Director request was not prepared at the expected time",
                            )
                        if director_two_started.is_set():
                            subject_two = next(iter(
                                director_openings[2]["subjects"].values()
                            ))
                            counter_id = next(
                                prop_id for prop_id, prop in
                                director_openings[2]["props"].items()
                                if prop.get("name") == "counter"
                            )
                            self.assertEqual(
                                subject_two.get("support_id"), counter_id
                            )
                        self.assertFalse(
                            render_two_started.is_set(),
                            "Segment 2 render must wait for Segment 1's video",
                        )
                        if not vision_continuity and not fail_speculative_prep:
                            self.assertTrue(durable_snapshots)
                            self.assertTrue(all(
                                not snapshot.get("segments")
                                and all(
                                    subject.get("support_id") is None
                                    for subject in snapshot.get(
                                        "world_state", {}
                                    ).get("subjects", {}).values()
                                )
                                for snapshot in durable_snapshots
                            ), "projected end state became durable before render success")
                        if fail_first_render:
                            release_render_one.set()
                            with self.assertRaisesRegex(
                                RuntimeError, "simulated Segment 1 render failure"
                            ):
                                run.result(timeout=10)
                            self.assertTrue(durable_snapshots)
                            self.assertTrue(all(
                                not snapshot.get("segments")
                                and all(
                                    subject.get("support_id") is None
                                    for subject in snapshot.get(
                                        "world_state", {}
                                    ).get("subjects", {}).values()
                                )
                                for snapshot in durable_snapshots
                            ), "failed render published projected state or completion")
                            self.assertTrue(all(
                                "prefetched_next_prompt" not in snapshot
                                for snapshot in durable_snapshots[-1:]
                            ))
                            return
                        release_render_one.set()
                        release_visual.set()
                        if fail_speculative_prep:
                            if fail_authoritative_prep:
                                with self.assertRaisesRegex(
                                    ValueError,
                                    "simulated Segment 2 preparation failure",
                                ):
                                    run.result(timeout=10)
                                self.assertEqual(world_state_prep_calls[2], 2)
                                self.assertFalse(director_two_started.is_set())
                                self.assertTrue(durable_snapshots[-1].get("segments"))
                                committed_subject = next(iter(
                                    durable_snapshots[-1]["world_state"][
                                        "subjects"
                                    ].values()
                                ))
                                committed_counter = next(
                                    prop_id for prop_id, prop in
                                    durable_snapshots[-1]["world_state"][
                                        "props"
                                    ].items()
                                    if prop.get("name") == "counter"
                                )
                                self.assertEqual(
                                    committed_subject.get("support_id"),
                                    committed_counter,
                                )
                                return
                            self.assertTrue(director_two_started.wait(5))
                            self.assertEqual(world_state_prep_calls[2], 2)
                            self.assertEqual(
                                director_two_started_during_render,
                                [False],
                                "fallback must prepare only after Segment 1 render",
                            )
                            subject_two = next(iter(
                                director_openings[2]["subjects"].values()
                            ))
                            counter_id = next(
                                prop_id for prop_id, prop in
                                director_openings[2]["props"].items()
                                if prop.get("name") == "counter"
                            )
                            self.assertEqual(
                                subject_two.get("support_id"), counter_id
                            )
                        self.assertTrue(render_two_started.wait(5))
                        self.assertFalse(
                            stitch_started.is_set(),
                            "final stitch started before the final render completed",
                        )
                        release_render_two.set()
                        run.result(timeout=10)

        self.assertEqual(
            render_sources,
            [(1, None), (2, os.path.abspath("segment_0001.mp4"))],
        )
        self.assertTrue(durable_snapshots)
        self.assertTrue(durable_snapshots[-1].get("segments"))
        final_subject = next(iter(
            durable_snapshots[-1]["world_state"]["subjects"].values()
        ))
        final_counter_id = next(
            prop_id for prop_id, prop in
            durable_snapshots[-1]["world_state"]["props"].items()
            if prop.get("name") == "counter"
        )
        self.assertEqual(final_subject.get("support_id"), final_counter_id)
        self.assertTrue(stitch_started.is_set())
        if phase_boundary:
            self.assertEqual(
                director_openings[2]["subjects"][next(iter(
                    director_openings[2]["subjects"]
                ))].get("support_id"),
                final_counter_id,
            )
            self.assertEqual(len(director_two_started_during_render), 1)
            self.assertTrue(director_two_started_during_render[0])
            self.assertEqual(
                director_bundles[2]["current_phase"]["phase_number"], 2
            )
            self.assertEqual(
                director_bundles[2]["assigned_source"],
                "Amy begins the second action.",
            )
            self.assertEqual(
                sum("Starting phase 2 at segment 2" in line for line in phase_logs),
                1,
            )


    def test_projected_director_prompt_overlaps_render_but_next_render_waits(self):
        self._run_two_segment_render_schedule()

    def test_visual_continuity_gate_completes_before_next_director_prefetch(self):
        self._run_two_segment_render_schedule(vision_continuity=1)

    def test_failed_render_rolls_back_speculative_next_segment_state(self):
        self._run_two_segment_render_schedule(fail_first_render=True)

    def test_speculative_setup_failure_falls_back_to_normal_preparation(self):
        self._run_two_segment_render_schedule(fail_speculative_prep=True)

    def test_normal_preparation_failure_still_propagates(self):
        self._run_two_segment_render_schedule(
            fail_speculative_prep=True,
            fail_authoritative_prep=True,
        )

    def test_phase_boundary_prefetch_uses_projected_state_once(self):
        self._run_two_segment_render_schedule(phase_boundary=True)


if __name__ == "__main__":
    unittest.main()
