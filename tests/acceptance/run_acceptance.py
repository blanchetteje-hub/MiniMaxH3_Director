#!/usr/bin/env python3
"""Run the locked MiniMax H3 gold benchmark against the local LLM pipeline.

The runner executes in an isolated temporary copy of the repository so the
developer's real story.txt, story arc, beats, prompt history, and generation
state are never overwritten.

It deliberately does not grade semantic quality locally.  It captures the
generated artifacts in one acceptance_run.json for fuzzy review against the
gold benchmark by GPT-5.6 Sol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK = Path(__file__).with_name("gold") / "amy_zombie_house.json"
RESULTS_ROOT = Path(__file__).with_name("results")

GENERATED_FILES = (
    "story_arc.json",
    "story_arc.json.sha256",
    "beats.txt",
    "generation_state.json",
    "beat_validation_state.json",
    "prompt_history.txt",
)
GENERATED_DIRS = ("prompts",)

MODE_TO_PIPELINE = {
    "initial": "initial",
    "append": "continuation",
    "refresh": "clean_refresh",
}


def load_benchmark(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        benchmark = json.load(handle)

    if benchmark.get("status") != "locked_gold_baseline":
        raise ValueError("Acceptance benchmark is not marked locked_gold_baseline.")
    beats = benchmark.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ValueError("Acceptance benchmark must contain a non-empty beats list.")

    expected_numbers = list(range(1, len(beats) + 1))
    actual_numbers = [int(beat.get("beat", -1)) for beat in beats]
    if actual_numbers != expected_numbers:
        raise ValueError(
            f"Benchmark beats must be consecutive and one-based: {actual_numbers!r}"
        )

    lengths = {float(beat.get("length_seconds", 0)) for beat in beats}
    if len(lengths) != 1 or next(iter(lengths)) <= 0:
        raise ValueError(
            "Current MiniMax runtime requires one fixed positive segment length "
            "for the whole acceptance story."
        )

    for beat in beats:
        mode = str(beat.get("mode", "")).strip()
        if mode not in MODE_TO_PIPELINE:
            raise ValueError(f"Unsupported benchmark mode: {mode!r}")
        for field in ("must_happen", "must_not_happen", "expected_end_state"):
            if not isinstance(beat.get(field), list):
                raise ValueError(
                    f"Beat {beat['beat']} field {field!r} must be a list."
                )

    return benchmark


def infer_refresh_interval(beats: list[dict]) -> int | None:
    refresh_segments = [
        int(beat["beat"]) for beat in beats if beat.get("mode") == "refresh"
    ]
    if not refresh_segments:
        return None

    count = len(beats)
    for interval in range(2, count + 1):
        scheduled = [
            segment
            for segment in range(2, count + 1)
            if segment % interval == 0
        ]
        if scheduled == refresh_segments:
            return interval

    raise ValueError(
        "Gold refresh schedule cannot be represented by the current "
        "--refresh interval model. This is an architectural mismatch, not a "
        "benchmark error."
    )


def parse_h3_prompts(log_text: str) -> dict[int, str]:
    starts = re.compile(
        r"DIRECTOR REQUEST 2: H3 prompt - SEGMENT\s+(\d+)\s*$"
    )
    ends = re.compile(r"END H3 PROMPT - SEGMENT\s+(\d+)(?!\d)")
    prompts: dict[int, str] = {}
    active_segment: int | None = None
    buffer: list[str] = []

    for line in log_text.splitlines():
        start_match = starts.search(line)
        if start_match:
            active_segment = int(start_match.group(1))
            buffer = []
            continue

        end_match = ends.search(line)
        if end_match and active_segment is not None:
            if int(end_match.group(1)) != active_segment:
                raise ValueError("Mismatched H3 prompt markers in acceptance log.")
            prompts[active_segment] = "\n".join(buffer).strip()
            active_segment = None
            buffer = []
            continue

        if active_segment is not None:
            buffer.append(line)

    if active_segment is not None:
        raise ValueError(
            f"Unterminated H3 prompt marker for segment {active_segment}."
        )
    return prompts


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "results",
    }
    return {name for name in names if name in ignored}


def prepare_workspace(repo_root: Path, workspace: Path, benchmark: dict) -> None:
    shutil.copytree(repo_root, workspace, ignore=_copy_ignore)

    (workspace / "story.txt").write_text(
        benchmark["story_text"].rstrip() + "\n",
        encoding="utf-8",
    )
    input_subjects = benchmark.get("input_subjects", [])
    (workspace / "subjects.txt").write_text(
        "\n".join(str(line).rstrip() for line in input_subjects).rstrip() + "\n",
        encoding="utf-8",
    )

    for filename in GENERATED_FILES:
        path = workspace / filename
        if path.exists():
            path.unlink()
    for dirname in GENERATED_DIRS:
        path = workspace / dirname
        if path.exists():
            shutil.rmtree(path)


def git_revision(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def copy_artifact(workspace: Path, output_dir: Path, filename: str) -> str | None:
    source = workspace / filename
    if not source.exists():
        return None
    destination_dir = output_dir / "generated"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    shutil.copy2(source, destination)
    return str(destination.relative_to(output_dir))


def acceptance_child_env() -> dict[str, str]:
    """Force live MiniMax output through the acceptance runner's pipe."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Windows pipes otherwise inherit a legacy charmap encoding and can crash
    # on ordinary model punctuation such as a non-breaking hyphen.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def build_command(
    python_executable: str,
    benchmark: dict,
    image1: Path,
    model: str,
    megapixels: float,
    extra_args: list[str],
    planning_only: bool = False,
) -> tuple[list[str], int | None]:
    beats = benchmark["beats"]
    if planning_only:
        command = [
            python_executable,
            "minimax.py",
            "--generate-beats",
            str(len(beats)),
            "--model",
            model,
        ]
        command.extend(extra_args)
        return command, None

    segment_length = float(beats[0]["length_seconds"])
    total_length = segment_length * len(beats)
    refresh_interval = infer_refresh_interval(beats)

    command = [
        python_executable,
        "minimax.py",
        f"{segment_length:g}",
        f"{total_length:g}",
        f"{megapixels:g}",
        "--test-prompt-generation",
        "--vision-continuity",
        "0",
        "--model",
        model,
        "--image1",
        str(image1),
    ]
    # The application defaults to a refresh cadence of 4, so explicitly
    # override it even when the benchmark has no refresh beats.
    command.extend(
        ["--refresh", str(refresh_interval if refresh_interval is not None else 999999)]
    )
    command.extend(extra_args)
    return command, refresh_interval


