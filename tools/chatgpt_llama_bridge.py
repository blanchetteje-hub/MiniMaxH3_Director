#!/usr/bin/env python3
"""Bridge ChatGPT-authored GitHub jobs to a local llama.cpp server.

The worker uses a dedicated git worktree/branch as a mailbox. ChatGPT writes
JSON jobs to bridge/jobs/ on that branch. This process polls, sends allowed
requests only to the configured local llama.cpp endpoint, writes results under
bridge/results/, then commits and pushes them.

No inbound port is opened. The bridge never executes arbitrary shell commands supplied by jobs and never
lets jobs choose the network endpoint. Local execution is limited to explicit
allowlisted test/acceptance job kinds.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import signal
import threading
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


DEFAULT_BRANCH = "gpt-runtime"
DEFAULT_ENDPOINT = "http://127.0.0.1:1234"
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024
DEFAULT_CODE_BRANCH = "gpt-arc-refresh"
ACCEPTANCE_MODEL = "gpt"
ACCEPTANCE_CODE_BRANCH = "gpt-arc-refresh"
DEFAULT_EXEC_WORKTREE_NAME = ".chatgpt_exec_worktree"

_ACTIVE_LOCAL_PROCESS = None


def _bridge_emergency_stop(_signum=None, _frame=None):
    """Hard-stop the bridge and any active allowlisted local child process."""

    process = _ACTIVE_LOCAL_PROCESS
    if process is not None and process.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                process.kill()
        except Exception:
            pass
    try:
        os.write(2, b"\nBridge emergency stop requested; exiting immediately.\n")
    finally:
        os._exit(130)


def install_bridge_interrupt_handlers():
    """Make Ctrl+C and Windows Ctrl+Q stop the bridge immediately."""

    signal.signal(signal.SIGINT, _bridge_emergency_stop)
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _bridge_emergency_stop)


def start_bridge_emergency_stop_listener():
    """On Windows, make Ctrl+Q work even while waiting on a child process."""

    if os.name != "nt":
        return None

    import msvcrt

    def watch_keyboard():
        while True:
            try:
                key = msvcrt.getwch()
            except (EOFError, OSError):
                return
            if key == "\x11":  # Ctrl+Q
                _bridge_emergency_stop()

    listener = threading.Thread(
        target=watch_keyboard,
        name="bridge-emergency-stop-listener",
        daemon=True,
    )
    listener.start()
    return listener


def run_git(args, cwd, *, check=True, capture=True, timeout=30):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=check,
            text=True,
            capture_output=capture,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"git command timed out after {timeout}s: git {' '.join(args)}"
        ) from error


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


def local_python(source_root: Path) -> Path:
    """Use the project's virtualenv Python when available."""

    candidates = [
        source_root / ".venv" / "Scripts" / "python.exe",
        source_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(sys.executable).resolve()


def ensure_exec_worktree(source_root: Path, branch: str = DEFAULT_CODE_BRANCH) -> Path:
    """Create/update a detached worktree for unattended test execution."""

    worktree = source_root / DEFAULT_EXEC_WORKTREE_NAME
    run_git(["fetch", "--no-tags", "origin", branch], source_root, timeout=30)
    if not worktree.exists():
        run_git(
            [
                "worktree",
                "add",
                "--detach",
                "--force",
                str(worktree),
                f"origin/{branch}",
            ],
            source_root,
            capture=False,
            timeout=30,
        )
    elif not (worktree / ".git").exists():
        raise RuntimeError(
            f"Execution worktree path exists but is not a git worktree: {worktree}"
        )
    run_git(
        ["reset", "--hard", f"origin/{branch}"],
        worktree,
        timeout=15,
    )
    return worktree


def run_local_process(command, cwd: Path, timeout: int) -> dict:
    """Run one allowlisted local process, stream output live, and capture it."""

    global _ACTIVE_LOCAL_PROCESS
    started = time.time()
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
        bufsize=1,
    )
    _ACTIVE_LOCAL_PROCESS = process
    output_lines = []

    def pump_output():
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            print(line, end="", flush=True)

    pump = threading.Thread(
        target=pump_output,
        name="bridge-local-process-output",
        daemon=True,
    )
    pump.start()

    timed_out = False
    try:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        pump.join(timeout=5)
    finally:
        _ACTIVE_LOCAL_PROCESS = None

    return {
        "command": [str(part) for part in command],
        "returncode": process.returncode,
        "stdout": "".join(output_lines),
        "stderr": "",
        "timed_out": timed_out,
        "timeout_seconds": int(timeout) if timed_out else None,
        "started_at": started,
        "finished_at": time.time(),
    }


