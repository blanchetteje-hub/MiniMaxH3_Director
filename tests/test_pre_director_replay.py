import json
from pathlib import Path
from unittest import mock

import pytest

import minimax


FIXTURE = (
    Path(__file__).parent
    / "acceptance"
    / "fixtures"
    / "tavern_job33_pre_director"
    / "replay.json"
)


def test_fixture_is_job33_pre_director_baseline_with_matching_request_hash():
    fixture = minimax.load_pre_director_replay_fixture(FIXTURE)
    state = fixture["pre_director"]["world_state"]
    assert fixture["provenance"]["completed_segments"] == 0
    assert minimax.world_state_sha256(state) == (
        "d9ba6db94ff5d5a9b4bd62a2742d41bd00013f43cad0c20242be92ced7449de0"
    )
    assert fixture["director_request1"]["metadata"]["opening_state_sha256"] == (
        minimax.world_state_sha256(state)
    )
    assert {subject["name"] for subject in state["subjects"].values()} == {
        "Amy", "Goblin", "Elf", "Dragon-shaped creature",
    }
    assert len(state["props"]) == 12
    assert len(state["locations"]) == 1
    assert state["subjects"]["subject_1"]["wardrobe"]["upper"]
    assert state["subjects"]["subject_goblin_a0f199af52d0"]["wardrobe"][
        "upper"
    ]
    assert state["subjects"]["subject_elf_a7b4191901e4"]["wardrobe"][
        "upper"
    ]
    assert state["subjects"]["subject_dragon_shaped_creature_91990debafe1"][
        "wardrobe"
    ]["other"] == "N/A"
    assert fixture["pre_director"]["subject_identity_lock"]["subjects"]["1"][
        "picture_ids"
    ] == [1]


def test_pre_director_replay_skips_upstream_llms_and_matches_request1(tmp_path):
    fixture = minimax.load_pre_director_replay_fixture(FIXTURE)
    args = minimax.parse_args([
        "8", "6", ".5",
        "--refresh", "999999",
        "--vision-continuity", "0",
        "--model", "gpt",
        "--pre-director-replay-fixture", str(FIXTURE),
    ])
    assert args.test_prompt_generation is True
    original_messages = fixture["director_request1"]["messages"]
    first_request = {}

    class _StopBeforeDirectorResponse(Exception):
        pass

    def capture_request(messages, **kwargs):
        first_request["messages"] = messages
        first_request["kwargs"] = kwargs
        raise _StopBeforeDirectorResponse()

    upstream_functions = (
        "load_or_generate_character_canon",
        "load_canonical_data",
        "load_beats",
        "load_story_arc",
        "load_or_generate_beats",
        "canonicalize_defined_subject_wardrobes",
        "extract_story_locations",
        "extract_static_setting",
        "refine_story_setting_spatially",
        "extract_story_setting_description",
        "extract_initial_location_subjects",
        "extract_registered_subject_story_start_presence",
        "prepare_segment_world_state_for_director",
    )
    patches = [
        mock.patch.object(minimax, "parse_args", return_value=args),
        mock.patch.object(minimax, "configure_reference_image_overrides"),
        mock.patch.object(minimax, "configure_formatter"),
        mock.patch.object(minimax, "reset_prompt_history"),
        mock.patch.object(minimax, "save_generated_prompts_file"),
        mock.patch.object(minimax, "save_generation_state"),
        mock.patch.object(minimax, "load_workflow", return_value={}),
        mock.patch.object(minimax, "copy_reference_image_inputs"),
        mock.patch.object(minimax, "verify_reference_images"),
        mock.patch.object(minimax, "verify_global_loras"),
        mock.patch.object(minimax, "ask_llm", side_effect=capture_request),
        mock.patch.object(minimax, "console_log"),
    ]
    patches.extend(
        mock.patch.object(minimax, name, side_effect=AssertionError(f"called {name}"))
        for name in upstream_functions
    )
    for patcher in patches:
        patcher.start()
    try:
        with pytest.raises(_StopBeforeDirectorResponse):
            minimax._run_main(None)
    finally:
        for patcher in reversed(patches):
            patcher.stop()

    assert first_request["messages"] == original_messages
    raw_schema = first_request["kwargs"]["response_format"]["json_schema"][
        "schema"
    ]
    assert "state_actions" not in raw_schema["properties"]
    assert "state_actions" not in raw_schema["required"]
    assert first_request["kwargs"]["history_metadata"]["segment"] == 1
    assert first_request["kwargs"]["history_metadata"]["opening_state_sha256"] == (
        fixture["provenance"]["opening_world_state_sha256"]
    )


