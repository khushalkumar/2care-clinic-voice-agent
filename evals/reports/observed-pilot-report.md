# Observed Voice Pilot Report

This is a redacted report generated from eight completed Retell phone calls made on
2026-07-20. It is an observed pilot sample, not the complete scripted scenario evaluation.
The calls were exploratory and were not executed as a controlled one-call-per-scenario run.

No caller identifiers, call IDs, phone numbers, transcripts, recordings, or access tokens are
included. Retell supplied ASR, LLM, TTS, and end-to-end latency percentiles. A separate network
component was not available in the exported traces, so network latency is reported as unavailable
rather than inferred from backend tool latency.

## Coverage And Outcome

| Observed language bucket | Calls | Successful definitive booking | Observed outcome |
| --- | ---: | ---: | --- |
| English | 6 | 0 | Availability was reached in some calls; booking, identity lookup, or availability failures prevented confirmation. |
| Hindi/Hinglish mixed | 2 | 0 | The agent handled Hindi and mixed Hindi-English turns, but booking confirmation was not reached. |
| Web call with no caller joined | 1 | Not applicable | Excluded from language and latency aggregates. |

## Latency

Values are Retell p50 milliseconds aggregated across the calls in each bucket. These figures are
descriptive only and should not be treated as production SLOs.

| Language bucket | Calls | ASR p50 | LLM p50 | TTS p50 | Network | End-to-end p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| English | 6 | 195 | 1023 | 384 | unavailable | 2265 |
| Hindi/Hinglish mixed | 2 | 218 | 1912 | 483 | unavailable | 3424 |

## Observed Findings

- Live availability lookup succeeded in multiple calls and the agent read back concrete slots.
- The earlier booking failures were real backend failures, including `patient_not_found` and
  `full_name_mismatch`; these were surfaced as follow-up rather than false confirmations.
- Hindi and mixed Hindi-English speech was transcribed and answered in the corresponding language
  style in the observed calls.
- The sample includes no confirmed booking, so booking completion rate is 0/8 in this pilot.
- The sample does not validate rescheduling, cancellation, cross-branch earliest-slot search,
  dropped-call continuation, missed-outbound callback continuation, interruption recovery, or
  every natural-language time scenario.

## Limitations

- The calls were not assigned to the 17 versioned scenario IDs before execution, so they cannot be
  used as complete machine-validated scenario coverage.
- The sample is small and exploratory, with six English calls and two Hindi/Hinglish calls.
- No controlled network timing was exported by Retell.
- Results reflect the staging configuration and the system state at the measurement time.

The complete evaluation remains pending until every versioned scenario is run in its required
language, manually reviewed, measured, and recorded in the redacted JSONL format accepted by the
repository validator.
