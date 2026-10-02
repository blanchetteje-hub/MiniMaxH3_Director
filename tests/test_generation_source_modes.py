from unittest import mock

import pytest

import minimax


@pytest.mark.parametrize('source', ['--new', '--existing'])
@pytest.mark.parametrize('mode', [[], ['--generate-prompts', '5'], ['--generate-all']])
def test_source_modes_support_full_or_prompt_only_pipeline(source, mode):
    args = minimax.parse_args(['8', '5', source, *mode])
    assert args.new_run == (source == '--new')
    assert args.existing_beats == (source == '--existing')


@pytest.mark.parametrize('arguments', [
    ['8', '5', '--new', '--existing'],
    ['8', '5', '--new', '--resume', '2'],
    ['8', '5', '--new', '--repair', '2'],
    ['8', '5', '--new', '--director-only'],
    ['--generate-from-prompts', '--new'],
    ['--generate-from-prompts', '--existing'],
    ['--use-prompts', 'saved.txt', '--existing'],
    ['--generate-beats', '5', '8', '--existing'],
    ['--generate-prompts', '5', '--steps', '0'],
    ['--generate-prompts', '5', '--capture-h3-segment', '1', '--capture-h3-fixture', 'capture.json'],
    ['--generate-prompts', '5', '--capture-h3-validation-segment', '1'],
])
def test_invalid_source_and_diagnostic_combinations_are_rejected(arguments):
    with pytest.raises(SystemExit):
        minimax.parse_args(arguments)


def test_new_run_resets_planning_outputs_and_preserves_sources_and_media(tmp_path):
    names = ['beats.txt', 'story_arc.json', 'story_arc.json.sha256',
             'beat_validation_state.json', 'generation_state.json', 'generated_prompts.txt',
             'story.txt', 'subjects.txt', 'canonical_data.txt', 'old_video.mp4']
    for name in names:
        (tmp_path / name).write_text('original', encoding='utf-8')
    with mock.patch.multiple(minimax,
        BEATS_FILE=str(tmp_path / 'beats.txt'),
        STORY_ARC_FILE=str(tmp_path / 'story_arc.json'),
        GENERATION_STATE_FILE=str(tmp_path / 'generation_state.json'),
        GENERATED_PROMPTS_FILE=str(tmp_path / 'generated_prompts.txt'),
    ):
        minimax.prepare_new_generation()
        minimax.prepare_new_generation()  # Missing generated artifacts are fine.
    assert (tmp_path / 'beats.txt').read_text() == ''
    for name in names[1:6]:
        assert not (tmp_path / name).exists()
    for name in names[6:]:
        assert (tmp_path / name).read_text() == 'original'


def test_existing_beats_are_loaded_verbatim_without_regeneration(tmp_path):
    path = tmp_path / 'beats.txt'
    text = 'Amy opens a door.\nAmy walks outside.\n'
    path.write_text(text, encoding='utf-8')
    with mock.patch.object(minimax, 'generate_beats_via_story_expansion') as generate:
        beats = minimax.require_existing_beats(str(path), 2)
        assert len(beats) == 2
        with pytest.raises(minimax.BeatGenerationError, match='exactly 3 beats'):
            minimax.require_existing_beats(str(path), 3)
        assert path.read_text() == text
        generate.assert_not_called()


def test_missing_or_empty_existing_beats_never_generate(tmp_path):
    path = tmp_path / 'beats.txt'
    with pytest.raises(minimax.BeatGenerationError):
        minimax.require_existing_beats(str(path), 2)
    path.write_text('', encoding='utf-8')
    with pytest.raises(minimax.BeatGenerationError):
        minimax.require_existing_beats(str(path), 2)


@pytest.mark.parametrize('recovery, should_reset', [(None, True), (1, False), (3, False)])
def test_automatic_recovery_does_not_clear_new_run_again(recovery, should_reset):
    args = minimax.parse_args(['8', '5', '--new'])
    with mock.patch.object(minimax, 'parse_args', return_value=args), \
         mock.patch.object(minimax, 'configure_formatter'), \
         mock.patch.object(minimax, 'configure_reference_image_overrides'), \
         mock.patch.object(minimax, 'load_text_file', side_effect=lambda path, **kwargs: '' if path == minimax.SUBJECT_DEFINITIONS_FILE else 'A story.'), \
         mock.patch.object(minimax, 'load_canonical_data', return_value='Amy is an adult.'), \
         mock.patch.object(minimax, 'prepare_new_generation') as reset, \
         mock.patch.object(minimax, 'load_or_generate_character_canon', side_effect=RuntimeError('stop at LLM')):
        with pytest.raises(RuntimeError, match='stop at LLM'):
            minimax._run_main(None, recovery_resume_segment=recovery)
        assert reset.called == should_reset


def test_existing_prompt_generation_never_enters_beat_generation():
    args = minimax.parse_args(['8', '1', '--existing', '--generate-prompts', '1'])
    with mock.patch.object(minimax, 'parse_args', return_value=args), \
         mock.patch.object(minimax, 'configure_formatter'), \
         mock.patch.object(minimax, 'configure_reference_image_overrides'), \
         mock.patch.object(minimax, 'load_text_file', side_effect=lambda path, **kwargs: '' if path == minimax.SUBJECT_DEFINITIONS_FILE else 'A story.'), \
         mock.patch.object(minimax, 'load_canonical_data', return_value='Amy is an adult.'), \
         mock.patch.object(minimax, 'load_or_generate_character_canon', return_value={'fields': [], 'characters': []}), \
         mock.patch.object(minimax, 'require_existing_beats', return_value=['Amy walks.']) as load_existing, \
         mock.patch.object(minimax, 'reset_prompt_history'), \
         mock.patch.object(minimax, 'load_phrase_exclusions', return_value=[]), \
         mock.patch.object(minimax, 'load_story_arc', side_effect=RuntimeError('stop after beats')), \
         mock.patch.object(minimax, 'load_or_generate_beats') as generate:
        with pytest.raises(RuntimeError, match='stop after beats'):
            minimax._run_main(None)
        load_existing.assert_called_once_with(minimax.BEATS_FILE, 1)
        generate.assert_not_called()
