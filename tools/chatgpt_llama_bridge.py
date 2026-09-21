#!/usr/bin/env python3
"""Bridge ChatGPT-authored GitHub jobs to a local llama.cpp server.

The worker uses a dedicated git worktree/branch as a mailbox. ChatGPT writes
JSON jobs to bridge/jobs/ on that branch. This process polls, sends allowed
requests only to the configured local llama.cpp endpoint, writes results under
bridge/results/, then commits and pushes them.

No inbound port is opened. The bridge never executes shell commands supplied by
jobs and never lets jobs choose the network endpoint.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


DEFAULT_BRANCH = "gpt-runtime"
DEFAULT_ENDPOINT = "http://127.0.0.1:8080"
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024


def run_git(args, cwd, *, check=True, capture=True):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )


def repo_root():
    result = run_git(["rev-parse", "--show-toplevel"], Path.cwd())
    return Path(result.stdout.strip()).resolve()


def ensure_worktree(source_root: Path, worktree: Path, branch: str) -> None:
    run_git(["fetch", "origin", branch], source_root)
    if worktree.exists():
        if not (worktree / ".git").exists():
            raise RuntimeError(
                f"Bridge worktree path exists but is not a git worktree: {worktree}"
            )
        return
    run_git(
        ["worktree", "add", "--force", str(worktree), branch],
        source_root,
        capture=False,
    )


def http_json(url: str, *, method="GET", payload=None, timeout=300):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def discover_model(endpoint: str) -> str:
    response = http_json(endpoint.rstrip("/") + "/v1/models")
    models = response.get("data") if isinstance(response, dict) else None
    if not isinstance(models, list) or not models:
        raise RuntimeError("llama.cpp /v1/models returned no models.")
    model_id = models[0].get("id") if isinstance(models[0], dict) else None
    if not isinstance(model_id, str) or not model_id.strip():
        raise RuntimeError("llama.cpp /v1/models returned an invalid model id.")
    return model_id.strip()


def safe_source_path(source_root: Path, raw_path: str) -> Path:
    candidate = (source_root / raw_path).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as error:
        raise ValueError(
            f"Requested file escapes the source repository: {raw_path!r}"
        ) from error
    return candidate


def collect_files(source_root: Path, patterns, destination: Path, max_bytes: int):
    collected = []
    destination.mkdir(parents=True, exist_ok=True)
    for pattern in patterns or []:
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        root_pattern = safe_source_path(source_root, pattern.strip())
        matches = glob.glob(str(root_pattern), recursive=True)
        for matched in matches:
            path = Path(matched).resolve()
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(source_root)
            except ValueError:
                continue
            size = path.stat().st_size
            if size > max_bytes:
                collected.append({
                    "path": str(relative),
                    "status": "skipped_too_large",
                    "size": size,
                })
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            collected.append({
                "path": str(relative),
                "status": "copied",
                "size": size,
            })
    return collected


def execute_job(job: dict, endpoint: str, source_root: Path, result_dir: Path,
                max_file_bytes: int) -> dict:
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("Bridge job is missing job_id.")
    kind = str(job.get("kind") or "llama_chat").strip()

    result = {
        "job_id": job_id,
        "kind": kind,
        "started_at": time.time(),
    }

    if kind == "llama_chat":
        messages = job.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("llama_chat job requires non-empty messages.")
        model = str(job.get("model") or "").strip() or discover_model(endpoint)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        for key in (
            "temperature",
            "top_p",
            "top_k",
            "min_p",
            "max_tokens",
            "seed",
            "repeat_penalty",
            "presence_penalty",
            "frequency_penalty",
        ):
            if key in job and job[key] is not None:
                payload[key] = job[key]
        result["request"] = payload
        result["response"] = http_json(
            endpoint.rstrip("/") + "/v1/chat/completions",
            method="POST",
            payload=payload,
            timeout=int(job.get("timeout_seconds") or 600),
        )
    elif kind == "collect_files":
        pass
    else:
        raise ValueError(f"Unsupported bridge job kind: {kind!r}")

    collect = job.get("collect")
    if collect:
        result["collected_files"] = collect_files(
            source_root,
            collect,
            result_dir / "files",
            max_file_bytes,
        )

    result["finished_at"] = time.time()
    return result


def processed_ids(results_root: Path) -> set[str]:
    if not results_root.exists():
        return set()
    return {
        path.name
        for path in results_root.iterdir()
        if path.is_dir() and (path / "result.json").is_file()
    }


def sync_branch(worktree: Path, branch: str) -> None:
    run_git(["pull", "--ff-only", "origin", branch], worktree)


def commit_result(worktree: Path, branch: str, result_dir: Path, job_id: str) -> None:
    relative = result_dir.relative_to(worktree)
    run_git(["add", str(relative)], worktree)
    status = run_git(["status", "--porcelain"], worktree).stdout.strip()
    if not status:
        return
    run_git(["commit", "-m", f"Bridge result {job_id}"], worktree, capture=False)
    run_git(["push", "origin", branch], worktree, capture=False)


def write_result(result_dir: Path, payload: dict) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    temp = result_dir / "result.json.tmp"
    final = result_dir / "result.json"
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, final)


def process_once(source_root: Path, worktree: Path, branch: str, endpoint: str,
                 max_file_bytes: int) -> int:
    sync_branch(worktree, branch)
    jobs_root = worktree / "bridge" / "jobs"
    results_root = worktree / "bridge" / "results"
    jobs_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)

    completed = processed_ids(results_root)
    handled = 0
    for job_path in sorted(jobs_root.glob("*.json")):
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job_id = str(job.get("job_id") or job_path.stem).strip()
        if job_id in completed:
            continue
        result_dir = results_root / job_id
        try:
            payload = execute_job(
                job,
                endpoint,
                source_root,
                result_dir,
                max_file_bytes,
            )
            payload["status"] = "ok"
        except Exception as error:
            payload = {
                "job_id": job_id,
                "status": "error",
                "error_type": type(error).__name__,
                "error": str(error),
                "finished_at": time.time(),
            }
        write_result(result_dir, payload)
        commit_result(worktree, branch, result_dir, job_id)
        completed.add(job_id)
        handled += 1
    return handled


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Poll GitHub jobs and execute them against local llama.cpp."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument(
        "--worktree",
        type=Path,
        default=None,
        help="mailbox worktree; default is <repo>/.chatgpt_bridge_worktree",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_BYTES / (1024 * 1024),
    )
    parser.add_argument("--once", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    source_root = repo_root()
    worktree = (
        args.worktree.resolve()
        if args.worktree is not None
        else source_root / ".chatgpt_bridge_worktree"
    )
    ensure_worktree(source_root, worktree, args.branch)

    endpoint = args.endpoint.rstrip("/")
    model = discover_model(endpoint)
    print(f"Bridge connected to llama.cpp: {endpoint}")
    print(f"Detected model: {model}")
    print(f"Mailbox branch: {args.branch}")
    print(f"Mailbox worktree: {worktree}")
    print("Waiting for ChatGPT jobs. Ctrl+C stops the bridge.")

    max_file_bytes = int(args.max_file_mb * 1024 * 1024)
    while True:
        try:
            handled = process_once(
                source_root,
                worktree,
                args.branch,
                endpoint,
                max_file_bytes,
            )
            if handled:
                print(f"Processed {handled} bridge job(s).")
        except urllib.error.URLError as error:
            print(f"llama.cpp connection error: {error}", file=sys.stderr)
        except subprocess.CalledProcessError as error:
            print(
                f"git bridge error ({error.returncode}): "
                f"{error.stderr or error.stdout or error}",
                file=sys.stderr,
            )
        if args.once:
            return 0
        time.sleep(max(0.5, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
