import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_bolna_manifest_is_complete_but_not_falsely_marked_live() -> None:
    manifest = json.loads((ROOT / "integrations/voice/bolna/agent-manifest.json").read_text())

    assert manifest["platform"] == "bolna"
    assert manifest["api"]["create_agent"] == "POST /v2/agent"
    assert manifest["deployment_status"] == "blocked_aws_account_verification_and_telephony"
    assert manifest["languages"] == ["en-IN", "hi-IN", "hinglish"]
    assert all(value == "TBD_AFTER_BAKEOFF" for value in manifest["providers"].values())


def test_voice_prompt_contains_safety_language_and_recovery_gates() -> None:
    prompt = (ROOT / "integrations/voice/bolna/prompt.md").read_text()

    required_rules = [
        "FULL_NAME_GATE",
        "FRESH_AVAILABILITY_GATE",
        "NO_FALSE_CONFIRMATION",
        "LANGUAGE_MIRRORING",
        "NO_CLINICAL_ADVICE",
        "HONEST_HUMAN_FOLLOWUP",
        "DROPPED_CALL_RECOVERY",
    ]
    assert all(rule in prompt for rule in required_rules)


def test_voice_tool_manifest_covers_every_backend_tool() -> None:
    tools = json.loads((ROOT / "integrations/voice/tool-contracts.json").read_text())["tools"]

    assert {tool["name"] for tool in tools} == {
        "clinic_catalog",
        "bootstrap_call",
        "search_availability",
        "book_appointment",
        "list_patient_appointments",
        "reschedule_appointment",
        "cancel_appointment",
        "save_call_checkpoint",
        "log_follow_up",
    }
    assert tools[0]["method"] == "GET"
    assert all(tool["method"] == "POST" for tool in tools[1:])
    assert all(tool["path"].startswith("/v1/tools/") for tool in tools)
