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


def test_hosted_voice_demo_uses_retell_web_sdk_without_an_embedded_secret() -> None:
    page = (ROOT / "web-demo/index.html").read_text()

    assert "RetellWebClient" in page
    assert "access_token" in page
    assert "RETELL_API_KEY" not in page


def test_retell_tools_bind_availability_to_bootstrapped_session() -> None:
    provisioner = (ROOT / "scripts/provision_retell_agent.mjs").read_text()
    prompt = (ROOT / "integrations/voice/retell/prompt.md").read_text()

    assert (
        provisioner.count('description: "Use the session_id returned by bootstrap_call exactly."')
        >= 5
    )
    assert (
        'session_id: { ...string, description: "Use the session_id returned by '
        'bootstrap_call exactly." }' in provisioner
    )
    assert 'description: "Use {{direction}} exactly."' in provisioner
    assert 'description: "Use {{agent_number}} exactly."' in provisioner
    assert 'description: "Use {{call_id}} exactly."' in provisioner
    assert '"platform_call_id": "retell-staging-web-demo"' not in provisioner
    assert "Use the `session_id` returned by `bootstrap_call`" in prompt
    assert "for both `search_availability` and `book_appointment`" in prompt


def test_retell_web_fallbacks_use_valid_inbound_call_values() -> None:
    provisioner = (ROOT / "scripts/provision_retell_agent.mjs").read_text()

    assert 'direction: "inbound"' in provisioner
    assert 'agent_number: "+14177428846"' in provisioner


def test_retell_prompt_requires_spoken_slot_labels_and_clear_choices() -> None:
    prompt = (ROOT / "integrations/voice/retell/prompt.md").read_text()

    assert "spoken_label" in prompt
    assert "one slot at a time" in prompt
    assert "Slot one" in prompt
