import copy
import json
from types import SimpleNamespace
from unittest import mock

import pytest
from PIL import Image

import minimax


@pytest.fixture(autouse=True)
def clean_optional_state():
    old = set(minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS)
    old_required = dict(minimax.REQUIRED_CONFIGURED_PICTURE_USES)
    minimax.REQUIRED_CONFIGURED_PICTURE_USES.clear()
    minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS.clear()
    yield
    minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS.clear()
    minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS.update(old)
    minimax.REQUIRED_CONFIGURED_PICTURE_USES.clear()
    minimax.REQUIRED_CONFIGURED_PICTURE_USES.update(old_required)


def workflows(optional=False):
    initial = minimax.load_workflow(minimax.INITIAL_WORKFLOW_FILE)
    append = minimax.load_workflow(minimax.APPEND_WORKFLOW_FILE)
    for workflow in (initial, append):
        _, target = minimax.find_workflow_node(workflow, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
        for number, title in enumerate(minimax.REFERENCE_IMAGE_NODE_NAMES, 1):
            node_id, node = minimax.find_workflow_node(workflow, title, 'test', 'LoadImage')
            node['inputs']['image'] = 'missing.png' if number == 1 else '0.jpg'
            if number == 1:
                node['_meta']['reference_optional'] = optional
                target['inputs']['ref_images.ref_image_0'] = [node_id, 0]
    return initial, append


def test_required_image_fails_with_actionable_path(tmp_path):
    initial, append = workflows()
    with pytest.raises(minimax.ReferenceAssetError, match=r'Required identity reference <Picture 1>.*missing.png.*--image1'):
        minimax.verify_reference_images(initial, append, str(tmp_path))


def test_optional_image_disconnects_bindings_and_identity_lookup(tmp_path):
    initial, append = workflows(optional=True)
    removed = minimax.verify_reference_images(initial, append, str(tmp_path))
    assert removed == {1}
    for workflow in (initial, append):
        _, target = minimax.find_workflow_node(workflow, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
        assert 'ref_images.ref_image_0' not in target['inputs']
    text = minimax.remove_optional_picture_bindings('<Subject 1> is Traveler, using <Picture 1>.', removed)
    assert minimax.parse_subject_registry(text)[1]['picture_ids'] == []
    assert minimax.subject_identity_reference_image({'name': 'Traveler', 'picture_id': 1}) == ''
    path = tmp_path / 'workflow.json'
    path.write_text(json.dumps(workflows(optional=True)[0]))
    reloaded = minimax.load_workflow(str(path))
    _, target = minimax.find_workflow_node(reloaded, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
    assert 'ref_images.ref_image_0' not in target['inputs']


def test_append_asset_is_validated_even_when_initial_image_exists(tmp_path):
    initial, append = workflows()
    Image.new('RGB', (2, 2)).save(tmp_path / 'valid.png')
    _, node = minimax.find_workflow_node(initial, 'Reference Image 1', 'test', 'LoadImage')
    node['inputs']['image'] = 'valid.png'
    with pytest.raises(minimax.ReferenceAssetError, match='append workflow'):
        minimax.verify_reference_images(initial, append, str(tmp_path))


def test_main_missing_asset_stops_before_canon_or_any_expensive_dispatch(tmp_path):
    initial, append = workflows()
    with mock.patch.object(minimax, 'parse_args', return_value=SimpleNamespace()), \
         mock.patch.object(minimax, 'load_workflow', side_effect=[initial, append]), \
         mock.patch.object(minimax, 'COMFY_INPUT', str(tmp_path)), \
         mock.patch.object(minimax, 'ask_llm') as llm, \
         mock.patch.object(minimax, 'load_or_generate_character_canon') as canon, \
         mock.patch.object(minimax, 'validate_runtime_environment') as runtime:
        with pytest.raises(minimax.ReferenceAssetError):
            minimax._run_main(None)
    llm.assert_not_called()
    canon.assert_not_called()
    runtime.assert_not_called()


def test_valid_required_image_preserves_binding(tmp_path):
    initial, append = workflows()
    Image.new('RGB', (2, 2)).save(tmp_path / 'missing.png')
    assert minimax.verify_reference_images(initial, append, str(tmp_path)) == set()
    assert minimax.parse_subject_registry('<Subject 1> is Traveler, using <Picture 1>.')[1]['picture_ids'] == [1]


def test_saved_package_missing_job_identity_fails_before_any_render(tmp_path):
    payload = {
        'config': {'segment_length': 8, 'total_length': 8, 'megapixels': .3},
        'prompts': [{'segment': 1, 'h3_prompt': 'scene'}],
        'reference_jobs': [{'kind': 'character_reference',
                            'identity_source': {'kind': 'configured_picture', 'image_name': 'lost.png'}}],
    }
    with mock.patch.object(minimax, 'load_generated_prompts_file', return_value=payload), \
         mock.patch.object(minimax, 'preflight_reference_images', return_value=set()), \
         mock.patch.object(minimax, 'COMFY_INPUT', str(tmp_path)), \
         mock.patch.object(minimax, 'render_saved_reference_jobs') as render, \
         mock.patch.object(minimax, 'validate_runtime_environment') as runtime:
        with pytest.raises(minimax.ReferenceAssetError, match='Required saved identity image'):
            minimax.render_generated_prompts(SimpleNamespace())
    render.assert_not_called()
    runtime.assert_not_called()


def test_saved_optional_picture_removal_clears_prompt_and_binding_metadata():
    payload = {
        'config': {'segment_length': 8, 'total_length': 8, 'megapixels': .3},
        'prompts': [{'segment': 1, 'h3_prompt': 'Traveler matches <Picture 1>.',
                     'subject_definitions': '<Subject 1> is Traveler, using <Picture 1>.'}],
    }
    with mock.patch.object(minimax, 'load_generated_prompts_file', return_value=payload), \
         mock.patch.object(minimax, 'preflight_reference_images', return_value={1}), \
         mock.patch.object(minimax, 'validate_runtime_environment', side_effect=RuntimeError('stop after preflight')):
        with pytest.raises(RuntimeError, match='stop after preflight'):
            minimax.render_generated_prompts(SimpleNamespace())
    record = payload['prompts'][0]
    assert '<Picture 1>' not in record['h3_prompt']
    assert '<Picture 1>' not in record['subject_definitions']
    assert record['excluded_picture_ids'] == [1]


def test_optional_availability_preserves_authored_checkpoint_fingerprint():
    authored = '<Subject 1> is Traveler, using <Picture 1>.'
    available = minimax.build_run_config(8, 8, .3, 1, subject_definitions=authored)
    unavailable = minimax.build_run_config(
        8, 8, .3, 1,
        subject_definitions=minimax.remove_optional_picture_bindings(authored, {1}),
        authored_subject_definitions=authored,
    )
    assert unavailable['source_sha256'] == available['source_sha256']


@pytest.mark.parametrize('segment', [1, 2])
def test_optional_unavailable_reference_does_not_return_from_seed_or_resume_bindings(segment):
    authored = '<Subject 1> is Traveler, using <Picture 1>.'
    seed = minimax.authoritative_world_state_seed_from_subject_definitions(authored)
    state = minimax.seed_generation_world_state_subjects(minimax.empty_world_state('test'), seed, {})
    # Stored canonical identity is retained even when its external media disappears.
    assert next(iter(state['subjects'].values()))['identity']['picture_ids'] == [1]
    minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS.add(1)
    runtime = minimax.remove_optional_picture_bindings(authored, {1})
    definitions = minimax.world_state_subject_definitions(runtime, state)
    _, definitions, binding_state, snapshot = minimax.build_segment_reference_bindings(
        segment_number=segment, total_segments=6,
        detailed_description='[Shot 1] <Subject 1> Traveler waits.',
        subject_definitions=definitions, character_references={}, base_reference_count=0,
        binding_state={'current_bindings': [{'subject_id': 1, 'picture_number': 1}]},
    )
    prompt = minimax.build_h3_prompt(
        {'detailed_description': '[Shot 1] <Subject 1> Traveler waits.',
         'overall_soundscape': 'Room tone.', 'non_diegetic_music': 'N/A'},
        definitions, segment_number=segment,
        conditioning_mode='initial' if segment == 1 else 'continuation', world_state=state,
    )
    assert '<Picture 1>' not in prompt
    assert not snapshot['bindings']
    assert not binding_state['current_bindings']


def test_authored_identity_dependency_is_checked_even_when_disconnected(tmp_path):
    initial, _ = workflows()
    _, target = minimax.find_workflow_node(initial, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
    target['inputs'].pop('ref_images.ref_image_0', None)
    with mock.patch.object(minimax, 'load_workflow', return_value=initial), \
         mock.patch.object(minimax, 'COMFY_INPUT', str(tmp_path)):
        with pytest.raises(minimax.ReferenceAssetError, match='Required authored identity <Picture 1>'):
            minimax.verify_subject_identity_references('<Subject 1> is Traveler, using <Picture 1>.')


def test_main_disconnected_authored_identity_stops_before_canon(tmp_path):
    initial, _ = workflows()
    _, target = minimax.find_workflow_node(initial, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
    target['inputs'].pop('ref_images.ref_image_0', None)
    args = SimpleNamespace(segment_length=8, total_length=8, megapixels=.3, resume=1)
    def text(path, **kwargs):
        return '<Subject 1> is Traveler, using <Picture 1>.' if path == minimax.SUBJECT_DEFINITIONS_FILE else 'Traveler enters a hall.'
    with mock.patch.object(minimax, 'parse_args', return_value=args), \
         mock.patch.object(minimax, 'preflight_reference_images', return_value=set()), \
         mock.patch.object(minimax, 'load_workflow', return_value=initial), \
         mock.patch.object(minimax, 'load_text_file', side_effect=text), \
         mock.patch.object(minimax, 'COMFY_INPUT', str(tmp_path)), \
         mock.patch.object(minimax, 'ask_llm') as llm, \
         mock.patch.object(minimax, 'load_or_generate_character_canon') as canon:
        with pytest.raises(minimax.ReferenceAssetError, match='Required authored identity'):
            minimax._run_main(None)
    llm.assert_not_called()
    canon.assert_not_called()


def test_missing_optional_use_cannot_disconnect_required_use_of_same_picture(tmp_path):
    initial, append = workflows(optional=True)
    _, node = minimax.find_workflow_node(append, 'Reference Image 1', 'test', 'LoadImage')
    node['_meta']['reference_optional'] = False
    node['inputs']['image'] = 'valid.png'
    Image.new('RGB', (2, 2)).save(tmp_path / 'valid.png')
    _, target = minimax.find_workflow_node(append, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
    connection = list(target['inputs']['ref_images.ref_image_0'])
    with pytest.raises(minimax.ReferenceAssetError, match='append workflow requires that Picture'):
        minimax.verify_reference_images(initial, append, str(tmp_path))
    assert target['inputs']['ref_images.ref_image_0'] == connection
    assert not minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS


def test_disconnected_optional_identity_cannot_remove_required_append_picture(tmp_path):
    initial, append = workflows(optional=True)
    _, initial_target = minimax.find_workflow_node(initial, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
    initial_target['inputs'].pop('ref_images.ref_image_0', None)
    _, node = minimax.find_workflow_node(append, 'Reference Image 1', 'test', 'LoadImage')
    node['_meta']['reference_optional'] = False
    node['inputs']['image'] = 'valid.png'
    Image.new('RGB', (2, 2)).save(tmp_path / 'valid.png')
    _, target = minimax.find_workflow_node(append, minimax.INITIAL_REFERENCE_CONDITIONING_NODE_NAME, 'test')
    connection = list(target['inputs']['ref_images.ref_image_0'])
    assert minimax.verify_reference_images(initial, append, str(tmp_path)) == set()
    with mock.patch.object(minimax, 'load_workflow', return_value=initial), \
         mock.patch.object(minimax, 'COMFY_INPUT', str(tmp_path)):
        with pytest.raises(minimax.ReferenceAssetError, match='append workflow requires that Picture'):
            minimax.verify_subject_identity_references('<Subject 1> is Traveler, using <Picture 1>.')
    assert target['inputs']['ref_images.ref_image_0'] == connection
    assert not minimax.UNAVAILABLE_OPTIONAL_PICTURE_IDS
