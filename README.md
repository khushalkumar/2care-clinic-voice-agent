# 2care Clinic Voice Agent

Production-oriented English, Hindi, and Hinglish voice receptionist for a sourced,
two-branch Physiotattva clinic demonstration. It supports booking, rescheduling,
cancellation, shared-phone identity, missed callbacks, dropped-call recovery, and honest
PMS failure handling.

## Current status

The backend is live in AWS staging behind an ALB, backed by RDS PostgreSQL and Cliniko.
The deployment has passed `/live` and dependency-aware `/ready` checks. Retell agent provisioning
is versioned in this repository and runs after each staging deployment. A web-call test is the
current live voice entry point; an independently callable PSTN number remains pending purchase.

- 76 automated tests pass locally before the Retell adapter changes.
- Booking races are enforced by PostgreSQL exclusion constraints.
- The Cliniko adapter chunks live availability requests into its verified seven-calendar-day limit.
- Live Cliniko availability and one synthetic patient/appointment write have been contract-verified.
- HMAC authentication, replay prevention, request limits, and opaque slot tokens are tested.
- Timeout-after-write reconciliation produces one appointment and never false confirmation.
- OpenTofu validates the staging/production AWS configuration.
- Twelve multi-turn EN/HI/Hinglish scenarios are versioned under `evals/scenarios/`.

## Voice platform decision

**Retell is the implementation platform.** It provides a managed real-time voice stack with
strict custom-function schemas, explicit tool timeouts, interruption controls, multilingual
agent locales (`en-IN`, `hi-IN`), an Indian English voice using ElevenLabs Multilingual v2, and
web-call testing before telephony purchase. The agent uses deterministic `gpt-5.1` tool calling,
0 temperature, strict mode, 12-second tool deadlines, and high interruption sensitivity.

Bolna remains documented as the comparison baseline, not a second live implementation. Retell
was chosen here because its API lets the project version and reconcile agent, prompt, voice,
tool schemas, and platform settings after each deployment. The remaining evidence task is a
30-call English/Hindi/Hinglish bake-off with reported tool accuracy, language drift, interruption
recovery, component latency, and cost per completed conversation.

## Architecture

```mermaid
flowchart LR
    Caller["Patient"] --> Tel["Retell web call / inbound telephony"]
    Tel --> Voice["Retell voice agent"]
    Voice -->|"Platform token (staging ALB transport)"| ALB["AWS ALB"]
    ALB --> API["FastAPI on ECS Fargate"]
    API --> DB[("RDS PostgreSQL")]
    API --> PMS["Cliniko / durable mock"]
    API --> Queue["SQS + DLQ"]
    Queue --> Worker["Reconciliation worker"]
    Worker --> PMS
    API --> CW["CloudWatch logs and alarms"]
```

Cliniko owns live clinic records. PostgreSQL owns call state, local reservations,
idempotency, replay defense, follow-ups, and recovery. A booking is spoken as confirmed only
after both the local reservation and PMS write are definitive.

## Local development

Prerequisites: Python 3.11 and PostgreSQL 16 test binaries.

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
pytest
ruff check app tests migrations
ruff format --check app tests migrations
mypy app
```

The integration suite starts an isolated PostgreSQL cluster and creates a fresh database per
test. It never reads a real `.env` file. Use `.env.example` only as a variable inventory.

To run the API in mock mode after starting PostgreSQL and applying migrations:

```bash
alembic upgrade head
APP_ENV=local PMS_PROVIDER=mock \
DATABASE_URL=postgresql+asyncpg://voice_agent:voice_agent@localhost:5432/voice_agent \
REQUEST_HMAC_SECRET='replace-with-32-random-characters-minimum' \
AVAILABILITY_TOKEN_SECRET='use-a-different-32-character-secret' \
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

## Deployment

Terraform-compatible infrastructure is in `infra/terraform`. It defines private Fargate tasks,
private RDS, an ALB, KMS, secret containers, SQS/DLQ, ECR, autoscaling, logs,
and alarms. No secret
value is stored in Terraform. Production enables two tasks, Multi-AZ RDS, longer backups, and
deletion protection. Staging uses one task, private single-AZ RDS, and a public-IP task reachable
only through the ALB security group to avoid NAT Gateway cost. Production keeps private tasks and
per-AZ NAT gateways.

Do not run `apply` until the image exists, secret JSON is populated, the plan is reviewed, and
the user explicitly approves billable resources. See [deployment runbook](docs/runbooks/deployment.md).

## Evidence and decisions

- [Original assignment](docs/assignment/original-assignment.docx)
- [Research and decision register](docs/research-and-decision-register.md)
- [Implementation specification](docs/implementation-spec.md)
- [Production implementation plan](docs/implementation-plan.md)
- [Architecture](docs/architecture.md)
- [Clinic/PMS decision](docs/decisions/0001-clinic-and-pms.md)
- [AWS decision](docs/decisions/0002-production-aws.md)
- [Booking persistence decision](docs/decisions/0004-booking-persistence.md)
- [Security and privacy](docs/security-and-privacy.md)
- [Operations runbooks](docs/runbooks/README.md)

Only public clinic facts with recorded provenance and synthetic patient/appointment data belong
in this repository. Never commit credentials, generated Cliniko IDs, Terraform state, real call
recordings, or unredacted transcripts.
