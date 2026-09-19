from __future__ import annotations

from cases import ALL_CASES
from llama_client import LLMError, call_llama, get_model_settings, normalize_result
from prompt_under_test import build_messages


def main() -> None:
    train_slugs = {case.story_slug for case in ALL_CASES[:15 * 20]}
    cases = [
        case
        for case in ALL_CASES
        if case.story_slug in train_slugs and case.beat_number in (4, 8)
    ]
    settings = get_model_settings()
    repeat_caught = 0
    history_caught = 0
    false_positives = 0
    format_errors = 0

    for case in cases:
        try:
            raw = call_llama(build_messages(case, settings))
            valid, issue = normalize_result(raw)
        except LLMError as exc:
            format_errors += 1
            print(f"FORMAT {case.story_slug} beat {case.beat_number}: {exc}")
            continue

        caught = not valid
        if case.beat_number == 4:
            repeat_caught += caught
        else:
            history_caught += caught
        false_positives += valid
        if not caught:
            print(
                f"MISSED {case.story_slug} beat {case.beat_number}: "
                f"issue={issue!r}"
            )

    print(f"REPEAT caught / 15: {repeat_caught}")
    print(f"invented-history caught / 15: {history_caught}")
    print(f"false positives: {false_positives}")
    if format_errors:
        print(f"format errors: {format_errors}")

    expected = {"repeat": 15, "history": 15, "false_positives": 0}
    actual = {
        "repeat": repeat_caught,
        "history": history_caught,
        "false_positives": false_positives,
    }
    raise SystemExit(0 if actual == expected and not format_errors else 1)


if __name__ == "__main__":
    main()
