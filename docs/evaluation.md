# Voice Evaluation Protocol

## Purpose

The assignment requires evidence from real bilingual voice calls, not an LLM-only prompt
review. The committed scenario corpus supplies repeatable conversation scripts; this protocol
turns redacted Retell call observations into per-language quality and latency reports.

## Before a run

1. Use only the synthetic Cliniko patients and a staging Retell agent.
2. Create one fresh web-call token per run, or use the connected test number once provisioned.
3. Run every scenario in `evals/scenarios/core.json` once in each of English, Hindi, and
   Hinglish. This is 51 calls for the current 17-scenario corpus. Include interruption,
   returning-patient, callback, stale-availability,
   cross-branch earliest, named-branch, dropped-call, booking, reschedule, cancellation, and
   human-follow-up paths.
4. Do not commit recordings, phone numbers, raw transcripts, Retell access tokens, or Cliniko IDs.

## Measurement record

Store one redacted JSON line per completed call outside Git, following
`evals/measurements.example.jsonl`. The required fields are scenario ID, `en`/`hi`/`hinglish`,
pass/fail, turns to a definitive outcome, redundant questions, and component milliseconds for
ASR, LLM, TTS, and network. Capture component timing from Retell call traces and backend logs;
do not substitute backend-tool latency for end-to-end voice latency.

## Report

```bash
python scripts/render_voice_eval.py /secure/path/calls.jsonl \
  --output /secure/path/voice-eval-report.md
```

The generated Markdown reports each language separately. It records scenario pass rate,
mean turns-to-completion, redundant-questions-per-call, and p50 ASR/LLM/TTS/network/end-to-end
latency. The report is intentionally not generated from the committed example input: those values
are illustrative and are not performance claims.

Validate complete coverage and redaction before rendering:

```bash
python scripts/validate_voice_eval.py /secure/path/calls.jsonl
```

The validator rejects call IDs, phone numbers, transcripts, recordings, duplicate scenario/language
rows, and incomplete coverage. A real evaluation report cannot be marked complete until this command
passes.

## Interpretation and limitations

- A scripted scenario can prove that the agent followed the expected tool path; it cannot prove
  robustness to arbitrary phrasing, accents, audio quality, or production traffic.
- Review failed calls manually for language drift, unnatural code-switching, pronunciation, and
  interruption recovery. Count a scenario as failed if the patient receives a false confirmation,
  wrong branch, stale slot, incorrect local date, or an untruthful handoff.
- Re-run the suite after any prompt, voice, model, tool-schema, PMS, or telephony change.
- Do not publish aggregate latency without language sample counts, platform/model versions, and
  the measurement window.
