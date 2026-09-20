#!/usr/bin/env python3
"""Render deterministic MiniMax H3 prompt variants from one fixture."""

import argparse
import copy
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import minimax

try:
    from .harness import (
        VARIANT_NAMES,
        build_variant_prompts,
        load_fixture,
        prompt_sha256,
        resolve_fixture_path,
        review_template,
        write_json,
    )
except ImportError:  # Direct ``python tests/H3/run_prompt_experiment.py``.
    from harness import (
        VARIANT_NAMES,
        build_variant_prompts,
        load_fixture,
        prompt_sha256,
        resolve_fixture_path,
        review_template,
        write_json,
    )


def _safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "experiment"


def _preflight_fixture(fixture):
    render = fixture["render"]
    workflow_file = resolve_fixture_path(fixture, render.get("workflow_file"))
    if workflow_file and os.path.isfile(workflow_file):
        current_digest = minimax._sha256_file(workflow_file)
        expected = render.get("workflow_sha256")
        if expected and current_digest != expected:
            raise RuntimeError(
                "Workflow file changed since capture: "
                f"{workflow_file} (expected {expected}, got {current_digest})."
            )
    elif workflow_file:
        raise FileNotFoundError(f"Captured workflow file is missing: {workflow_file}")

    for key in ("previous_video_path", "refresh_frame_path"):
        path = resolve_fixture_path(fixture, render.get(key))
        if path and not os.path.isfile(path):
            raise FileNotFoundError(f"Fixture input is missing: {path}")


def _reference_overrides(fixture):
    overrides = {}
    workflow_inputs = fixture["render"].get("workflow_inputs") or {}
    for title, values in workflow_inputs.items():
        match = re.fullmatch(r"Reference Image (\d+)", str(title))
        if not match or not isinstance(values, dict):
            continue
        image = values.get("image")
        if image:
            overrides[int(match.group(1))] = str(image)
    return overrides


def _apply_reference_inputs(fixture, workflow):
    for title, values in (fixture["render"].get("workflow_inputs") or {}).items():
        if not str(title).startswith("Reference Image "):
            continue
        if not isinstance(values, dict) or "image" not in values:
            continue
        try:
            minimax.set_node_input(
                workflow,
                title,
                "image",
                values["image"],
                "H3 prompt experiment workflow",
                "LoadImage",
            )
        except RuntimeError:
            # A pruned reference node is intentionally disconnected by the
            # normal workflow preparation path; it is not a runner failure.
            continue


def _prepare_workflow(fixture, prompt, output_prefix):
    segment = fixture["segment"]
    render = fixture["render"]
    number = int(segment["number"])
    duration = float(render["duration"])
    segment_length = float(render.get("segment_length") or duration)
    megapixels = float(render.get("megapixels") or 0.2)
    steps = int(render["steps"])
    seed = render.get("seed")
    loras = copy.deepcopy(render.get("loras") or [])
    workflow_type = render["workflow_type"]
    previous_video = resolve_fixture_path(fixture, render.get("previous_video_path"))
    refresh_frame = resolve_fixture_path(fixture, render.get("refresh_frame_path"))

    if workflow_type == "initial":
        workflow = minimax.prepare_initial_workflow(
            duration,
            megapixels,
            prompt,
            number,
            steps=steps,
            loras=loras,
            noise_seed=seed,
            output_prefix=output_prefix,
        )
    elif workflow_type == "clean_refresh":
        if not refresh_frame:
            raise RuntimeError("A clean-refresh fixture needs refresh_frame_path.")
        workflow = minimax.prepare_refresh_workflow(
            duration,
            megapixels,
            prompt,
            refresh_frame,
            number,
            steps=steps,
            loras=loras,
            noise_seed=seed,
            output_prefix=output_prefix,
        )
    else:
        if not previous_video:
            raise RuntimeError("An append fixture needs previous_video_path.")
        workflow = minimax.prepare_append_workflow(
            duration,
            prompt,
            previous_video,
            number,
            steps=steps,
            loras=loras,
            noise_seed=seed,
            output_prefix=output_prefix,
            segment_length=segment_length,
        )

    _apply_reference_inputs(fixture, workflow)
    # The append preparer may normalize picture references.  The experiment's
    # prompt must still be exactly the variant text written next to the video.
    minimax.set_node_input(
        workflow,
        minimax.PROMPT_NODE_NAME,
        "text",
        prompt,
        "H3 prompt experiment workflow",
        "DPRandomGenerator",
    )
    return workflow


