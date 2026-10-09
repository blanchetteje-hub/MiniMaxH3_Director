from unittest import mock

import pytest

import desktop_app
import minimax


EXPECTED_PROFILE_PURPOSES = {
    "creative": {
        "director_h3_soundscape",
        "director_h3_music",
    },
    "smart_creative": {
        "story_expansion",
        "character_canon",
        "story_subject_wardrobe_extract",
        "story_setting_spatial_refine",
        "macro_arc_create",
        "macro_arc_majority_tail_repair",
        "macro_arc_repair",
        "beat_generation",
        "beat_repair",
        "director_raw_scene",
    },
    "extractor": {
        "story_location_extract",
        "static_setting_extract",
        "beat_destination_presence_extract",
        "beat_finite_endpoint_extract",
        "accepted_beat_state_extract",
        "director_raw_scene_pronoun_resolution",
        "continuity_attachment_extract",
        "continuity_phase_2_h3_opening",
        "json_repair",
        "director_h3_formatter",
    },
    "smart_extractor": {
        "story_to_beats",
        "story_to_beats_repair",
        "story_setting_extract",
        "source_unit_terminal",
        "source_unit_hard_reset",
        "source_unit_split_gate",
        "source_unit_cut_choice",
        "source_unit_visible_responsibility",
        "source_unit_local_relation",
        "director_raw_scene_subject_resolution",
        "registered_subject_story_start_presence",
        "world_state_current_segment_subjects",
        "world_state_current_segment_props",
        "source_unit_state_effects",
        "macro_arc_validate",
        "macro_arc_majority_validate",
        "beat_validation",
        "beat_coherence_validation",
        "beat_instruction_review",
        "director_raw_scene_physical",
        "director_raw_scene_prop_state",
        "director_raw_scene_timing",
        "director_raw_scene_visible_subject_resolution",
        "director_raw_scene_coherence",
        "continuity_combined_reduced_state",
        "continuity_state_validation",
        "combined_continuity",
        "subject_continuity",
        "final_h3_action_preservation",
    },
}

PROFILE_CONSTANTS = {
    "creative": minimax.CREATIVE_LLM_SETTINGS,
    "smart_creative": minimax.SMART_CREATIVE_LLM_SETTINGS,
    "extractor": minimax.EXTRACTOR_LLM_SETTINGS,
    "smart_extractor": minimax.SMART_EXTRACTOR_LLM_SETTINGS,
}


def test_four_llm_profiles_are_immutable_and_keep_sampling_defaults():
    for obsolete in (
        "CREATIVE_GENERATION_LLM_SETTINGS",
        "DIRECTOR_RAW_SCENE_LLM_SETTINGS",
        "BEAT_WRITING_LLM_SETTINGS",
        "STORY_EXPANSION_LLM_SETTINGS",
        "STORY_TO_BEATS_LLM_SETTINGS",
        "MUSIC_GENERATION_LLM_SETTINGS",
        "SLIGHTLY_CREATIVE_LLM_SETTINGS",
        "DETERMINISTIC_ANALYSIS_LLM_SETTINGS",
        "LONG_CONTEXT_DETERMINISTIC_ANALYSIS_LLM_SETTINGS",
    ):
        assert not hasattr(minimax, obsolete)

    for profile in PROFILE_CONSTANTS.values():
        assert "context_token_budget" not in profile
        assert "max_output_tokens" not in profile
        with pytest.raises(TypeError):
            profile["temperature"] = 9

    for name in ("creative", "smart_creative"):
        profile = PROFILE_CONSTANTS[name]
        assert profile["temperature"] == 0.6
        assert profile["seed"] is None
        assert profile["top_p"] == 0.95
        assert profile["top_k"] == 0
        assert profile["min_p"] == 0.05
        assert profile["presence_penalty"] == 0.0
        assert profile["frequency_penalty"] == 0.0
        assert profile["repeat_penalty"] == 1.15

    assert minimax.CREATIVE_LLM_SETTINGS["reasoning_effort"] == "medium"
    assert minimax.CREATIVE_LLM_SETTINGS["thinking_budget_tokens"] == 256
    assert minimax.SMART_CREATIVE_LLM_SETTINGS["reasoning_effort"] == "high"
    assert minimax.SMART_CREATIVE_LLM_SETTINGS["thinking_budget_tokens"] == 1024

    for name in ("extractor", "smart_extractor"):
        profile = PROFILE_CONSTANTS[name]
        assert profile["temperature"] == 0
        assert profile["seed"] == minimax.BENCHMARK_SEED == 42
        assert profile["top_p"] is None
        assert profile["top_k"] is None
        assert profile["min_p"] is None
        assert profile["presence_penalty"] is None
        assert profile["frequency_penalty"] is None
        assert profile["repeat_penalty"] == 1.15

    assert minimax.EXTRACTOR_LLM_SETTINGS["reasoning_effort"] == "medium"
    assert minimax.EXTRACTOR_LLM_SETTINGS["thinking_budget_tokens"] == 256
    assert minimax.SMART_EXTRACTOR_LLM_SETTINGS["reasoning_effort"] == "high"
    assert minimax.SMART_EXTRACTOR_LLM_SETTINGS["thinking_budget_tokens"] == 1024


