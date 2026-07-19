import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Turn:
    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    language: str
    turns: tuple[Turn, ...]
    expected_tools: tuple[str, ...]


def load_scenarios(path: Path | None = None) -> list[Scenario]:
    source = path or Path(__file__).parents[2] / "evals" / "scenarios" / "core.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    scenarios = []
    for item in payload["scenarios"]:
        scenarios.append(
            Scenario(
                id=item["id"],
                language=item["language"],
                turns=tuple(Turn(**turn) for turn in item["turns"]),
                expected_tools=tuple(item["expected_tools"]),
            )
        )
    return scenarios