def build_report(
    benchmark_path: Path,
    benchmark: dict,
    command: list[str],
    refresh_interval: int | None,
    exit_code: int,
    log_text: str,
    workspace: Path,
    output_dir: Path,
    planning_only: bool = False,
) -> dict:
    generated_prompts = {} if planning_only else parse_h3_prompts(log_text)
    generation_state = read_json(workspace / "generation_state.json") or {}
    segment_records = {
        int(record.get("segment_number")): record
        for record in generation_state.get("segments", [])
        if isinstance(record, dict) and record.get("segment_number") is not None
    }

    segments = []
    if not planning_only:
        for gold in benchmark["beats"]:
            number = int(gold["beat"])
            record = segment_records.get(number, {})
            expected_mode = gold["mode"]
            segments.append(
                {
                    "segment_number": number,
                    "gold_mode": expected_mode,
                    "pipeline_mode": MODE_TO_PIPELINE[expected_mode],
                    "gold_target": gold,
                    "generated_h3_prompt": generated_prompts.get(number),
                    "generated_request2_result": record.get("llm_result"),
                    "generated_continuity_state": record.get("continuity_state"),
                    "generated_subject_identity_snapshot": record.get(
                        "subject_identity_snapshot"
                    ),
                    "completed_beat_ids": record.get("completed_beat_ids"),
                }
            )

    artifact_paths = {}
    for filename in (
        "story_arc.json",
        "beats.txt",
        "generation_state.json",
        "prompt_history.txt",
        "subjects.txt",
        "story.txt",
    ):
        copied = copy_artifact(workspace, output_dir, filename)
        if copied:
            artifact_paths[filename] = copied

    if planning_only:
        expected_segments = 0
        captured_segments = []
        missing_segments = []
        planning_complete = bool(
            read_json(workspace / "story_arc.json")
            and (read_text(workspace / "beats.txt") or "").strip()
        )
    else:
        expected_segments = len(benchmark["beats"])
        captured_segments = sorted(generated_prompts)
        missing_segments = [
            number
            for number in range(1, expected_segments + 1)
            if number not in generated_prompts
        ]
        planning_complete = False

    return {
        "acceptance_report_version": 1,
        "story_id": benchmark["story_id"],
        "benchmark_version": benchmark.get("benchmark_version"),
        "benchmark_path": str(benchmark_path.relative_to(REPO_ROOT)),
        "benchmark_sha256": file_sha256(benchmark_path),
        "repository_revision": git_revision(REPO_ROOT),
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": command,
        "exit_code": exit_code,
        "capture_status": {
            "complete": planning_complete if planning_only else not missing_segments,
            "mode": "planning_only" if planning_only else "full_prompt_generation",
            "expected_segments": expected_segments,
            "captured_segments": captured_segments,
            "missing_segments": missing_segments,
        },
        "refresh_interval": refresh_interval,
        "grading": {
            "local_pass_fail": None,
            "grader": "GPT-5.6 Sol",
            "note": (
                "No semantic score is produced locally. Review each generated "
                "segment fuzzily against gold_target."
            ),
        },
        "generated_story_arc": read_json(workspace / "story_arc.json"),
        "generated_beats_text": read_text(workspace / "beats.txt"),
        "segments": segments,
        "artifacts": artifact_paths,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Run a locked MiniMax H3 acceptance story against the local LLM "
            "without touching the developer's active project files."
        )
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=DEFAULT_BENCHMARK,
        help="gold benchmark JSON (default: Amy zombie house)",
    )
    parser.add_argument(
        "--image1",
        type=Path,
        required=True,
        help="reference image for <Picture 1> / Amy",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="result directory; defaults under tests/acceptance/results/",
    )
    parser.add_argument("--model", default="mistral")
    parser.add_argument("--megapixels", type=float, default=0.5)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to run minimax.py",
    )
    parser.add_argument(
        "--extra-minimax-arg",
        action="append",
        default=[],
        help="extra argument passed through to minimax.py; repeat as needed",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="copy the isolated worktree into the result directory",
    )
    parser.add_argument(
        "--planning-only",
        action="store_true",
        help=(
            "run only ARC + BEATS generation in the locked workspace using "
            "minimax.py --generate-beats, then capture story_arc.json and beats.txt"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="prepare and print the command without contacting the local LLM",
    )
    return parser.parse_args(argv)


def _console_write_utf8_safe(text):
    """Echo child output without crashing on the host console encoding."""

    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe_text = str(text).encode(encoding, errors="replace").decode(
        encoding, errors="replace"
    )
    stream.write(safe_text)
    stream.flush()


def main(argv=None) -> int:
    args = parse_args(argv)
    benchmark_path = args.benchmark.resolve()
    image1 = args.image1.resolve()

    if not benchmark_path.is_file():
        raise FileNotFoundError(f"Benchmark not found: {benchmark_path}")
    if not image1.is_file():
        raise FileNotFoundError(f"Reference image not found: {image1}")
    if args.megapixels <= 0:
        raise ValueError("--megapixels must be greater than zero.")

    benchmark = load_benchmark(benchmark_path)

    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else (RESULTS_ROOT / f"{benchmark['story_id']}-{timestamp}").resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(benchmark_path, output_dir / "gold_benchmark.json")

    with tempfile.TemporaryDirectory(prefix="minimax-acceptance-") as temporary:
        workspace = Path(temporary) / "repo"
        prepare_workspace(REPO_ROOT, workspace, benchmark)
        command, refresh_interval = build_command(
            args.python,
            benchmark,
            image1,
            args.model,
            args.megapixels,
            list(args.extra_minimax_arg),
            planning_only=args.planning_only,
        )

        plan = {
            "story_id": benchmark["story_id"],
            "workspace": str(workspace),
            "output_dir": str(output_dir),
            "command": command,
            "refresh_interval": refresh_interval,
        }
        (output_dir / "run_plan.json").write_text(
            json.dumps(plan, indent=2) + "\n",
            encoding="utf-8",
        )

        print("Acceptance command:")
        print(" ".join(command))
        print(f"Isolated workspace: {workspace}")
        print(f"Results: {output_dir}")

        if args.dry_run:
            print("Dry run complete; local LLM was not contacted.")
            return 0

        log_path = output_dir / "run.log"
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=acceptance_child_env(),
            )
            assert process.stdout is not None
            for line in process.stdout:
                _console_write_utf8_safe(line)
                log_handle.write(line)
                log_handle.flush()
            exit_code = process.wait()

        log_text = log_path.read_text(encoding="utf-8")
        report = build_report(
            benchmark_path,
            benchmark,
            command,
            refresh_interval,
            exit_code,
            log_text,
            workspace,
            output_dir,
            planning_only=args.planning_only,
        )
        report_path = output_dir / "acceptance_run.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if args.keep_workdir:
            shutil.copytree(
                workspace,
                output_dir / "workdir",
                ignore=_copy_ignore,
            )

    print()
    print(f"Acceptance capture complete: {report_path}")
    print("Upload acceptance_run.json for GPT-5.6 Sol review.")
    capture_complete = bool(report["capture_status"]["complete"])
    if not capture_complete:
        if args.planning_only:
            print(
                "Planning-only capture is incomplete; story_arc.json and/or "
                "beats.txt was not produced. Include run.log for diagnosis."
            )
        else:
            missing = report["capture_status"]["missing_segments"]
            print(
                "Acceptance capture is structurally incomplete; missing H3 prompt "
                f"segment(s): {missing}. Include run.log for diagnosis."
            )
    if exit_code != 0:
        print(f"MiniMax exited with code {exit_code}; include run.log for diagnosis.")
    if exit_code != 0:
        return exit_code
    return 0 if capture_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
