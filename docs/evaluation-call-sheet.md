# 51-Call Evaluation Worksheet

Run each scenario three times: once in English (`en`), once in Hindi (`hi`), and once in Hinglish
(`hinglish`). This worksheet is a checklist, not evidence by itself. Record one redacted JSON line
per call outside Git, then validate the completed file before rendering the report.

## Procedure

1. Create a fresh Retell browser-call token for each call, or use the connected test number.
2. Use only synthetic demo patients and do not include real patient data.
3. Read the scenario turns naturally. Do not add hints that are not in the scenario.
4. Mark `passed` only when the expected outcome is correct and there is no false confirmation,
   wrong branch, stale slot, incorrect date/time, redundant question, or misleading handoff.
5. Record turns to the definitive outcome, redundant questions, and ASR/LLM/TTS/network timings.
6. Keep raw call IDs, recordings, transcripts, tokens, and phone numbers outside the repository.

## Coverage

| Scenario | English | Hindi | Hinglish |
| --- | --- | --- | --- |
| returning_shared_phone | [ ] | [ ] | [ ] |
| cross_branch_earliest | [ ] | [ ] | [ ] |
| slot_race | [ ] | [ ] | [ ] |
| missed_callback | [ ] | [ ] | [ ] |
| reschedule | [ ] | [ ] | [ ] |
| cancel | [ ] | [ ] | [ ] |
| dropped_call | [ ] | [ ] | [ ] |
| clinical_followup | [ ] | [ ] | [ ] |
| mid_call_code_switch | [ ] | [ ] | [ ] |
| new_patient_hinglish | [ ] | [ ] | [ ] |
| human_request_hinglish | [ ] | [ ] | [ ] |
| interrupted_booking_hinglish | [ ] | [ ] | [ ] |
| natural_time_december_13 | [ ] | [ ] | [ ] |
| recurring_mondays_wednesdays | [ ] | [ ] | [ ] |
| after_work_around_430 | [ ] | [ ] | [ ] |
| thursday_morning | [ ] | [ ] | [ ] |
| branch_specialty_triage | [ ] | [ ] | [ ] |

## Measurement format

Use the exact redacted schema in `evals/measurements.example.jsonl`:

```json
{"scenario_id":"returning_shared_phone","language":"en","passed":true,"turns_to_completion":5,"redundant_questions":0,"latency_ms":{"asr":0,"llm":0,"tts":0,"network":0}}
```

Replace the example values with observed measurements. The validator now requires all 51 unique
scenario/language pairs:

```bash
python scripts/validate_voice_eval.py /secure/path/calls.jsonl
python scripts/render_voice_eval.py /secure/path/calls.jsonl --output /secure/path/voice-eval-report.md
```
