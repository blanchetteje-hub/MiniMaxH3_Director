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


BRIDGE_BUILD = "2026-09-25-run-tests-v3"
DEFAULT_BRANCH = "gpt-runtime"
DEFAULT_ENDPOINT = "http://127.0.0.1:1234"
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
    """Return the main repository root, even when launched inside a worktree."""
    result = run_git(["rev-parse", "--git-common-dir"], Path.cwd())
    common_git = Path(result.stdout.strip())
    if not common_git.is_absolute():
        common_git = (Path.cwd() / common_git).resolve()
    else:
        common_git = common_git.resolve()
    return common_git.parent


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


def ensure_code_test_worktree(source_root: Path, branch: str) -> Path:
    """Return a detached sibling worktree synced to one repo branch."""
    branch = str(branch or "").strip()
    if not branch:
        raise ValueError("run_tests requires code_branch.")
    run_git(["check-ref-format", "--branch", branch], source_root)
    run_git(["fetch", "origin", branch], source_root)
    run_git(["worktree", "prune"], source_root)

    safe_name = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in branch
    )

    common_raw = run_git(
        ["rev-parse", "--git-common-dir"],
        source_root,
    ).stdout.strip()
    common_git = Path(common_raw)
    if not common_git.is_absolute():
        common_git = (source_root / common_git).resolve()
    else:
        common_git = common_git.resolve()
    main_repo_root = common_git.parent
    worktree = (
        main_repo_root.parent
        / f"{main_repo_root.name}.chatgpt_test_{safe_name}"
    )
    remote_ref = f"origin/{branch}"

    if worktree.exists():
        if not (worktree / ".git").exists():
            shutil.rmtree(worktree)
            run_git(["worktree", "prune"], source_root)
        else:
            run_git(["checkout", "--detach", remote_ref], worktree)
            run_git(["reset", "--hard", remote_ref], worktree)
            run_git(["clean", "-fd"], worktree)
            return worktree

    run_git(
        ["worktree", "add", "--force", "--detach", str(worktree), remote_ref],
        source_root,
    )
    return worktree


def run_pytest_job(source_root: Path, job: dict) -> dict:
    """Run pytest only on repository test paths in a dedicated code worktree."""
    code_branch = str(job.get("code_branch") or "").strip()
    test_paths = job.get("tests")
    if not isinstance(test_paths, list) or not test_paths:
        raise ValueError("run_tests requires a non-empty tests array.")

    worktree = ensure_code_test_worktree(source_root, code_branch)
    normalized = []
    tests_root = (worktree / "tests").resolve()
    for raw_path in test_paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("run_tests test paths must be non-empty strings.")
        path = safe_source_path(worktree, raw_path.strip())
        try:
            path.relative_to(tests_root)
        except ValueError as error:
            raise ValueError(
                f"run_tests may only execute paths under tests/: {raw_path!r}"
            ) from error
        if not path.exists():
            raise ValueError(f"Requested test path does not exist: {raw_path!r}")
        normalized.append(str(path.relative_to(worktree)))

    timeout = int(job.get("timeout_seconds") or 900)
    timeout = max(1, min(timeout, 1800))

    explicit_python = os.environ.get("MINIMAX_TEST_PYTHON", "").strip()
    pytest_executable = shutil.which("pytest")
    windows_venv_python = source_root / ".venv" / "Scripts" / "python.exe"
    posix_venv_python = source_root / ".venv" / "bin" / "python"
    py_launcher = shutil.which("py")

    if explicit_python:
        command = [explicit_python, "-m", "pytest", "-q", *normalized]
    elif windows_venv_python.exists():
        command = [str(windows_venv_python), "-m", "pytest", "-q", *normalized]
    elif posix_venv_python.exists():
        command = [str(posix_venv_python), "-m", "pytest", "-q", *normalized]
    elif pytest_executable:
        command = [pytest_executable, "-q", *normalized]
    elif py_launcher:
        command = [py_launcher, "-m", "pytest", "-q", *normalized]
    else:
        command = [sys.executable, "-m", "pytest", "-q", *normalized]

    completed = subprocess.run(
        command,
        cwd=worktree,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "code_branch": code_branch,
        "tests": normalized,
        "runner": command[:3],
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


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
    elif kind == "run_tests":
        result["test_run"] = run_pytest_job(source_root, job)
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
    """Reset the disposable mailbox worktree to the remote branch head.

    The mailbox contains only ChatGPT-authored jobs and bridge-authored results.
    If a local result was written or committed but not pushed before an
    interruption, discarding it is safe: the remote job still exists and will
    simply be processed again.
    """
    run_git(["fetch", "origin", branch], worktree)
    run_git(["reset", "--hard", f"origin/{branch}"], worktree)
    run_git(["clean", "-fd"], worktree)


def commit_result(worktree: Path, branch: str, result_dir: Path, job_id: str) -> None:
    relative = result_dir.relative_to(worktree)
    run_git(["add", str(relative)], worktree)
    status = run_git(["status", "--porcelain"], worktree).stdout.strip()
    if not status:
        return
    run_git(["commit", "-m", f"Bridge result {job_id}"], worktree, capture=False)

    # A new ChatGPT-authored job may land after the result commit but before
    # this push. Rebase the result commit onto the newest mailbox head and
    # retry instead of leaving the worktree permanently diverged.
    last_error = None
    for _attempt in range(5):
        try:
            run_git(["pull", "--rebase", "origin", branch], worktree)
            run_git(["push", "origin", branch], worktree, capture=False)
            return
        except subprocess.CalledProcessError as error:
            last_error = error
            time.sleep(0.5)
    raise last_error


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
    loaded_script_bytes = Path(__file__).resolve().read_bytes()
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
    print(f"Bridge build: {BRIDGE_BUILD}")
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

            current_script = Path(__file__).resolve()
            if current_script.read_bytes() != loaded_script_bytes:
                print("Bridge code changed during mailbox sync; restarting automatically.")
                os.execv(sys.executable, [sys.executable, *sys.argv])
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
