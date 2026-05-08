#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

OVERALL_MINIMUM = 80.0


def main() -> int:
    coverage_json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".coverage.json")
    if not coverage_json_path.is_file():
        print(f"Coverage report not found: {coverage_json_path}", file=sys.stderr)
        return 1

    report = json.loads(coverage_json_path.read_text())
    totals = report.get("totals")
    if not isinstance(totals, dict):
        print(f"Unexpected coverage report shape in {coverage_json_path}", file=sys.stderr)
        return 1
    value = totals.get("percent_covered")
    if not isinstance(value, int | float):
        print(f"Unexpected coverage total in {coverage_json_path}", file=sys.stderr)
        return 1

    coverage = float(value)
    if coverage < OVERALL_MINIMUM:
        print(
            f"Coverage policy failed: total {coverage:.2f}% is below {OVERALL_MINIMUM:.2f}%",
            file=sys.stderr,
        )
        return 1

    print(f"Coverage policy satisfied: total {coverage:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
