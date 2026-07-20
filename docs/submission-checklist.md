# Submission Checklist

## Complete in repository

- [x] Retell agent configuration, prompt, real-time voice selection, and tool contracts are versioned.
- [x] AWS staging uses ECS Fargate, RDS PostgreSQL, ALB, ECR, Secrets Manager, KMS, SQS/DLQ, CloudWatch, and CloudTrail resources.
- [x] Cliniko-backed booking, rescheduling, cancellation, idempotency, shared-phone identity, callback context, and dropped-call recovery are implemented.
- [x] HTTPS browser voice test is published through GitHub Pages.
- [x] CI verifies the full pytest suite, lint, type checks, infrastructure validation, Gitleaks, and Trivy.
- [x] The assignment scenario corpus, redaction validator, and per-language reporting tool are committed.
- [x] All patient mutations use an active call session, caller-phone/name authorization, idempotency,
  fresh reschedule availability tokens, and local conflict protection.
- [x] API hardening includes request size/content-type enforcement, replay-safe HMAC, security headers,
  default-deny CORS, and AWS WAF IP rate limiting.

## Required before claiming a complete live-demo submission

- [x] Purchase a test-capable Twilio number and connect it to the Retell inbound agent via Elastic
  SIP Trunking.
- [ ] Place English, Hindi, and Hinglish calls against the number. Run every scenario in
  `evals/scenarios/core.json` in all three language modes, including interruption and callback recovery.
- [ ] Record only redacted measurements, render the report with `scripts/render_voice_eval.py`, and
  run `scripts/validate_voice_eval.py` before linking the resulting report from the README or
  submission write-up.
- [x] Deploy the hosted staging backend and configure Retell tools against its AWS ALB endpoint.
- [ ] Run a final synthetic booking, reschedule, cancellation, conflict, and human-follow-up canary
  against the live staging endpoint.

HTTPS/ACM is intentionally not a submission blocker for this assignment environment because the
project does not currently control a domain. It remains a required production hardening step in
the production Terraform profile, but buying a domain is not necessary to demonstrate the live
staging voice workflow.

## Email deliverables

Send the repository link, write-up/README link, prompt location
(`integrations/voice/retell/prompt.md`), live test number `+1 417 742 8846`, and live test
instructions to
`tech@2care.ai`, `p@2care.ai`, and `s@2care.ai`. Do not include API keys, web-call URLs, patient
details, or recordings in the email.
