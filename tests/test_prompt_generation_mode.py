from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import minimax


def _args(**overrides):
    values = {
        "generate_beats": None,
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


def test_prompt_generation_mode_skips_comfyui_and_stitching():
    args = _args()

    def load_text(path, required=True):
        del required
        if path == minimax.STORY_FILE:
            return "A story."
        return ""

    def request_segment(bundle, _beats, _run_id, _run_config):
        payload = dict(bundle)
        payload["llm_result"] = {
            "detailed_description": "[Shot 1] A scene.",
            "overall_soundscape": "Room tone.",
            "non_diegetic_music": "N/A",
            "completed_beat_ids": [],
        }
        return payload

    render = mock.patch("minimax.render_segment_with_retries")
    stitch = mock.patch("minimax.stitch_videos")
    verify_images = mock.patch("minimax.verify_reference_images")
    verify_loras = mock.patch("minimax.verify_global_loras")
    patches = (
        mock.patch("minimax.parse_args", return_value=args),
        mock.patch("minimax.configure_formatter"),
        mock.patch("minimax.configure_reference_image_overrides"),
        mock.patch("minimax.load_text_file", side_effect=load_text),
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
        mock.patch("minimax.build_h3_prompt", return_value="H3 prompt"),
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

    render_mock.assert_not_called()
    stitch_mock.assert_not_called()
    verify_images_mock.assert_called_once()
    verify_loras_mock.assert_called_once()
