import json
import subprocess
import sys

from app.evaluation.scenarios import load_scenarios


def _validate(path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_voice_eval.py", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_evaluation_validation_requires_every_scenario_in_each_language(tmp_path) -> None:
    measurements = tmp_path / "measurements.jsonl"
    scenario = load_scenarios()[0]
    measurements.write_text(
        json.dumps(
            {
                "scenario_id": scenario.id,
                "language": scenario.language,
                "passed": True,
                "turns_to_completion": 4,
                "redundant_questions": 0,
                "latency_ms": {"asr": 100, "llm": 200, "tts": 100, "network": 30},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _validate(measurements)

    assert result.returncode != 0
    assert "missing evaluation coverage" in result.stderr


def test_evaluation_validation_rejects_call_identifiers_and_pii(tmp_path) -> None:
    measurements = tmp_path / "measurements.jsonl"
    measurements.write_text(
        json.dumps(
            {
                "scenario_id": "scenario-1",
                "language": "en",
                "passed": True,
                "turns_to_completion": 4,
                "redundant_questions": 0,
                "latency_ms": {"asr": 100, "llm": 200, "tts": 100, "network": 30},
                "retell_call_id": "call-secret",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _validate(measurements)

    assert result.returncode != 0
    assert "redacted" in result.stderr
