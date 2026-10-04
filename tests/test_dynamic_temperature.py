from unittest import mock

import pytest

import desktop_app
import minimax


@pytest.mark.parametrize('mode', [[], ['--generate-prompts', '5']])
def test_temperature_default_and_override(mode):
    assert minimax.parse_args(['8', '5', *mode]).temp == .4
    assert minimax.parse_args(['8', '5', '--temp', '1.2', *mode]).temp == 1.2
    assert minimax.parse_args(['--generate-beats', '5', '8', '--temp', '0']).temp == 0


@pytest.mark.parametrize('value', ['-1', 'nan', 'inf', '-inf', 'wrong'])
def test_temperature_rejects_invalid_values(value):
    with pytest.raises(SystemExit):
        minimax.parse_args(['8', '5', '--temp', value])


def test_only_story_request_uses_dynamic_temperature():
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        'choices': [{'message': {'content': '{"ok": true}'}, 'finish_reason': 'stop'}]
    }
    profiles = {
        'story_to_beats': minimax.STORY_TO_BEATS_LLM_SETTINGS,
        'character_canon': minimax.CREATIVE_GENERATION_LLM_SETTINGS,
        'director_raw_scene': minimax.CREATIVE_GENERATION_LLM_SETTINGS,
        'director_h3_music': minimax.MUSIC_GENERATION_LLM_SETTINGS,
        'beat_generation': minimax.BEAT_WRITING_LLM_SETTINGS,
        'continuity_state_validation': minimax.DETERMINISTIC_ANALYSIS_LLM_SETTINGS,
    }
    with mock.patch.dict(minimax.STORY_EXPANSION_LLM_SETTINGS), \
         mock.patch.object(minimax.requests, 'post', return_value=response) as post, \
         mock.patch.object(minimax, 'append_prompt_history'):
        minimax.configure_story_temperature(1.25)
        for purpose in ['story_expansion', *profiles]:
            minimax.ask_llm(
                [{'role': 'user', 'content': 'Write a scene.'}],
                response_format=None, history_metadata={'purpose': purpose},
            )
            expected = 1.25 if purpose == 'story_expansion' else profiles[purpose]['temperature']
            assert post.call_args.kwargs['json']['temperature'] == expected
        minimax.configure_story_temperature()
        assert minimax.STORY_EXPANSION_LLM_SETTINGS['temperature'] == .4


def test_run_configures_story_temperature_before_llm_calls():
    args = minimax.parse_args(['8', '5', '--temp', '1.1'])
    with mock.patch.dict(minimax.STORY_EXPANSION_LLM_SETTINGS), \
         mock.patch.object(minimax, 'parse_args', return_value=args), \
         mock.patch.object(minimax, 'configure_formatter'), \
         mock.patch.object(minimax, 'load_text_file', side_effect=RuntimeError('stop before story')):
        with pytest.raises(RuntimeError, match='stop before story'):
            minimax._run_main(None)
        assert minimax.STORY_EXPANSION_LLM_SETTINGS['temperature'] == 1.1


def test_gui_temperature_is_passed_for_full_prompts_and_beats():
    bridge = desktop_app.MiniMaxBridge()
    settings = dict(desktop_app.DEFAULT_SETTINGS, segment_length='8', total_segments='5',
                    temp='1.15', beat_count='5', beat_length='8')
    for operation in ('generate', 'prompts'):
        args = minimax.parse_args(bridge.build_command(settings, action=operation)[3:])
        assert args.temp == 1.15
    args = minimax.parse_args(bridge.build_command(settings, generate_beats=True)[3:])
    assert args.temp == 1.15
    command = bridge.build_command(dict(settings, generation_mode='render_only', temp='invalid'))
    assert '--temp' not in command
    assert desktop_app.DEFAULT_SETTINGS['temp'] == '0.4'


@pytest.mark.parametrize('value', ['-1', 'nan', 'inf', 'wrong', ''])
def test_gui_validates_temperature(value):
    settings = dict(desktop_app.DEFAULT_SETTINGS, segment_length='8', total_segments='5', temp=value)
    with pytest.raises(ValueError, match='Story temperature'):
        desktop_app.MiniMaxBridge().build_command(settings)
