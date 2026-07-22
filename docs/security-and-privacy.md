# Security and privacy

## Trust boundaries

- Voice tools require HMAC-SHA256 over timestamp, event ID, method, path, and exact body hash.
- Event IDs are claimed atomically in PostgreSQL for replay defense across tasks and restarts.
- Pydantic rejects unknown fields; SQLAlchemy binds values; provider hosts are configured, not caller supplied.
- Availability tokens are signed, short lived, call bound, and rechecked against the PMS.
- Patient list/reschedule/cancel mutations require an active call session, an exact normalized
  caller-ID match, and a durable server-side phone-to-patient binding. Multiple Cliniko records
  for one phone are treated as aliases; the backend verifies that the selected appointment belongs
  to that phone group. Every mutation requires explicit confirmation of the selected appointment;
  rescheduling also requires a fresh signed availability token and local exclusion-constraint
  reservation.
- Browser CORS is disabled by default because Retell calls the API server-to-server. If a browser
  origin is ever needed, `CORS_ALLOWED_ORIGINS` accepts only explicit HTTP(S) origins and never `*`.
- Responses include baseline browser hardening headers. AWS WAF is an explicit production edge
  control with a per-IP rate limit before the ALB; production Terraform refuses to proceed until
  it is enabled and the deployer has WAF permissions. Staging keeps the API-level request size,
  content type, HMAC replay, and platform-token gates active without requiring that IAM grant.
- PostgreSQL exclusion constraints and idempotency keys remain authoritative if prompts fail.
- The backend applies a configurable 60-minute same-day booking buffer by default; operators can
  change it with `SAME_DAY_BOOKING_BUFFER_MINUTES` without changing the voice prompt.

## Data policy

- Clinic addresses and practitioner names are public facts with source-manifest provenance.
- Patients, phone numbers, availability, and appointments are synthetic.
- HTTP logs contain request ID, method, path, status, and duration only. Bodies and auth headers are excluded.
- Do not persist model chain-of-thought, full transcripts, or recordings by default.
- Private evaluation artifacts belong in `evals/reports/private/`, which Git ignores.

## Secrets

CI runs history-aware Gitleaks and Trivy image scans. AWS secret resources contain metadata only;
operators populate values out of band. Rotate tool HMAC secrets with an overlap window: deploy
dual verification, update Bolna, verify traffic, then remove the old key. Rotate Cliniko and
database credentials independently. Never put secret values in Terraform variables or state.

## Known gate

Bolna webhook/header capabilities and the live Cliniko field contract must be verified in the
trial accounts before production. Until then, production startup intentionally refuses the
unvalidated Cliniko runtime adapter.