def test_replay_option_allows_checkpoint_resume_and_remains_opt_in():
    assert minimax.parse_args(["8", "6", ".5"]).pre_director_replay_fixture is None
    args = minimax.parse_args([
        "8", "6", ".5", "--resume", "2",
        "--pre-director-replay-fixture", str(FIXTURE),
    ])
    assert args.pre_director_replay_fixture == str(FIXTURE.resolve())
    assert args.resume == 2
    assert args.test_prompt_generation is True
    with pytest.raises(SystemExit):
        minimax.parse_args([
            "8", "6", ".5", "--new",
            "--pre-director-replay-fixture", str(FIXTURE),
        ])


def test_replay_resume_uses_segment_checkpoint_without_reseeding_fixture():
    fixture = minimax.load_pre_director_replay_fixture(FIXTURE)
    args = minimax.parse_args([
        "8", "6", ".5",
        "--resume", "2",
        "--refresh", "999999",
        "--vision-continuity", "0",
        "--model", "gpt",
        "--pre-director-replay-fixture", str(FIXTURE),
    ])
    fixture_state = fixture["pre_director"]["world_state"]
    checkpoint_state = json.loads(json.dumps(fixture_state))
    checkpoint_state["revision"] += 1
    state = minimax.new_generation_state(fixture["run_config"])
    state["world_state"] = checkpoint_state
    state["metadata"] = json.loads(json.dumps(fixture["pre_director"]["metadata"]))
    state["location_state"] = json.loads(
        json.dumps(fixture["pre_director"]["location_state"])
    )
    state["reference_binding_state"] = json.loads(
        json.dumps(fixture["pre_director"]["reference_binding_state"])
    )
    state["character_reference_images"] = json.loads(
        json.dumps(fixture["pre_director"]["character_reference_images"])
    )
    restore = mock.Mock(return_value={
        "state": state,
        "completed_beat_ids": {1},
        "recent_results": [(1, {"detailed_description": "accepted segment 1"})],
        "video_paths": [],
        "previous_video_path": None,
    })

    class _ReachedRestoredCheckpoint(BaseException):
        pass

    def check_restored_world_state(base_definitions, restored_world_state):
        assert minimax.world_state_sha256(restored_world_state) == (
            minimax.world_state_sha256(checkpoint_state)
        )
        assert minimax.world_state_sha256(restored_world_state) != (
            minimax.world_state_sha256(fixture_state)
        )
        raise _ReachedRestoredCheckpoint()

    patches = [
        mock.patch.object(minimax, "parse_args", return_value=args),
        mock.patch.object(minimax, "configure_reference_image_overrides"),
        mock.patch.object(minimax, "configure_formatter"),
        mock.patch.object(minimax, "save_generated_prompts_file"),
        mock.patch.object(minimax, "load_generated_prompts_file", return_value={
            "prompts": [], "reference_jobs": [], "config": {},
        }),
        mock.patch.object(minimax, "save_generation_state"),
        mock.patch.object(minimax, "restore_generation_state", restore),
        mock.patch.object(
            minimax,
            "world_state_subject_definitions",
            side_effect=check_restored_world_state,
        ),
        mock.patch.object(minimax, "console_log"),
    ]
    for name in (
        "seed_generation_world_state_subjects",
        "seed_canonical_static_location_state",
        "seed_story_start_presence",
        "extract_registered_subject_story_start_presence",
    ):
        patches.append(
            mock.patch.object(
                minimax,
                name,
                side_effect=AssertionError(f"fixture opening was reseeded via {name}"),
            )
        )
    for patcher in patches:
        patcher.start()
    try:
        with pytest.raises(_ReachedRestoredCheckpoint):
            minimax._run_main(None)
    finally:
        for patcher in reversed(patches):
            patcher.stop()

    restore.assert_called_once()
    assert restore.call_args.args[0] == 2


def test_replay_fixture_rejects_a_worldstate_changed_after_capture(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["pre_director"]["world_state"]["revision"] += 1
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="opening hash"):
        minimax.load_pre_director_replay_fixture(path)
