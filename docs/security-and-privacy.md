# Security and privacy

## Trust boundaries

- Voice tools require HMAC-SHA256 over timestamp, event ID, method, path, and exact body hash.
- Event IDs are claimed atomically in PostgreSQL for replay defense across tasks and restarts.
- Pydantic rejects unknown fields; SQLAlchemy binds values; provider hosts are configured, not caller supplied.
- Availability tokens are signed, short lived, call bound, and rechecked against the PMS.
- PostgreSQL exclusion constraints and idempotency keys remain authoritative if prompts fail.

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
