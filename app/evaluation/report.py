import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True, slots=True)
class CallMeasurement:
    scenario_id: str
    language: str
    passed: bool
    turns_to_completion: int
    redundant_questions: int
    latency_ms: dict[str, float]


def load_measurements(path: Path) -> list[CallMeasurement]:
    measurements: list[CallMeasurement] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            latency = raw["latency_ms"]
            measurement = CallMeasurement(
                scenario_id=str(raw["scenario_id"]),
                language=str(raw["language"]),
                passed=bool(raw["passed"]),
                turns_to_completion=int(raw["turns_to_completion"]),
                redundant_questions=int(raw["redundant_questions"]),
                latency_ms={
                    name: float(latency[name]) for name in ("asr", "llm", "tts", "network")
                },
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid measurement at line {line_number}") from error
        if measurement.language not in {"en", "hi", "hinglish"}:
            raise ValueError(f"invalid language at line {line_number}")
        if measurement.turns_to_completion < 1 or measurement.redundant_questions < 0:
            raise ValueError(f"invalid turn counts at line {line_number}")
        if any(value < 0 for value in measurement.latency_ms.values()):
            raise ValueError(f"invalid latency at line {line_number}")
        measurements.append(measurement)
    if not measurements:
        raise ValueError("at least one measurement is required")
    return measurements


def _p50(values: list[float]) -> int:
    return round(median(values))


def render_markdown_report(measurements: list[CallMeasurement]) -> str:
    grouped: dict[str, list[CallMeasurement]] = defaultdict(list)
    for measurement in measurements:
        grouped[measurement.language].append(measurement)
    quality_header = (
        "| "
        + " | ".join(
            [
                "Language",
                "Calls",
                "Scenario pass rate",
                "Mean turns to completion",
                "Redundant questions/call",
            ]
        )
        + " |"
    )

    lines = [
        "# Voice Evaluation Report",
        "",
        "This report is generated from redacted, manually reviewed Retell call measurements.",
        "Latency is milliseconds at p50; sample counts are reported per language and results are",
        "not blended.",
        "",
        "## Quality",
        "",
        quality_header,
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for language in sorted(grouped):
        items = grouped[language]
        pass_rate = sum(item.passed for item in items) / len(items)
        mean_turns = sum(item.turns_to_completion for item in items) / len(items)
        redundant_questions = sum(item.redundant_questions for item in items) / len(items)
        lines.append(
            f"| {language} | {len(items)} | {pass_rate:.1%} | {mean_turns:.2f} | "
            f"{redundant_questions:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Latency",
            "",
            "| Language | ASR p50 | LLM p50 | TTS p50 | Network p50 | End-to-end p50 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for language in sorted(grouped):
        items = grouped[language]
        component = {
            name: _p50([item.latency_ms[name] for item in items])
            for name in ("asr", "llm", "tts", "network")
        }
        total = sum(component.values())
        lines.append(
            "| {language} | {asr} | {llm} | {tts} | {network} | {total} |".format(
                language=language,
                total=total,
                **component,
            )
        )
    return "\n".join(lines) + "\n"
