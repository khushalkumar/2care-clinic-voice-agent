import json

from app.evaluation.metrics import ScenarioResult, summarize
from app.evaluation.report import load_measurements, render_markdown_report
from app.evaluation.scenarios import load_scenarios


def test_scenario_corpus_covers_required_multiturn_language_cases() -> None:
    scenarios = load_scenarios()
    ids = {scenario.id for scenario in scenarios}

    assert {
        "returning_shared_phone",
        "cross_branch_earliest",
        "slot_race",
        "reschedule",
        "cancel",
        "missed_callback",
        "dropped_call",
        "clinical_followup",
        "mid_call_code_switch",
        "natural_time_december_13",
        "recurring_mondays_wednesdays",
        "after_work_around_430",
        "thursday_morning",
        "branch_specialty_triage",
    } <= ids
    assert {scenario.language for scenario in scenarios} == {"en", "hi", "hinglish"}
    assert len(scenarios) == 17
    assert all(len(scenario.turns) >= 2 for scenario in scenarios)
    assert all(scenario.expected_tools for scenario in scenarios)


def test_metrics_are_reported_per_language_with_turn_efficiency() -> None:
    report = summarize(
        [
            ScenarioResult("en-1", "en", True, 4, 0),
            ScenarioResult("en-2", "en", False, 6, 2),
            ScenarioResult("hi-1", "hi", True, 5, 1),
            ScenarioResult("mix-1", "hinglish", True, 3, 0),
        ]
    )

    assert set(report) == {"en", "hi", "hinglish"}
    assert report["en"].pass_rate == 0.5
    assert report["en"].turns_to_completion_mean == 5
    assert report["en"].redundant_questions_per_call == 1
    assert report["hi"].pass_rate == 1


def test_measurement_report_separates_language_and_component_latency(tmp_path) -> None:
    measurements = tmp_path / "calls.jsonl"
    measurements.write_text(
        "\n".join(
            json.dumps(item)
            for item in [
                {
                    "scenario_id": "english-booking",
                    "language": "en",
                    "passed": True,
                    "turns_to_completion": 4,
                    "redundant_questions": 0,
                    "latency_ms": {"asr": 120, "llm": 280, "tts": 90, "network": 30},
                },
                {
                    "scenario_id": "hindi-booking",
                    "language": "hi",
                    "passed": False,
                    "turns_to_completion": 6,
                    "redundant_questions": 1,
                    "latency_ms": {"asr": 180, "llm": 320, "tts": 140, "network": 50},
                },
            ]
        )
        + "\n"
    )

    report = render_markdown_report(load_measurements(measurements))

    assert "| en | 1 | 100.0% | 4.00 | 0.00 |" in report
    assert "| hi | 1 | 0.0% | 6.00 | 1.00 |" in report
    assert "| en | 120 | 280 | 90 | 30 | 520 |" in report
    assert "| Language | Calls | Scenario pass rate | Mean turns to completion |" in report
    assert "p50; sample counts are reported per language" in report
