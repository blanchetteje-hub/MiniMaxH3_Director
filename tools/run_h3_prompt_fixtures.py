#!/usr/bin/env python3
"""Run final-H3 extractor validation against saved post-Director fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import minimax


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixtures", nargs="+", type=Path)
    parser.add_argument(
        "--model",
        choices=tuple(minimax.FORMATTER_CLASSES),
        default="gpt",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    minimax.configure_formatter(args.model)
    results = []
    failed_expectations = 0
    for path in args.fixtures:
        result = minimax.run_h3_prompt_validation_fixture(path)
        fixture = minimax.load_h3_prompt_validation_fixture(path)
        expected = fixture.get("expected") if isinstance(fixture, dict) else None
        if isinstance(expected, dict):
            expected_valid = expected.get("action_preservation_valid")
            if isinstance(expected_valid, bool):
                actual_valid = bool(result["action_preservation"]["valid"])
                result["expected_action_preservation_valid"] = expected_valid
                result["matches_expected"] = actual_valid == expected_valid
                if not result["matches_expected"]:
                    failed_expectations += 1
        results.append(result)

    print(json.dumps(
        {
            "fixture_count": len(results),
            "failed_expectations": failed_expectations,
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 1 if failed_expectations else 0


if __name__ == "__main__":
    raise SystemExit(main())
