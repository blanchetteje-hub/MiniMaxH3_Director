from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


DEFAULT_URL = "http://127.0.0.1:1234/v1/chat/completions"
BENCHMARK_SEED = 42


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()

    # First try exact JSON.
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    # llama.cpp models sometimes wrap JSON in markdown or a sentence.
    # This fallback keeps formatting noise separate from semantic failures.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise LLMError(f"No JSON object found in model response: {text!r}")

    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError(f"Invalid JSON from model: {text!r}") from exc

    if not isinstance(value, dict):
        raise LLMError(f"Expected JSON object, got: {type(value).__name__}")
    return value


def call_llama(messages: list[dict[str, str]], url: str | None = None) -> dict:
    url = url or os.environ.get("H3_LLM_URL", DEFAULT_URL)
    model = os.environ.get(
        "H3_LLM_MODEL",
        "ministral-3-14b-instruct-2512-absolute-heresy",
    )
    timeout = float(os.environ.get("H3_LLM_TIMEOUT", "120"))
    temperature = float(os.environ.get("H3_LLM_TEMPERATURE", "0"))

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "seed": BENCHMARK_SEED,
        "repeat_penalty": 1.1,
        "top_p": 0.95,
        "min_p": 0.05,
        "stream": False,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(f"llama.cpp request failed: {exc}") from exc

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected endpoint response: {body!r}") from exc

    return _extract_json(text)


def normalize_result(raw: dict) -> tuple[bool, str]:
    if "valid" not in raw or "issue" not in raw:
        raise LLMError(f"Missing valid/issue fields: {raw!r}")

    valid = raw["valid"]
    issue = raw["issue"]

    if not isinstance(valid, bool):
        raise LLMError(f"'valid' must be boolean: {raw!r}")
    if not isinstance(issue, str):
        raise LLMError(f"'issue' must be a string: {raw!r}")

    return valid, issue.strip()
