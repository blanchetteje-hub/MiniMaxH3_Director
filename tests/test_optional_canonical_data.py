from unittest import mock

import pytest

import minimax


@pytest.mark.parametrize('content', [None, '', '  \n\t ', 'Amy wears a red coat.'])
def test_optional_canonical_data_always_generates_fresh_canon(tmp_path, content):
    path = tmp_path / 'canonical_data.txt'
    if content is not None:
        path.write_text(content, encoding='utf-8')
    cache = tmp_path / 'character_canon.json'
    cache.write_text('stale cached character facts', encoding='utf-8')
    with mock.patch.object(minimax, 'CANONICAL_DATA_FILE', str(path)):
        assert minimax.load_canonical_data() == (content or '').strip()
        with mock.patch.object(minimax, 'ask_llm', return_value={'characters': [{'name': 'Amy', 'age': '30', 'clothing': 'red coat', 'gender': 'female', 'other_facts': []}]}) as llm:
            canon = minimax.load_or_generate_character_canon(story='Amy walks.', subject_definitions='<Subject 1> is Amy.', path=str(cache))
            assert canon['characters'][0]['name'] == 'Amy'
            llm.assert_called_once()
            assert llm.call_args.kwargs['history_metadata']['purpose'] == 'character_canon'
    assert 'red coat' in cache.read_text()


def test_generation_reaches_beats_without_canonical_data(tmp_path):
    story = tmp_path / 'story.txt'
    story.write_text('Amy opens a door.', encoding='utf-8')
    args = minimax.parse_args(['8', '1', '--generate-prompts', '1'])
    with mock.patch.multiple(minimax,
        STORY_FILE=str(story), SUBJECT_DEFINITIONS_FILE=str(tmp_path / 'subjects.txt'),
        CANONICAL_DATA_FILE=str(tmp_path / 'canonical_data.txt'),
    ), mock.patch.object(minimax, 'parse_args', return_value=args), \
       mock.patch.object(minimax, 'configure_formatter'), \
       mock.patch.object(minimax, 'reset_prompt_history'), \
       mock.patch.object(minimax, 'load_phrase_exclusions', return_value=[]), \
       mock.patch.object(minimax, 'ask_llm', return_value={'characters': [{'name': 'Amy', 'age': '30', 'clothing': 'red coat', 'gender': 'female', 'other_facts': []}]}) as llm, \
       mock.patch.object(minimax, 'save_character_canon', return_value={'fields': [], 'characters': []}) as save, \
       mock.patch.object(minimax, 'load_or_generate_beats', side_effect=RuntimeError('reached beats')) as beats:
        with pytest.raises(minimax.BeatGenerationError, match='reached beats'):
            minimax._run_main(None)
        beats.assert_called_once()
        llm.assert_called_once()
        save.assert_called_once()


def test_present_canonical_data_is_loaded(tmp_path):
    path = tmp_path / 'canonical_data.txt'
    path.write_text('Amy wears a red coat.\n', encoding='utf-8')
    assert minimax.load_canonical_data(str(path)) == 'Amy wears a red coat.'
