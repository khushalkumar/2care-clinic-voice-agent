# Submission Checklist

## Complete in repository

- [x] Retell agent configuration, prompt, real-time voice selection, and tool contracts are versioned.
- [x] AWS staging uses ECS Fargate, RDS PostgreSQL, ALB, ECR, Secrets Manager, KMS, SQS/DLQ, CloudWatch, and CloudTrail resources.
- [x] Cliniko-backed booking, rescheduling, cancellation, idempotency, shared-phone identity, callback context, and dropped-call recovery are implemented.
- [x] HTTPS browser voice test is published through GitHub Pages.
- [x] CI verifies 82 tests, lint, type checks, infrastructure validation, Gitleaks, and Trivy.
- [x] The assignment scenario corpus and redacted per-language reporting tool are committed.

## Required before claiming a production-ready, call-in submission

- [x] Purchase a test-capable Twilio number and connect it to the Retell inbound agent via Elastic
  SIP Trunking.
- [ ] Place English, Hindi, and Hinglish calls against the number. Run every scenario in
  `evals/scenarios/core.json`, including interruption and callback recovery.
- [ ] Record only redacted measurements, render the report with `scripts/render_voice_eval.py`, and
  link the resulting report from the README or submission write-up.
- [ ] Obtain an ACM certificate for a domain controlled by the project, pass it as
  `certificate_arn`, and verify Retell tools use the resulting HTTPS endpoint.
- [ ] Run a final synthetic booking, reschedule, cancellation, conflict, and human-follow-up canary
  after the number and certificate changes.

## Email deliverables

Send the repository link, write-up/README link, prompt location
(`integrations/voice/retell/prompt.md`), live test number `+1 417 742 8846`, and live test
instructions to
`tech@2care.ai`, `p@2care.ai`, and `s@2care.ai`. Do not include API keys, web-call URLs, patient
details, or recordings in the email.
