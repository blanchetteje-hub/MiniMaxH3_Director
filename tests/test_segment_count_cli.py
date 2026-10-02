import json
from unittest import mock

import pytest

import desktop_app
import minimax


def test_two_positionals_mean_five_full_eight_second_clips():
    args = minimax.parse_args(['8', '5'])
    assert args.segment_length == 8
    assert args.total_segments == 5
    assert args.total_length == 40
    assert args.megapixels == .5
    assert list(minimax.get_segments_to_generate(args.resume, args.total_segments)) == [1, 2, 3, 4, 5]


@pytest.mark.parametrize('count', ['0', '-1', '1.5', 'nan', 'inf', '5.0'])
def test_segment_count_requires_positive_integer(count):
    with pytest.raises(SystemExit):
        minimax.parse_args(['8', count])


@pytest.mark.parametrize('mode', [[], ['--director-only'], ['--test-prompt-generation']])
def test_count_semantics_in_all_positional_modes(mode):
    args = minimax.parse_args(['2.5', '3', '.2', *mode])
    assert args.total_segments == 3
    assert args.total_length == 7.5
    assert args.megapixels == .2


def test_prompt_count_defaults_and_explicit_match():
    args = minimax.parse_args(['--generate-prompts', '5'])
    assert args.total_segments == 5
    assert args.total_length == args.segment_length * 5
    args = minimax.parse_args(['8', '5', '--generate-prompts', '5'])
    assert args.total_length == 40
    with pytest.raises(SystemExit):
        minimax.parse_args(['8', '4', '--generate-prompts', '5'])


def test_beat_generation_sets_count_and_derived_duration():
    args = minimax.parse_args(['--generate-beats', '5', '8'])
    assert args.total_segments == 5
    assert args.total_length == 40


def test_saved_desktop_duration_is_migrated_to_count(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'segment_length': '8', 'total_length': '40'}))
    with mock.patch.object(desktop_app, 'SETTINGS_FILE', path):
        settings = desktop_app.MiniMaxBridge._load_settings()
    assert settings['total_segments'] == '5'
    assert 'total_length' not in settings


def test_desktop_rejects_fractional_segment_count():
    with pytest.raises(ValueError, match='Number of segments'):
        desktop_app.MiniMaxBridge._validate_settings({
            'segment_length': '8', 'total_segments': '1.5', 'megapixels': '.5'
        })


def test_no_music_cli_flag():
    assert minimax.parse_args(['8', '5', '--no-music']).no_music is True
    assert minimax.parse_args(['8', '5']).no_music is False
    assert minimax.build_run_config(8, 40, .5, 5, no_music=True)['no_music'] is True
