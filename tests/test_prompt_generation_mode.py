import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import minimax
import pytest


def _args(**overrides):
    values = {
        "generate_beats": None,
        "generate_prompts": None,
        "use_prompts": None,
        "generate_from_prompts": False,
        "director_only": False,
        "segment_length": 5.0,
        "total_length": 5.0,
        "megapixels": 0.5,
        "resume": 1,
        "repair": None,
        "model": "mistral",
        "lora": [],
        "lora_dir": "/tmp/loras",
        "refresh": None,
        "trim_frames": 2,
        "retention": False,
        "disable_subject_removal": False,
        "test_prompt_generation": True,
        "vision_continuity": 1,
        "steps": 6,
        "ff": False,
        "capture_h3_fixture": None,
        "capture_h3_segment": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_parse_args_defaults_prompt_generation_test_mode_off():
    args = minimax.parse_args(["5", "10", ".2"])
    assert not args.test_prompt_generation
    assert not args.disable_subject_removal
    assert minimax.parse_args(
        ["5", "10", ".2", "--disable-subject-removal"]
    ).disable_subject_removal
    assert minimax.parse_args(
        ["5", "10", ".2", "--test-prompt-generation"]
    ).test_prompt_generation


def test_removed_save_flag_is_rejected():
    with pytest.raises(SystemExit):
        minimax.parse_args(["8", "8", ".5", "--generate-all"])


def test_use_prompts_accepts_explicit_package_path_without_video_positionals(tmp_path):
    package = tmp_path / "my_prompts.json"
    args = minimax.parse_args(["--use-prompts", str(package)])
    assert args.use_prompts == str(package.resolve())
    assert args.segment_length is None
    assert args.total_length is None
    assert args.megapixels is None


def test_use_prompts_rejects_video_positionals():
    with __import__("pytest").raises(SystemExit):
        minimax.parse_args(["8", "64", ".5", "--use-prompts", "prompts.json"])


def test_director_only_implies_prompt_generation_and_never_combines_with_generation():
    args = minimax.parse_args(["5", "10", ".2", "--director-only"])
    assert args.director_only
    assert args.test_prompt_generation

    with __import__("pytest").raises(SystemExit):
        minimax.parse_args(["5", "10", ".2", "--director-only", "--generate-prompts", "2"])


def test_director_only_saved_expansion_seeds_location_world_state(tmp_path):
    fixture_dir = (
        Path(__file__).parent
        / "acceptance"
        / "fixtures"
        / "tavern_run21_plan"
    )
    expanded_story = (fixture_dir / "expanded_story.txt").read_text(
        encoding="utf-8"
    )
    story_file = tmp_path / "story.txt"
    story_file.write_text("Amy works in a tavern.", encoding="utf-8")
    beats_file = tmp_path / "beats.txt"
    beats_file.write_text(
        (fixture_dir / "beats.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    arc_file = tmp_path / "story_arc.json"
    arc_file.write_text(
        (fixture_dir / "story_arc.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    expanded_story_file = tmp_path / "expanded_story.txt"
    expanded_story_file.write_text(expanded_story, encoding="utf-8")
    subjects_file = tmp_path / "subjects.txt"
    subjects_file.write_text("", encoding="utf-8")
    phrase_exclusions_file = tmp_path / "phrase_exclusions.txt"
    args = _args(
        director_only=True,
        segment_length=8.0,
        total_length=48.0,
        total_segments=6,
        refresh=999999,
        vision_continuity=0,
    )
    expected_location_state = {
        "location": {"name": "The Hearthside Tavern"},
        "anchors": [{"name": "stone counter", "type": "stone counter"}],
        "objects": [],
    }
    captured = {}

    class _StopAfterWorldStateSeed(Exception):
        pass

    def capture_seeded_state(state, *seed_args, **seed_kwargs):
        original_validate(state, *seed_args, **seed_kwargs)
        captured["location_state"] = copy.deepcopy(state["location_state"])
        captured["world_state"] = copy.deepcopy(state["world_state"])
        raise _StopAfterWorldStateSeed()

    def extract_story_locations(expanded, **_kwargs):
        captured["expanded_story_for_location"] = expanded
        return {
            "overall_location": "a medieval tavern",
            "starting_location": "The Hearthside Tavern",
        }

    location_description = {
        "text_description": "A medieval tavern with stone walls and a counter.",
        "location_state": expected_location_state,
    }
    original_validate = minimax.validate_subject_identity_state
    generate_beats_patcher = mock.patch.object(minimax, "load_or_generate_beats")
    expand_story_patcher = mock.patch.object(
        minimax, "generate_beats_via_story_expansion"
    )
    validate_beats_patcher = mock.patch.object(
        minimax, "_run_forward_beat_validation"
    )
    generate_beats = generate_beats_patcher.start()
    expand_story = expand_story_patcher.start()
    validate_beats = validate_beats_patcher.start()
    patches = [
        mock.patch.object(minimax, "parse_args", return_value=args),
        mock.patch.object(minimax, "configure_reference_image_overrides"),
        mock.patch.object(minimax, "configure_formatter"),
        mock.patch.object(minimax, "STORY_FILE", story_file),
        mock.patch.object(minimax, "BEATS_FILE", beats_file),
        mock.patch.object(minimax, "STORY_ARC_FILE", arc_file),
        mock.patch.object(minimax, "EXPANDED_STORY_FILE", expanded_story_file),
        mock.patch.object(minimax, "SUBJECT_DEFINITIONS_FILE", subjects_file),
        mock.patch.object(minimax, "PHRASE_EXCLUSIONS_FILE", phrase_exclusions_file),
        mock.patch.object(minimax, "load_beats", return_value=[f"Beat {i}" for i in range(1, 7)]),
        mock.patch.object(minimax, "load_canonical_data", return_value={}),
        mock.patch.object(minimax, "load_or_generate_character_canon", return_value={}),
        mock.patch.object(minimax, "canonicalize_defined_subject_wardrobes", return_value={}),
        mock.patch.object(minimax, "reset_prompt_history"),
        mock.patch.object(minimax, "save_generated_prompts_file"),
        mock.patch.object(minimax, "extract_story_locations", side_effect=extract_story_locations),
        mock.patch.object(minimax, "extract_static_setting", return_value="Static setting"),
        mock.patch.object(minimax, "refine_story_setting_spatially", return_value="Spatial setting"),
        mock.patch.object(minimax, "extract_story_setting_description", return_value=location_description),
        mock.patch.object(minimax, "extract_initial_location_subjects", return_value=[]),
        mock.patch.object(minimax, "extract_registered_subject_story_start_presence", side_effect=lambda state, *_a, **_k: state),
        mock.patch.object(minimax, "validate_subject_identity_state", side_effect=capture_seeded_state),
    ]
    for patcher in patches:
        patcher.start()
    try:
        with pytest.raises(_StopAfterWorldStateSeed):
            minimax._run_main(None)
    finally:
        for patcher in reversed(patches):
            patcher.stop()
        validate_beats_patcher.stop()
        expand_story_patcher.stop()
        generate_beats_patcher.stop()

    assert captured["expanded_story_for_location"] == expanded_story.strip()
    assert captured["location_state"] == expected_location_state
    assert {
        location["name"] for location in captured["world_state"]["locations"].values()
    } == {"The Hearthside Tavern"}
    assert {
        prop["name"] for prop in captured["world_state"]["props"].values()
    } == {"stone counter"}
    minimax.validate_world_state(captured["world_state"])
    generate_beats.assert_not_called()
    expand_story.assert_not_called()
    validate_beats.assert_not_called()


def test_director_raw_scene_retry_budget_is_five():
    assert minimax.DIRECTOR_RAW_SCENE_ATTEMPTS == 5
    assert minimax.DIRECTOR_RAW_SCENE_REPAIR_ATTEMPTS == 5


@pytest.mark.parametrize("count, render_enabled", [(1, False), (5, False), (1, True)])
def test_prompts_are_saved_automatically_before_rendering(count, render_enabled):
    args = _args(segment_length=8.0, total_segments=count, total_length=999.0,
                 test_prompt_generation=not render_enabled)
    saved_packages = []
    durations = []
    completed_world_states = []

    def load_text(path, required=True):
        del required
        if path == minimax.STORY_FILE:
            return "A story."
        if path == minimax.CANONICAL_DATA_FILE:
            return "Amy is female and 30-years-old."
        return ""

    def request_segment(bundle, _beats, _run_id, _run_config):
        durations.append(bundle["current_duration"])
        assert _run_config["total_segments"] == count
        assert _run_config["total_length"] == 8 * count
        payload = dict(bundle)
        payload["llm_result"] = {
            "detailed_description": "[Shot 1] A scene.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }
        payload["request1_result"] = {
            "state_actions": [],
            "state_actions_dry_run_accepted": True,
        }
        return payload

    def capture_completed_state(state, *args, **kwargs):
        del args, kwargs
        completed_world_states.append(copy.deepcopy(state["world_state"]))
        return {}

    def assemble_prompt(*args, **kwargs):
        assert kwargs["character_canon"]["characters"][0]["name"] == "Amy"
        return "H3 prompt"

    render = mock.patch("minimax.render_segment_with_retries",
                        side_effect=RuntimeError("stop at rendering") if render_enabled else None)
    stitch = mock.patch("minimax.stitch_videos")
    verify_images = mock.patch("minimax.verify_reference_images")
    verify_loras = mock.patch("minimax.verify_global_loras")
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
            return_value=("A story.", []),
        ),
        mock.patch("minimax.os.path.isfile", return_value=False),
        mock.patch("minimax.load_phrase_exclusions", return_value=[]),
        mock.patch("minimax.reset_prompt_history"),
        mock.patch("minimax.load_or_generate_beats", return_value=[]),
        mock.patch("minimax.load_story_arc", return_value={"phases": []}),
        mock.patch("minimax.save_generation_state"),
        mock.patch("minimax.validate_runtime_environment"),
        mock.patch("minimax.save_generated_prompts_file", side_effect=lambda payload: saved_packages.append(copy.deepcopy(payload))),
        mock.patch("minimax.request_segment_llm", side_effect=request_segment),
        mock.patch(
            "minimax.request_combined_continuity",
            return_value={"reduced_state": {}},
        ),
        mock.patch("minimax.build_h3_prompt", side_effect=assemble_prompt),
        mock.patch(
            "minimax.request_continuity_opening_state",
            return_value="OPENING",
        ),
        mock.patch(
            "minimax.record_completed_segment",
            side_effect=capture_completed_state,
        ),
        mock.patch(
            "minimax.commit_accepted_director_world_state",
            wraps=minimax.commit_accepted_director_world_state,
        ),
        verify_images,
        verify_loras,
        render,
        stitch,
    )
    verify_images_mock = verify_images.start()
    verify_loras_mock = verify_loras.start()
    render_mock = render.start()
    stitch_mock = stitch.start()
    world_state_commit_mock = patches[-5].start()
    for patcher in patches[:-5]:
        patcher.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as summary_executor, ThreadPoolExecutor(max_workers=1) as render_executor:
            if render_enabled:
                with pytest.raises(RuntimeError, match="stop at rendering"):
                    minimax._run_main(summary_executor, None, render_executor if render_enabled else None)
            else:
                minimax._run_main(summary_executor, None, render_executor if render_enabled else None)
    finally:
        for patcher in reversed(patches):
            patcher.stop()

    assert durations == [8.0] * count
    assert len(saved_packages[-1]["prompts"]) == count
    if not render_enabled:
        assert len(completed_world_states) == count
        assert world_state_commit_mock.call_count == count
    else:
        assert completed_world_states == []
        world_state_commit_mock.assert_not_called()
    assert saved_packages[-1]["prompts"][0]["h3_prompt"] == "H3 prompt"
    if render_enabled:
        render_mock.assert_called_once()
    else:
        render_mock.assert_not_called()
    stitch_mock.assert_not_called()
    verify_images_mock.assert_called_once()
    verify_loras_mock.assert_called_once()
