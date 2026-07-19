from collections import defaultdict
from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    language: str
    passed: bool
    turns_to_completion: int
    redundant_questions: int


@dataclass(frozen=True, slots=True)
class LanguageMetrics:
    sample_count: int
    pass_rate: float
    turns_to_completion_mean: float
    redundant_questions_per_call: float


def summarize(results: list[ScenarioResult]) -> dict[str, LanguageMetrics]:
    grouped: dict[str, list[ScenarioResult]] = defaultdict(list)
    for result in results:
        grouped[result.language].append(result)
    return {
        language: LanguageMetrics(
            sample_count=len(items),
            pass_rate=sum(item.passed for item in items) / len(items),
            turns_to_completion_mean=mean(item.turns_to_completion for item in items),
            redundant_questions_per_call=mean(item.redundant_questions for item in items),
        )
        for language, items in sorted(grouped.items())
    }
