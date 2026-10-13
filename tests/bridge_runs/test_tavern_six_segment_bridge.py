import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_tavern_six_segment_live_pipeline(tmp_path):
    image_path = tmp_path / "amy_bridge_reference.jpg"
    Image.new("RGB", (512, 768), (128, 128, 128)).save(image_path, "JPEG")

    output_dir = tmp_path / "acceptance-output"
    command = [
        sys.executable,
        "tests/acceptance/run_acceptance.py",
        "--benchmark",
        "tests/acceptance/gold/amy_medieval_tavern_six.json",
        "--image1",
        str(image_path),
        "--output-dir",
        str(output_dir),
        "--model",
        "gpt",
        "--megapixels",
        "0.3",
        "--keep-workdir",
        "--extra-minimax-arg=--visual-style",
        "--extra-minimax-arg=Live-action cinematic",
        "--extra-minimax-arg=--no-music",
    ]
    env = os.environ.copy()
    env["MINIMAX_COMFYUI_OUTPUT"] = str((tmp_path / "comfy-output").resolve())
    env["MINIMAX_COMFYUI_INPUT"] = str((tmp_path / "comfy-input").resolve())
    env["MINIMAX_VIDEO_OUTPUT"] = str((tmp_path / "video-output").resolve())
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=1700,
        env=env,
    )

    print("\n=== BRIDGE ACCEPTANCE PROCESS OUTPUT ===")
    print(completed.stdout)

    files_to_dump = [
        output_dir / "acceptance_run.json",
        output_dir / "run.log",
        output_dir / "generated" / "prompt_history.txt",
        output_dir / "generated" / "generation_state.json",
        output_dir / "generated" / "character_canon.json",
        output_dir / "generated" / "beats.txt",
        output_dir / "generated" / "story_arc.json",
    ]
    for path in files_to_dump:
        print(f"\n=== ARTIFACT: {path.name} ===")
        if path.is_file():
            print(path.read_text(encoding="utf-8", errors="replace"))
        else:
            print("<missing>")

    report_path = output_dir / "acceptance_run.json"
    assert report_path.is_file(), "acceptance_run.json was not produced"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert completed.returncode == 0, (
        f"live six-segment run exited {completed.returncode}"
    )
    assert report["capture_status"]["complete"] is True
    assert report["capture_status"]["expected_segments"] == 6
    assert report["capture_status"]["captured_segments"] == [1, 2, 3, 4, 5, 6]
