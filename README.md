# 2care Clinic Voice Agent

Production-oriented English, Hindi, and Hinglish voice receptionist for a sourced,
two-branch Physiotattva clinic demonstration. It supports booking, rescheduling,
cancellation, shared-phone identity, missed callbacks, dropped-call recovery, and honest
PMS failure handling.

## Current status

The backend is live in AWS staging behind an ALB, backed by RDS PostgreSQL and Cliniko.
The deployment has passed `/live` and dependency-aware `/ready` checks. Retell agent provisioning
is versioned in this repository and runs after each staging deployment. The HTTPS web-call test is
published through GitHub Pages, and the Twilio number `+1 417 742 8846` is connected to Retell
through a Twilio Elastic SIP Trunk for inbound PSTN testing.

- The test suite covers the API, booking state, calls, recovery, and voice assets.
- Booking races are enforced by PostgreSQL exclusion constraints.
- The Cliniko adapter chunks live availability requests into its verified seven-calendar-day limit.
- Live Cliniko availability and one synthetic patient/appointment write have been contract-verified.
- HMAC authentication, replay prevention, request limits, opaque slot tokens, session-bound
  patient authorization, strict security headers, and default-deny CORS are implemented and
  tested. WAF rate limiting is provisioned by the production Terraform profile.
- Timeout-after-write reconciliation produces one appointment and never false confirmation.
- OpenTofu validates the staging/production AWS configuration.
- Seventeen multi-turn EN/HI/Hinglish scenarios are versioned under `evals/scenarios/`. The live
  evidence gate requires every scenario in all three language modes; no results are claimed until
  those calls are completed and redacted.
- An [observed pilot report](evals/reports/observed-pilot-report.md) summarizes eight completed
  exploratory phone calls. It is explicitly not the complete scripted scenario evaluation and
  reports booking completion as 0/8 for that sample.

## Voice platform decision

**Retell is the implementation platform.** It provides a managed real-time voice stack with
strict custom-function schemas, explicit tool timeouts, interruption controls, multilingual
agent locales (`en-IN`, `hi-IN`), an Indian English voice using ElevenLabs Multilingual v2, and
web-call testing before telephony purchase. The agent uses deterministic `gpt-5.1` tool calling,
0 temperature, strict mode, 12-second tool deadlines, and high interruption sensitivity.

Bolna remains documented as the comparison baseline, not a second live implementation. Retell
was chosen here because its API lets the project version and reconcile agent, prompt, voice,
tool schemas, and platform settings after each deployment. Real-call results are intentionally
not claimed until the 51-call English/Hindi/Hinglish bake-off has been run using the
[evaluation protocol](docs/evaluation.md). It reports tool accuracy, language drift, interruption
recovery, component latency, and cost per completed conversation.

## Live voice test

Call the live test number:

```text
+1 417 742 8846
```

The number is a Twilio US number attached to the `2care-retell-staging` Elastic SIP Trunk. Twilio
termination is authenticated with the Retell SBC IP ACL documented by Retell, origination routes to
`sip:sip.retellai.com`, and Retell imports the number as `2care Twilio staging` with inbound calls
assigned to `2care Physiotattva Bilingual Receptionist (Staging) / V0 - staging (Draft)`.

The browser client is hosted at
[`https://khushalkumar.github.io/2care-clinic-voice-agent/`](https://khushalkumar.github.io/2care-clinic-voice-agent/).
It contains no secret and accepts a short-lived Retell access token only in the URL fragment, which
the browser does not send to GitHub Pages. Generate a one-use call URL locally with a Retell API key
and the staging agent ID from the Retell dashboard:

```bash
export RETELL_API_KEY='...'
export RETELL_AGENT_ID='agent_...'
export DEMO_URL='https://khushalkumar.github.io/2care-clinic-voice-agent/'
node scripts/create_retell_web_call.mjs
```

Open the emitted `demo_url` directly, permit microphone access, and test a booking conversation in
English, Hindi, and Hinglish. Do not store or share the generated URL: it includes a short-lived
web-call access token.

## Architecture

```mermaid
flowchart LR
    Caller["Patient"] --> Tel["Retell web call / inbound telephony"]
    Tel --> Voice["Retell voice agent"]
    Voice -->|"Platform token (staging ALB transport)"| ALB["AWS ALB"]
    ALB --> WAF["AWS WAF rate limit"]
    WAF --> API["FastAPI on ECS Fargate"]
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

The live assignment environment is staging and intentionally uses the AWS ALB HTTP endpoint;
it does not require a purchased domain. Retell staging tools are provisioned against the ALB URL
and the current call path is operational. HTTPS via ACM remains an optional production upgrade:
when a certificate is supplied, HTTP redirects to HTTPS and HSTS is enabled. The production
Terraform profile still refuses to provision voice traffic without that certificate. See the
[deployment runbook](docs/runbooks/deployment.md).

## Evidence and decisions

- [Original assignment](docs/assignment/original-assignment.docx)
- [Research and decision register](docs/research-and-decision-register.md)
- [Implementation specification](docs/implementation-spec.md)
- [Production implementation plan](docs/implementation-plan.md)
- [Architecture](docs/architecture.md)
- [Voice evaluation protocol](docs/evaluation.md)
- [51-call evaluation worksheet](docs/evaluation-call-sheet.md)
- [Submission checklist](docs/submission-checklist.md)
- [Clinic/PMS decision](docs/decisions/0001-clinic-and-pms.md)
- [AWS decision](docs/decisions/0002-production-aws.md)
- [Booking persistence decision](docs/decisions/0004-booking-persistence.md)
- [Security and privacy](docs/security-and-privacy.md)
- [Operations runbooks](docs/runbooks/README.md)

Only public clinic facts with recorded provenance and synthetic patient/appointment data belong
in this repository. Never commit credentials, generated Cliniko IDs, Terraform state, real call
recordings, or unredacted transcripts.
