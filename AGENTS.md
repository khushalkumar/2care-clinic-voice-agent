# Repository Instructions

- Never create, read, or modify a real `.env` file. Maintain `.env.example` only.
- Use `venv`, never `.venv`.
- Follow test-driven development: add a failing test, verify the failure, then implement the smallest passing change.
- Use public clinic data only where the source manifest records provenance.
- Use synthetic patient, availability, and appointment data only.
- Never commit credentials, generated Cliniko IDs, Terraform state, call recordings containing PII, or unredacted transcripts.
- Keep voice-platform-specific code behind integration boundaries until the measured platform decision is recorded.
- Ask for confirmation before staging, committing, pushing, creating a pull request, or deploying billable infrastructure.
