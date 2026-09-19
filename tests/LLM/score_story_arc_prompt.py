from __future__ import annotations

import argparse
import os
from collections import Counter

from tests.LLM.llama_client import LLMError, call_llama, get_model_settings
from tests.LLM.story_arc_cases import cases_for_split
from tests.LLM.story_arc_prompt_under_test import build_messages


BENCHMARK_URL = os.environ.get(
    "H3_LLM_URL",
    "http://127.0.0.1:1234/v1/chat/completions",
)


def normalize_arc_result(raw: dict) -> tuple[bool, list[str]]:
    if not isinstance(raw, dict):
        raise LLMError(f"Expected JSON object, got {type(raw).__name__}.")
    valid = raw.get("valid")
    issues = raw.get("issues")
    if not isinstance(valid, bool):
        raise LLMError(f"'valid' must be boolean: {raw!r}")
    if not isinstance(issues, list) or any(
        not isinstance(issue, str) or not issue.strip()
        for issue in issues
    ):
        raise LLMError(f"'issues' must be an array of non-empty strings: {raw!r}")
    issues = [" ".join(issue.split()) for issue in issues]
    if valid != (not issues):
        raise LLMError(
            "'valid' must be true exactly when the issues array is empty: "
            f"{raw!r}"
        )
    return valid, issues


def run_case(case, url):
    try:
        settings = get_model_settings()
        raw = call_llama(build_messages(case, settings), url=url)
        valid, issues = normalize_arc_result(raw)
        return case, valid, issues, None
    except LLMError as exc:
        return case, None, None, exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=("smoke", "train", "holdout", "all"),
        default="smoke",
    )
    parser.add_argument(
        "--failures",
        type=int,
        default=100,
        help="Maximum failure details to print.",
    )
    args = parser.parse_args()

    cases = cases_for_split(args.split)
    correct = 0
    format_errors = 0
    false_negatives = []
    false_positives = []
    failures = []
    diagnostic_counts = Counter()

    for index, case in enumerate(cases, start=1):
        case, valid, issues, error = run_case(case, BENCHMARK_URL)
        if error is not None:
            format_errors += 1
            failures.append((case, None, f"LLM/format error: {error}"))
            print(
                f"[{index:03d}/{len(cases)}] FORMAT "
                f"{case.case_id} ({case.beat_count} beats)"
            )
            continue

        passed = valid == case.expected_valid
        correct += passed
        if not passed:
            reason = "false positive" if case.expected_valid else "false negative"
            failures.append((case, issues, reason))
            if case.expected_valid:
                false_positives.append(case)
            else:
                false_negatives.append(case)

        for diagnostic in case.expected_issues:
            diagnostic_counts[diagnostic] += 1

        print(
            f"[{index:03d}/{len(cases)}] "
            f"{'PASS' if passed else 'FAIL'} "
            f"{case.case_id} ({case.beat_count} beats)"
        )

    total = len(cases)
    broken = sum(not case.expected_valid for case in cases)
    valid_cases = total - broken

    print("\n=== STORY ARC VALIDATOR SCORE ===")
    print(f"Split:            {args.split}")
    print(f"Cases:            {total}")
    print(f"Accuracy:         {correct}/{total} ({correct / total:.1%})")
    print(
        f"False negatives:  {len(false_negatives)}/{broken} "
        f"({len(false_negatives) / broken:.1%})"
    )
    print(
        f"False positives:  {len(false_positives)}/{valid_cases} "
        f"({len(false_positives) / valid_cases:.1%})"
    )
    print(f"Format errors:    {format_errors}")

    if diagnostic_counts:
        print("\n=== EXPECTED DIAGNOSTIC METADATA ===")
        for diagnostic, count in sorted(diagnostic_counts.items()):
            print(f"{diagnostic:30s} {count:3d}")

    if failures:
        print(f"\n=== FAILURES ({len(failures)}) ===")
        for case, issues, reason in failures[:args.failures]:
            print(f"\n{case.case_id} / {case.story_title}")
            print(f"Theme:          {case.theme}")
            print(f"Beat count:     {case.beat_count}")
            print(f"Classification: {reason}")
            print(f"Expected valid: {case.expected_valid}")
            print(f"Diagnostics:    {case.expected_issues}")
            print(f"Model issues:   {issues!r}")

    raise SystemExit(0 if correct == total else 1)


if __name__ == "__main__":
    main()
