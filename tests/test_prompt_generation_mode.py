from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import minimax
import pytest


def _args(**overrides):
    values = {
        "generate_beats": None,
        "generate_prompts": None,
        "generate_all": False,
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
    assert not minimax.parse_args(["5", "10", ".2"]).test_prompt_generation
    assert minimax.parse_args(
        ["5", "10", ".2", "--test-prompt-generation"]
    ).test_prompt_generation


def test_generate_all_uses_normal_video_positionals_without_comfyui():
    args = minimax.parse_args(["8", "8", ".5", "--generate-all"])
    assert args.generate_all
    assert args.segment_length == 8
    assert args.total_length == 64
    assert args.megapixels == 0.5


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


def test_director_raw_scene_retry_budget_is_five():
    assert minimax.DIRECTOR_RAW_SCENE_ATTEMPTS == 5


@pytest.mark.parametrize("count", [1, 5])
def test_prompt_generation_mode_skips_comfyui_and_stitching(count):
    args = _args(segment_length=8.0, total_segments=count, total_length=999.0)
    durations = []

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
        return payload

    def assemble_prompt(*args, **kwargs):
        assert kwargs["character_canon"]["characters"][0]["name"] == "Amy"
        return "H3 prompt"

    render = mock.patch("minimax.render_segment_with_retries")
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
        mock.patch("minimax.record_completed_segment", return_value={}),
        verify_images,
        verify_loras,
        render,
        stitch,
    )
    verify_images_mock = verify_images.start()
    verify_loras_mock = verify_loras.start()
    render_mock = render.start()
    stitch_mock = stitch.start()
    for patcher in patches[:-4]:
        patcher.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as summary_executor:
            minimax._run_main(summary_executor, None, None)
    finally:
        for patcher in reversed(patches):
            patcher.stop()

    assert durations == [8.0] * count
    render_mock.assert_not_called()
    stitch_mock.assert_not_called()
    verify_images_mock.assert_called_once()
    verify_loras_mock.assert_called_once()
