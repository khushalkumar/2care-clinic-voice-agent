import argparse
import json
import sys
from pathlib import Path

from app.evaluation.report import CallMeasurement, load_measurements
from app.evaluation.scenarios import load_scenarios

_ALLOWED_KEYS = {
    "scenario_id",
    "language",
    "passed",
    "turns_to_completion",
    "redundant_questions",
    "latency_ms",
}


def validate_measurement_coverage(path: Path) -> list[CallMeasurement]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid redacted measurement at line {line_number}") from error
        unexpected = set(raw) - _ALLOWED_KEYS
        if unexpected:
            raise ValueError(
                f"measurement at line {line_number} is not redacted; remove {sorted(unexpected)}"
            )

    measurements = load_measurements(path)
    expected = {(scenario.id, scenario.language) for scenario in load_scenarios()}
    observed = {(item.scenario_id, item.language) for item in measurements}
    duplicates = len(measurements) != len(observed)
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if duplicates:
        raise ValueError("duplicate scenario/language measurement")
    if missing:
        raise ValueError(
            f"missing evaluation coverage: {', '.join(f'{sid}/{lang}' for sid, lang in missing)}"
        )
    if unexpected:
        raise ValueError(f"measurement references unknown scenario: {unexpected}")
    return measurements


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate complete redacted voice evaluation coverage."
    )
    parser.add_argument("input", type=Path, help="Redacted JSONL measurement file")
    args = parser.parse_args()
    try:
        measurements = validate_measurement_coverage(args.input)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"validated {len(measurements)} redacted scenario measurements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