def copy_acceptance_artifacts(exec_root: Path, result_dir: Path) -> dict:
    """Copy the newest acceptance report/log into the mailbox result."""

    results_root = exec_root / "tests" / "acceptance" / "results"
    candidates = sorted(
        (
            path for path in results_root.glob("amy_zombie_house-*")
            if path.is_dir()
            and (
                (path / "acceptance_run.json").is_file()
                or (path / "run.log").is_file()
            )
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("Acceptance runner produced no result directory or run.log.")
    latest = candidates[0]
    artifacts_dir = result_dir / "files"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    copied = {}
    for filename in ("acceptance_run.json", "run.log"):
        source = latest / filename
        if source.is_file():
            target = artifacts_dir / filename
            shutil.copy2(source, target)
            copied[filename] = str(target.relative_to(result_dir))
    copied["source_result_dir"] = str(latest.relative_to(exec_root))
    return copied


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


def _select_pytest_runner(source_root: Path) -> list[str]:
    """Choose the first fixed local Python/pytest runner that actually has pytest."""
    explicit_python = os.environ.get("MINIMAX_TEST_PYTHON", "").strip()
    windows_venv_python = source_root / ".venv" / "Scripts" / "python.exe"
    posix_venv_python = source_root / ".venv" / "bin" / "python"

    interpreter_candidates = []
    if explicit_python:
        interpreter_candidates.append(explicit_python)
    for candidate in (
        str(windows_venv_python) if windows_venv_python.exists() else "",
        str(posix_venv_python) if posix_venv_python.exists() else "",
        shutil.which("python") or "",
        shutil.which("python3") or "",
        shutil.which("py") or "",
        sys.executable,
    ):
        if candidate and candidate not in interpreter_candidates:
            interpreter_candidates.append(candidate)

    attempted = []
    for interpreter in interpreter_candidates:
        command = [interpreter, "-m", "pytest"]
        attempted.append(interpreter)
        try:
            probe = subprocess.run(
                [*command, "--version"],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return command

    pytest_executable = shutil.which("pytest")
    if pytest_executable:
        try:
            probe = subprocess.run(
                [pytest_executable, "--version"],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            probe = None
        if probe is not None and probe.returncode == 0:
            return [pytest_executable]

    raise RuntimeError(
        "No local Python environment with pytest was found. Checked: "
        + ", ".join(attempted or ["none"])
        + ". Set MINIMAX_TEST_PYTHON to a Python executable that has pytest."
    )


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
        selector = raw_path.strip()
        file_part, sep, node_part = selector.partition("::")
        path = safe_source_path(worktree, file_part)
        try:
            path.relative_to(tests_root)
        except ValueError as error:
            raise ValueError(
                f"run_tests may only execute paths under tests/: {raw_path!r}"
            ) from error
        if not path.exists():
            raise ValueError(f"Requested test path does not exist: {file_part!r}")
        normalized_selector = str(path.relative_to(worktree))
        if sep:
            normalized_selector += "::" + node_part
        normalized.append(normalized_selector)

    timeout = int(job.get("timeout_seconds") or 900)
    timeout = max(1, min(timeout, 1800))
    runner = _select_pytest_runner(source_root)
    command = [*runner, "-vv", *normalized]

    print(
        f"Running pytest job on {code_branch}: "
        + " ".join(normalized),
        flush=True,
    )
    completed = run_local_process(command, worktree, timeout)
    return {
        "code_branch": code_branch,
        "tests": normalized,
        "runner": runner,
        "returncode": completed["returncode"],
        "passed": completed["returncode"] == 0 and not completed["timed_out"],
        "stdout": completed["stdout"],
        "stderr": completed["stderr"],
        "timed_out": completed["timed_out"],
        "timeout_seconds": completed["timeout_seconds"],
        "started_at": completed["started_at"],
        "finished_at": completed["finished_at"],
    }



def execute_local_tests(job: dict, source_root: Path) -> dict:
    """Run only explicitly named unittest modules from the repository tests tree."""

    tests = job.get("tests")
    if tests is None:
        tests = [
            "tests.test_story_arc_structural_guarantees",
            "tests.test_refresh_context_latents",
            "tests.test_continuation_frame_anchor",
            "tests.test_reference_pruning",
        ]
    if not isinstance(tests, list) or not tests:
        raise ValueError("run_tests requires a non-empty tests array.")
    safe_tests = []
    for test in tests:
        value = str(test).strip()
        if not re.fullmatch(r"tests(?:\.[A-Za-z_][A-Za-z0-9_]*)+", value):
            raise ValueError(f"Unsupported unittest module: {value!r}")
        safe_tests.append(value)

    exec_root = ensure_exec_worktree(source_root)
    python = local_python(source_root)
    return run_local_process(
        [python, "-m", "unittest", *safe_tests],
        exec_root,
        timeout=int(job.get("timeout_seconds") or 900),
    )


def _find_lms_cli() -> str | None:
    """Return the LM Studio CLI path when it is installed."""

    found = shutil.which("lms")
    if found:
        return found

    executable_names = (
        ("lms.exe", "lms.cmd", "lms")
        if os.name == "nt"
        else ("lms",)
    )
    for name in executable_names:
        candidate = Path.home() / ".lmstudio" / "bin" / name
        if candidate.is_file():
            return str(candidate)
    return None


def start_lmstudio_developer_log(result_dir: Path) -> dict:
    """Capture LM Studio model input/output + stats for one bridge run."""

    artifacts_dir = result_dir / "files"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifacts_dir / "developer_log.jsonl"
    stderr_path = artifacts_dir / "developer_log.stderr.log"

    cli = _find_lms_cli()
    if cli is None:
        log_path.write_text(
            json.dumps({
                "bridge_log_capture_error": (
                    "LM Studio CLI 'lms' was not found; developer log capture "
                    "could not start."
                )
            }, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {
            "process": None,
            "log_path": log_path,
            "stderr_path": stderr_path,
            "stdout_handle": None,
            "stderr_handle": None,
        }

    stdout_handle = log_path.open("wb")
    stderr_handle = stderr_path.open("wb")
    command = [
        cli,
        "log",
        "stream",
        "--source",
        "model",
        "--filter",
        "input,output",
        "--json",
        "--stats",
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=result_dir,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        # Give the log subscriber a brief chance to attach before MiniMax starts.
        time.sleep(0.5)
        if process.poll() is not None:
            raise RuntimeError(
                f"LM Studio log stream exited immediately with "
                f"code {process.returncode}."
            )
    except Exception as error:
        stdout_handle.close()
        stderr_handle.close()
        log_path.write_text(
            json.dumps({
                "bridge_log_capture_error": str(error),
                "command": command,
            }, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {
            "process": None,
            "log_path": log_path,
            "stderr_path": stderr_path,
            "stdout_handle": None,
            "stderr_handle": None,
        }

    return {
        "process": process,
        "log_path": log_path,
        "stderr_path": stderr_path,
        "stdout_handle": stdout_handle,
        "stderr_handle": stderr_handle,
    }


def stop_lmstudio_developer_log(capture: dict, result_dir: Path) -> dict:
    """Stop one LM Studio log stream and return mailbox artifact paths."""

    process = capture.get("process")
    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                process.kill()
            try:
                process.wait(timeout=5)
            except Exception:
                pass

    for key in ("stdout_handle", "stderr_handle"):
        handle = capture.get(key)
        if handle is not None and not handle.closed:
            handle.flush()
            handle.close()

    artifacts = {}
    for name, key in (
        ("developer_log.jsonl", "log_path"),
        ("developer_log.stderr.log", "stderr_path"),
    ):
        path = capture.get(key)
        if isinstance(path, Path) and path.is_file():
            artifacts[name] = str(path.relative_to(result_dir))
    return artifacts


def execute_acceptance(job: dict, source_root: Path, result_dir: Path) -> dict:
    """Run the fixed prompt-generation acceptance suite on one code branch."""

    code_branch = str(job.get("code_branch") or ACCEPTANCE_CODE_BRANCH).strip()
    if code_branch != ACCEPTANCE_CODE_BRANCH:
        raise ValueError(
            f"Acceptance jobs must run on {ACCEPTANCE_CODE_BRANCH!r}; "
            f"got {code_branch!r}."
        )
    model = str(job.get("model") or ACCEPTANCE_MODEL).strip()
    if model != ACCEPTANCE_MODEL:
        raise ValueError(
            f"Acceptance jobs must use the {ACCEPTANCE_MODEL!r} baseline; "
            f"got {model!r}."
        )

    exec_root = ensure_exec_worktree(source_root, code_branch)
    python = local_python(source_root)
    image1_raw = str(job.get("image1") or "amy.jpg").strip()
    image1 = safe_source_path(source_root, image1_raw)
    if not image1.is_file():
        raise FileNotFoundError(f"Acceptance image not found: {image1}")

    command = [
        python,
        "tests/acceptance/run_acceptance.py",
        "--image1",
        image1,
        "--model",
        model,
    ]
    if bool(job.get("planning_only")):
        command.append("--planning-only")

    developer_capture = start_lmstudio_developer_log(result_dir)
    try:
        process = run_local_process(
            command,
            exec_root,
            timeout=int(job.get("timeout_seconds") or 3600),
        )
    finally:
        developer_artifacts = stop_lmstudio_developer_log(
            developer_capture,
            result_dir,
        )

    artifacts = copy_acceptance_artifacts(exec_root, result_dir)
    artifacts.update(developer_artifacts)
    process["artifacts"] = artifacts
    return process


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
    elif kind == "run_tests":
        result["test_run"] = run_pytest_job(source_root, job)
    elif kind == "run_acceptance":
        result["process"] = execute_acceptance(job, source_root, result_dir)
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

    process = result.get("process")
    if isinstance(process, dict) and process.get("returncode") not in (None, 0):
        result["local_process_failed"] = True

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
    """Make the isolated mailbox worktree exactly match the remote branch."""

    run_git(["fetch", "--no-tags", "origin", branch], worktree, timeout=30)
    run_git(
        ["reset", "--hard", f"origin/{branch}"],
        worktree,
        timeout=15,
    )


def commit_result(worktree: Path, branch: str, result_dir: Path, job_id: str) -> None:
    """Publish one result without losing it when ChatGPT updates the mailbox.

    The assistant may add another job to gpt-runtime while the local worker is
    finishing a long llama/acceptance run.  That makes a normal push race with
    the newer remote commit.  Rebase this result-only commit onto the latest
    mailbox tip and retry instead of letting the next poll reset/discard it and
    execute the expensive job again.
    """

    relative = result_dir.relative_to(worktree)
    result_json = relative / "result.json"
    run_git(["add", str(relative)], worktree)
    status = run_git(["status", "--porcelain"], worktree).stdout.strip()
    if not status:
        return
    run_git(["commit", "-m", f"Bridge result {job_id}"], worktree, capture=False)

    last_error = ""
    for attempt in range(1, 4):
        pushed = run_git(
            ["push", "origin", branch],
            worktree,
            check=False,
            timeout=60,
        )
        if pushed.returncode == 0:
            return

        last_error = (pushed.stderr or pushed.stdout or "").strip()
        run_git(["fetch", "--no-tags", "origin", branch], worktree, timeout=30)

        # Another worker/process may already have published this exact job.
        remote_has_result = run_git(
            [
                "cat-file",
                "-e",
                f"origin/{branch}:{result_json.as_posix()}",
            ],
            worktree,
            check=False,
            timeout=15,
        ).returncode == 0
        if remote_has_result:
            run_git(["reset", "--hard", f"origin/{branch}"], worktree, timeout=15)
            return

        try:
            run_git(
                ["rebase", f"origin/{branch}"],
                worktree,
                capture=False,
                timeout=60,
            )
        except (subprocess.CalledProcessError, RuntimeError):
            run_git(["rebase", "--abort"], worktree, check=False, timeout=15)
            raise

        print(
            f"Mailbox advanced while publishing {job_id}; "
            f"rebased result and retrying push ({attempt}/3).",
            flush=True,
        )

    raise RuntimeError(
        f"Could not publish bridge result {job_id} after 3 attempts: {last_error}"
    )


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
        kind = str(job.get("kind") or "llama_chat").strip()
        print(f"Processing bridge job: {job_id} ({kind})", flush=True)
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
        if str(job.get("kind") or "").strip() == "run_acceptance":
            print(
                "===========\n"
                "Pass back to GPT\n"
                "===========",
                flush=True,
            )
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
            print("Checking mailbox...", flush=True)
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
                flush=True,
            )
        except RuntimeError as error:
            print(f"bridge error: {error}", file=sys.stderr, flush=True)
        if args.once:
            return 0
        time.sleep(max(0.5, args.poll_seconds))


if __name__ == "__main__":
    install_bridge_interrupt_handlers()
    start_bridge_emergency_stop_listener()
    print("Bridge emergency stop: press Ctrl+C (or Ctrl+Q on Windows).")
    raise SystemExit(main())
