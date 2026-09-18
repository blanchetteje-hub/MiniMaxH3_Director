from __future__ import annotations

import argparse
import os
from collections import Counter

from cases import ALL_CASES
from llama_client import LLMError, call_llama, normalize_result
from prompt_under_test import build_messages
from skeptic_prompt import build_skeptic_messages


BENCHMARK_URL = os.environ.get(
    "H3_LLM_URL",
    "http://127.0.0.1:1234/v1/chat/completions",
)


def run_case(case, url, messages):
    try:
        raw = call_llama(messages, url=url)
        valid, issue = normalize_result(raw)
        return case, valid, issue, None
    except LLMError as exc:
        return case, None, None, exc


def run_lane(indexed_cases, url, message_builder):
    return [
        (index, *run_case(case, url, message_builder(case)))
        for index, case in indexed_cases
    ]


def choose_cases(split: str):
    train_slugs = {c.story_slug for c in ALL_CASES[:15 * 20]}

    if split == "smoke":
        return [c for c in ALL_CASES if c.beat_number in (1, 14)]
    if split == "train":
        return [c for c in ALL_CASES if c.story_slug in train_slugs]
    if split == "holdout":
        return [c for c in ALL_CASES if c.story_slug not in train_slugs]
    if split == "all":
        return list(ALL_CASES)
    raise ValueError(split)


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
        help="Maximum validity failure details to print.",
    )
    parser.add_argument(
        "--mode",
        choices=("primary", "primary+skeptic"),
        default="primary",
        help="Score the frozen primary alone or add the second-pass skeptic.",
    )
    args = parser.parse_args()

    cases = choose_cases(args.split)
    primary_correct = 0
    final_correct = 0
    format_errors = 0
    final_failures = []
    primary_false_negatives = []
    primary_false_positives = []
    final_false_negatives = []
    final_false_positives = []
    changed_cases = []
    skeptic_catches = []
    skeptic_rejections = []
    second_pass_calls = 0
    diagnostic_counts = Counter()

    results = run_lane(enumerate(cases, 1), BENCHMARK_URL, build_messages)

    for index, case, valid, issue, error in results:
        if error is not None:
            format_errors += 1
            final_failures.append((case, None, f"LLM/format error: {error}"))
            print(f"[{index:03d}/{len(cases)}] FORMAT {case.story_slug} beat {case.beat_number}")
            continue

        primary_valid = valid
        primary_issue = issue
        primary_correct += primary_valid == case.expected_valid
        if primary_valid != case.expected_valid:
            if case.expected_valid:
                primary_false_positives.append(case)
            else:
                primary_false_negatives.append(case)

        final_valid = primary_valid
        final_issue = primary_issue
        skeptic_valid = None
        skeptic_issue = None
        if args.mode == "primary+skeptic" and primary_valid:
            second_pass_calls += 1
            _, skeptic_valid, skeptic_issue, skeptic_error = run_case(
                case, BENCHMARK_URL, build_skeptic_messages(case)
            )
            if skeptic_error is not None:
                format_errors += 1
            elif not skeptic_valid:
                final_valid = False
                final_issue = skeptic_issue
                changed_cases.append(
                    (case, primary_valid, primary_issue, skeptic_valid, skeptic_issue)
                )
                if not case.expected_valid:
                    skeptic_catches.append(case)
                else:
                    skeptic_rejections.append(case)

        final_correct += final_valid == case.expected_valid
        if final_valid != case.expected_valid:
            reason = "false positive" if case.expected_valid else "false negative"
            final_failures.append((case, final_issue, reason))
            if case.expected_valid:
                final_false_positives.append(case)
            else:
                final_false_negatives.append(case)

        for diagnostic in case.expected_issues:
            diagnostic_counts[diagnostic] += 1

        print(
            f"[{index:03d}/{len(cases)}] "
            f"{'PASS' if final_valid == case.expected_valid else 'FAIL'} "
            f"{case.story_slug} beat {case.beat_number:02d}"
        )

    total = len(cases)
    broken = sum(not case.expected_valid for case in cases)
    valid_cases = total - broken
    print("\n=== SCORE ===")
    print(f"Split:                 {args.split}")
    print(f"Cases:                 {total}")
    print(f"Mode:                  {args.mode}")
    print(f"Primary accuracy:       {primary_correct}/{total} ({primary_correct / total:.1%})")
    print(f"Primary false negatives:{len(primary_false_negatives)}/{broken} ({len(primary_false_negatives) / broken:.1%})")
    print(f"Primary false positives:{len(primary_false_positives)}/{valid_cases} ({len(primary_false_positives) / valid_cases:.1%})")
    print(f"Final accuracy:         {final_correct}/{total} ({final_correct / total:.1%})")
    print(f"Final false negatives:  {len(final_false_negatives)}/{broken} ({len(final_false_negatives) / broken:.1%})")
    print(f"Final false positives:  {len(final_false_positives)}/{valid_cases} ({len(final_false_positives) / valid_cases:.1%})")
    print(f"Second-pass calls:      {second_pass_calls}")
    print(f"Primary FN caught:      {len(skeptic_catches)}")
    print(f"New valid beats rejected:{len(skeptic_rejections)}")
    print(f"Format errors:         {format_errors}")

    if diagnostic_counts:
        print("\n=== EXPECTED DIAGNOSTIC METADATA ===")
        for diagnostic, count in sorted(diagnostic_counts.items()):
            print(f"{diagnostic:14s} {count:3d}")

    if changed_cases:
        print(f"\n=== CHANGED BY SKEPTIC ({len(changed_cases)}) ===")
        for case, primary_valid, primary_issue, skeptic_valid, skeptic_issue in changed_cases:
            print(f"\n{case.story_title} / Beat {case.beat_number}")
            print(f"Expected valid: {case.expected_valid}")
            print(f"Primary:        {primary_valid} / {primary_issue!r}")
            print(f"Skeptic:        {skeptic_valid} / {skeptic_issue!r}")

    if final_failures:
        print(f"\n=== FINAL VALIDITY FAILURES ({len(final_failures)}) ===")
        for case, issue, reason in final_failures[:args.failures]:
            print(f"\n{case.story_title} / Beat {case.beat_number}")
            print(f"Classification: {reason}")
            print(f"Model issue:    {issue!r}")
            print(f"Expected valid: {case.expected_valid}")
            print(f"Diagnostics:    {case.expected_issues}")
            print(f"Candidate:      {case.candidate_beat}")

    raise SystemExit(0 if final_correct == total else 1)


if __name__ == "__main__":
    main()
