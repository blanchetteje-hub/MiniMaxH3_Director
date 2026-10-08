from unittest import mock

import pytest

import desktop_app
import minimax


def test_llm_profiles_are_immutable():
    profiles = (
        minimax.VISION_LLM_SETTINGS,
        minimax.CREATIVE_GENERATION_LLM_SETTINGS,
        minimax.DIRECTOR_RAW_SCENE_LLM_SETTINGS,
        minimax.BEAT_WRITING_LLM_SETTINGS,
        minimax.STORY_EXPANSION_LLM_SETTINGS,
        minimax.STORY_TO_BEATS_LLM_SETTINGS,
        minimax.MUSIC_GENERATION_LLM_SETTINGS,
        minimax.SLIGHTLY_CREATIVE_LLM_SETTINGS,
        minimax.DETERMINISTIC_ANALYSIS_LLM_SETTINGS,
        minimax.SMART_EXTRACTOR_LLM_SETTINGS,
        minimax.LONG_CONTEXT_CREATIVE_GENERATION_LLM_SETTINGS,
        minimax.LONG_CONTEXT_DETERMINISTIC_ANALYSIS_LLM_SETTINGS,
    )
    for profile in profiles:
        with pytest.raises(TypeError):
            profile["temperature"] = 9
        with pytest.raises(TypeError):
            profile["max_output_tokens"] = 1


def test_cli_does_not_accept_runtime_llm_setting_overrides():
    args = minimax.parse_args(["8", "5"])
    assert not hasattr(args, "temp")
    with pytest.raises(SystemExit):
        minimax.parse_args(["8", "5", "--temp", "1.2"])


def test_story_expansion_uses_its_fixed_profile_temperature():
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "{\"ok\": true}"}, "finish_reason": "stop"}]
    }
    with mock.patch.object(minimax.requests, "post", return_value=response) as post, \
         mock.patch.object(minimax, "append_prompt_history"):
        minimax.ask_llm(
            [{"role": "user", "content": "Write a scene."}],
            response_format=None,
            history_metadata={"purpose": "story_expansion"},
        )
    assert post.call_args.kwargs["json"]["temperature"] == \
        minimax.STORY_EXPANSION_LLM_SETTINGS["temperature"]


def test_subject_resolution_uses_smart_profile_output_limit():
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]
    }
    with mock.patch.object(minimax.requests, "post", return_value=response) as post, \
         mock.patch.object(minimax, "append_prompt_history"):
        minimax.ask_llm(
            [{"role": "user", "content": "Classify the Subjects."}],
            response_format=None,
            history_metadata={"purpose": "director_raw_scene_subject_resolution"},
        )
    request = post.call_args.kwargs["json"]
    assert request["max_tokens"] == \
        minimax.SMART_EXTRACTOR_LLM_SETTINGS["max_output_tokens"] == 4096


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
