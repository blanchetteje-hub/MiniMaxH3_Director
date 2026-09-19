from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


DEFAULT_URL = "http://127.0.0.1:1234/v1/chat/completions"
BENCHMARK_SEED = 42
DEFAULT_MODEL = "minstral-3-14b-instruct-2512-absolute-heresy"


# Settings that were previously hard-coded in call_llama(). Values set to None
# use the llama.cpp/server default and are omitted from the request payload.
MINSTRAL_24B_SETTINGS = {
  "temperature": 0,
  "seed": BENCHMARK_SEED,
  "repeat_penalty": 1.15,
  "top_p": None,
  "top_k": None,
  "min_p": None,
  "thinking": "off",
  "chat_template": "built-in",
  "jinja": True,
  "context": 4096,
  "user_prompt_only": False,
  "stream": False
}


QWEN38_27B_SETTINGS = {
    "temperature": 0,
    "seed": BENCHMARK_SEED,
    "repeat_penalty": 1.15,
    "top_p": None,
    "top_k": None,
    "min_p": None,
    "thinking": "off",
    "chat_template": "built-in",
    "jinja": True,
    "context": 4096,
    "user_prompt_only": True,
    "stream": False,
}


class LLMError(RuntimeError):
    pass


def get_model_settings(model: str | None = None) -> dict[str, object]:
    """Return a copy of the benchmark settings for the selected model."""
    model = model or os.environ.get("H3_LLM_MODEL", DEFAULT_MODEL)
    profile = (
        QWEN38_27B_SETTINGS
        if "qwen" in model.casefold()
        else MINSTRAL_24B_SETTINGS
    )
    settings = dict(profile)
    settings["model"] = model
    settings["timeout"] = float(os.environ.get("H3_LLM_TIMEOUT", "120"))
    if "H3_LLM_TEMPERATURE" in os.environ:
        settings["temperature"] = float(os.environ["H3_LLM_TEMPERATURE"])
    return settings


def _strip_trailing_commas(text: str) -> str:
    """Match minimax.parse_llm_json_content's trailing-comma recovery."""
    cleaned = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            cleaned.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            cleaned.append(char)
            index += 1
            continue
        if char == ",":
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and text[next_index] in "}]":
                index += 1
                continue
        cleaned.append(char)
        index += 1
    return "".join(cleaned)


def _find_json_segment(text: str) -> str | None:
    """Find the first balanced JSON object or array."""
    for start_index, start_char in enumerate(text):
        if start_char not in "[{":
            continue
        stack = []
        in_string = False
        escaped = False
        for index in range(start_index, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char in "[{":
                stack.append(char)
            elif char in "]}":
                if not stack:
                    break
                expected = "]" if stack[-1] == "[" else "}"
                if char != expected:
                    break
                stack.pop()
                if not stack:
                    return text[start_index:index + 1]
    return None


def _parse_json_with_local_fixer(content: str) -> dict:
    """Local equivalent of minimax.parse_llm_json_content for this harness.

    The benchmark environment does not include minimax.py's application
    dependencies, so retain the parser's deterministic JSON recovery here.
    """
    if not isinstance(content, str):
        raise TypeError("LLM response content must be text.")
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline != -1:
            candidate = candidate[first_newline + 1:-3].strip()

    candidates = [candidate, _strip_trailing_commas(candidate)]
    segment = _find_json_segment(candidate)
    if segment is not None:
        candidates.extend([segment, _strip_trailing_commas(segment)])
    last_error = None
    for candidate_text in candidates:
        try:
            value = json.loads(candidate_text)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(value, dict):
            return value
        last_error = TypeError(
            f"Expected JSON object, got: {type(value).__name__}"
        )
    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("Invalid JSON", candidate, 0)


def _parse_json_with_fixer(content: str) -> dict:
    """Use minimax's JSON fixer when importable, otherwise use its local twin."""
    try:
        from minimax import parse_llm_json_content
    except (ImportError, ModuleNotFoundError):
        return _parse_json_with_local_fixer(content)

    value = parse_llm_json_content(content, repair_on_failure=True)
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object, got: {type(value).__name__}")
    return value


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        # Only malformed JSON is sent through the minimax-compatible fixer.
        try:
            return _parse_json_with_fixer(text)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMError(f"Invalid JSON from model: {text!r}") from exc

    if not isinstance(value, dict):
        raise LLMError(f"Expected JSON object, got: {type(value).__name__}")
    return value


def call_llama(messages: list[dict[str, str]], url: str | None = None) -> dict:
    url = url or os.environ.get("H3_LLM_URL", DEFAULT_URL)
    settings = get_model_settings()

    payload = {
        "model": settings["model"],
        "messages": messages,
        "temperature": settings["temperature"],
        "seed": settings["seed"],
        "stream": settings["stream"],
    }
    for parameter in ("repeat_penalty", "top_p", "top_k", "min_p"):
        value = settings[parameter]
        if value is not None:
            payload[parameter] = value

    # Qwen's built-in Jinja template reads this standard llama.cpp option.
    # The --jinja flag and context size are server launch settings, so they
    # remain in the profile rather than being sent as chat-completion fields.
    if settings["thinking"] in (False, "off"):
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=settings["timeout"]) as response:
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