def test_purpose_routes_are_a_disjoint_exhaustive_partition_of_text_calls():
    actual = {name: set() for name in EXPECTED_PROFILE_PURPOSES}
    for purpose, profile in minimax.LLM_PURPOSE_PROFILES.items():
        profile_name = next(
            name for name, expected in PROFILE_CONSTANTS.items()
            if profile is expected
        )
        actual[profile_name].add(purpose)

    assert actual == EXPECTED_PROFILE_PURPOSES
    assert "visual_end_state" not in minimax.LLM_PURPOSE_PROFILES
    assert minimax.VISION_LLM_SETTINGS["max_output_tokens"] == 2500


@pytest.mark.parametrize(
    ("purpose", "profile_name"),
    [
        (purpose, profile_name)
        for profile_name, purposes in EXPECTED_PROFILE_PURPOSES.items()
        for purpose in sorted(purposes)
    ],
)
def test_ask_llm_routes_each_purpose_to_its_standard_profile(
    purpose,
    profile_name,
):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]
    }
    profile = PROFILE_CONSTANTS[profile_name]
    with (
        mock.patch.object(minimax.requests, "post", return_value=response) as post,
        mock.patch.object(minimax, "append_prompt_history"),
        mock.patch.object(minimax, "estimate_message_tokens", return_value=10),
        mock.patch.object(minimax, "generate_random_llm_seed", return_value=777) as seed,
    ):
        minimax.ask_llm(
            [{"role": "user", "content": "request"}],
            response_format=None,
            history_metadata={"purpose": purpose},
        )

    request = post.call_args.kwargs["json"]
    assert request["temperature"] == profile["temperature"]
    assert request["seed"] == (777 if profile["seed"] is None else 42)
    assert request["reasoning_effort"] == profile["reasoning_effort"]
    assert request["thinking_budget_tokens"] == profile["thinking_budget_tokens"]
    assert seed.call_count == (1 if profile["seed"] is None else 0)


def test_request_context_and_output_budgets_are_independent_of_profiles():
    assert minimax.LLM_PURPOSE_CONTEXT_TOKEN_BUDGETS == {
        "story_expansion": minimax.STORY_PIPELINE_CONTEXT_TOKEN_BUDGET,
        "story_to_beats": minimax.STORY_PIPELINE_CONTEXT_TOKEN_BUDGET,
        "story_to_beats_repair": minimax.STORY_PIPELINE_CONTEXT_TOKEN_BUDGET,
        "registered_subject_story_start_presence": minimax.STORY_PIPELINE_CONTEXT_TOKEN_BUDGET,
    }
    assert minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS["story_expansion"] == 12000
    assert minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS["story_to_beats"] == 4096
    assert minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS["director_h3_music"] == 512
    assert minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS["source_unit_state_effects"] == 2048
    assert minimax.LLM_DEFAULT_MAX_OUTPUT_TOKENS == 2048
    assert 1024 not in minimax.LLM_PURPOSE_MAX_OUTPUT_TOKENS.values()

    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]
    }
    with (
        mock.patch.object(minimax.requests, "post", return_value=response) as post,
        mock.patch.object(minimax, "append_prompt_history"),
        mock.patch.object(minimax, "estimate_message_tokens", return_value=9000),
        mock.patch.object(minimax, "generate_random_llm_seed", return_value=123),
    ):
        minimax.ask_llm(
            [{"role": "user", "content": "request"}],
            response_format=None,
            history_metadata={"purpose": "story_expansion"},
        )
        assert post.call_args.kwargs["json"]["max_tokens"] == 12000
        assert "context_token_budget" not in post.call_args.kwargs["json"]
        with pytest.raises(RuntimeError, match="Simplify the stage prompt"):
            minimax.ask_llm(
                [{"role": "user", "content": "request"}],
                response_format=None,
                history_metadata={"purpose": "story_location_extract"},
            )
        assert post.call_count == 1


def test_unknown_purpose_uses_extractor_profile_and_default_budgets():
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]
    }
    with (
        mock.patch.object(minimax.requests, "post", return_value=response) as post,
        mock.patch.object(minimax, "append_prompt_history"),
    ):
        minimax.ask_llm(
            [{"role": "user", "content": "request"}],
            response_format=None,
            history_metadata={"purpose": "unclassified_test"},
        )
    request = post.call_args.kwargs["json"]
    assert request["temperature"] == 0
    assert request["seed"] == 42
    assert request["reasoning_effort"] == "medium"
    assert request["thinking_budget_tokens"] == 256
    assert request["max_tokens"] == minimax.LLM_DEFAULT_MAX_OUTPUT_TOKENS == 2048


def test_cli_does_not_accept_runtime_llm_setting_overrides():
    args = minimax.parse_args(["8", "5"])
    assert not hasattr(args, "temp")
    with pytest.raises(SystemExit):
        minimax.parse_args(["8", "5", "--temp", "1.2"])


def test_desktop_does_not_validate_or_pass_saved_temperature():
    bridge = desktop_app.MiniMaxBridge()
    settings = dict(
        desktop_app.DEFAULT_SETTINGS,
        segment_length="8",
        total_segments="5",
        temp="not-a-number",
        beat_count="5",
        beat_length="8",
    )
    command = bridge.build_command(settings, action="generate")
    assert "--temp" not in command

    beat_command = bridge.build_command(settings, generate_beats=True)
    assert "--temp" not in beat_command
    assert "temp" not in desktop_app.DEFAULT_SETTINGS