def run_experiment(fixture_path, output_dir, selected_variants=None):
    fixture = load_fixture(fixture_path)
    _preflight_fixture(fixture)
    variants = build_variant_prompts(fixture)
    selected = tuple(selected_variants or VARIANT_NAMES)
    unknown = set(selected) - set(VARIANT_NAMES)
    if unknown:
        raise ValueError(f"Unknown variants: {sorted(unknown)}")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_copy = output_dir / "fixture.json"
    if Path(fixture_path).resolve() != fixture_copy.resolve():
        shutil.copy2(fixture_path, fixture_copy)
    experiment_name = _safe_name(output_dir.name)
    original_overrides = minimax.REFERENCE_IMAGE_OVERRIDES
    captured_overrides = _reference_overrides(fixture)
    if captured_overrides:
        minimax.REFERENCE_IMAGE_OVERRIDES = captured_overrides

    manifest = {
        "schema_version": 1,
        "fixture": str(Path(fixture_path).resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nondeterminism_note": (
            "MiniMax H3/ComfyUI may remain nondeterministic even with a reused seed; "
            "human review is the source of truth."
        ),
        "variants": {},
    }
    try:
        for name in selected:
            value = variants[name]
            prompt_path = output_dir / f"{name}.txt"
            record = {"prompt_sha256": None, "status": None}
            if isinstance(value, dict) and value.get("status") == "skipped":
                reason = value.get("reason", "")
                prompt_path.write_text(
                    f"SKIPPED: {reason}\n",
                    encoding="utf-8",
                )
                record.update(
                    status="skipped",
                    reason=reason,
                    prompt_path=str(prompt_path),
                )
                manifest["variants"][name] = record
                continue

            prompt = str(value)
            prompt_path.write_text(prompt + "\n", encoding="utf-8")
            record["prompt_sha256"] = prompt_sha256(prompt)
            output_prefix = (
                f"video/h3_experiments/{experiment_name}/{name}"
            )
            try:
                workflow = _prepare_workflow(fixture, prompt, output_prefix)
                prompt_id = minimax.queue_workflow(workflow)
                result = minimax.wait_for_completion(prompt_id)
                video_path = minimax.get_video_path(result, workflow)
                record.update(
                    status="rendered",
                    prompt_path=str(prompt_path),
                    video_path=os.path.abspath(video_path),
                    prompt_id=prompt_id,
                )
            except Exception as error:  # Keep later variants usable.
                record.update(
                    status="error",
                    prompt_path=str(prompt_path),
                    error=f"{type(error).__name__}: {error}",
                )
            manifest["variants"][name] = record
    finally:
        minimax.REFERENCE_IMAGE_OVERRIDES = original_overrides

    write_json(output_dir / "review.json", review_template(selected))
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--variant",
        action="append",
        choices=VARIANT_NAMES,
        dest="variants",
        help="render only this variant; repeat to select multiple variants",
    )
    args = parser.parse_args(argv)
    if args.output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_dir = (
            Path(__file__).resolve().parent / "experiments" / f"experiment_{stamp}"
        )
    manifest = run_experiment(args.fixture, args.output_dir, args.variants)
    failed = [
        name for name, record in manifest["variants"].items()
        if record.get("status") == "error"
    ]
    print(f"Experiment outputs: {Path(args.output_dir).resolve()}")
    if failed:
        print("Variant failures: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
