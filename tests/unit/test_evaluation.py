from app.evaluation.metrics import ScenarioResult, summarize
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
    } <= ids
    assert {scenario.language for scenario in scenarios} == {"en", "hi", "hinglish"}
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
