# 2care.ai Voice Receptionist: Implementation Specification

Status: proposed for approval before repository creation.

Clinic decision: approved 2026-07-18.

Production AWS direction: approved 2026-07-18.

Voice platform and provider versions: pending measured bake-off and credentials.

## 1. Product boundary

Build a production-oriented bilingual voice receptionist for a limited demo representation of Physiotattva's Jayanagar and Indiranagar branches.

The system will:

- answer one independently callable phone number;
- support English, Hindi, and natural Hinglish;
- identify new and returning synthetic patients;
- search fresh Cliniko availability across both branches and all eligible practitioners;
- book, reschedule, and cancel appointments;
- survive slot races, dropped calls, callbacks, duplicated requests, and PMS failures;
- disclose that it is an AI and create honest human follow-up requests;
- produce reproducible per-language evaluation evidence.

It will not provide clinical advice, use real patient information, imply affiliation with Physiotattva, or claim that synthetic schedules represent the clinic's current availability.

## 2. Data provenance contract

Every clinic seed field must have one of these labels:

| Label | Meaning | Example |
|---|---|---|
| `sourced` | Verbatim or normalized public fact from an official clinic page | Branch address, practitioner name |
| `derived` | Mechanical interpretation of a sourced fact | `Asia/Kolkata` from Bengaluru location |
| `synthetic` | Created solely for this demonstration | Weekly rota, patient phone, existing appointment |

The repository will include `data/clinic_source_manifest.yaml` with source URL, retrieval date, field paths, and label. CI will reject clinic records without provenance.

Required disclaimer:

> This project is an independent technical demonstration. Public clinic names, locations, practitioners, and services are used only to satisfy the sourced-clinic assignment requirement. Availability schedules, patients, phone numbers, appointments, and operational mappings are synthetic. This project is not affiliated with or endorsed by Physiotattva.

## 3. Approved Cliniko dataset

### Cliniko business and branch mapping

The trial uses one Cliniko business, `Physiotattva Demo Clinic`, as the practice container.
Jayanagar and Indiranagar are physical branch records in this application, not duplicate Cliniko
businesses. Their scheduling boundary is the existing branch-prefixed appointment type plus the
mapped practitioner.

| Internal branch key | Cliniko mapping | Address | Provenance |
|---|---|---|---|
| `jayanagar` | `Jayanagar — Initial consultation`; `Jayanagar — Follow-up` | 75, 8th Main Road, Jaya Nagar 1st Block, Bengaluru, Karnataka 560011 | Address sourced; appointment types synthetic |
| `indiranagar` | `Indiranagar — Initial consultation`; `Indiranagar — Follow-up` | 1st Floor, 3478/A, 14th Main Road, HAL 2nd Stage, Bengaluru, Karnataka 560038 | Address sourced; appointment types synthetic |

The Cliniko business uses timezone `Asia/Kolkata`, currency `INR`, and locale `en-IN`. Timezone
and currency are derived from location.

### Practitioners

Use one existing practitioner per branch. The assignment requires two locations, not four
practitioners, and the pair proves cross-branch availability without unnecessary trial setup.

| Internal key | Practitioner | Business | Provenance |
|---|---|---|---|
| `nadia_zainab` | Dr Nadia Zainab (PT) | Jayanagar | Sourced |
| `silki_gupta` | Dr Silki Gupta (PT) | Indiranagar | Sourced |

Normalize all-caps public names for natural TTS while preserving the source spelling in the manifest.

### Services and appointment types

Publicly sourced clinic services include musculoskeletal, neurological, sports injury, geriatric, pediatric, vestibular, post-surgical, and women's health physiotherapy. Exact bookable product definitions are not public, so Cliniko appointment types are synthetic operational representations.

| Appointment type | Duration | Capacity buffer | Fee | Provenance |
|---|---:|---:|---:|---|
| Initial Physiotherapy Assessment | 60 minutes | 10 minutes after | INR 650 | Duration bounded by sourced 30-60 minute statement; exact type/buffer/fee are synthetic unless fee source is reconfirmed |
| Follow-up Physiotherapy Session | 30 minutes | 10 minutes after | INR 650 | Duration bounded by source; exact type/buffer/fee are synthetic unless reconfirmed |

Do not publish the fee as a real Physiotattva price until its current official source is reverified. If not verified, label it “demo fee” in every prompt and README reference.

### Synthetic weekly availability

These schedules are intentionally different so “earliest across branches and practitioners” cannot be faked by querying one calendar.

| Practitioner | Days | Working windows |
|---|---|---|
| Dr Nadia Zainab | Monday to Friday | 09:00-14:00 |
| Dr Silki Gupta | Monday to Friday | 15:00-17:00 |

No Sunday availability. Seed selected unavailable blocks, existing appointments, and same-day buffers to create deterministic conflict scenarios.

### Synthetic patients

Use reserved example-domain emails and non-routable/test-controlled phone numbers supplied at deployment time. Never seed a random real Indian number.

| Patient key | Purpose |
|---|---|
| `returning_single` | One patient on a phone number with appointment history |
| `family_adult_1` | First patient sharing a family phone |
| `family_adult_2` | Second patient sharing the same family phone |
| `missed_callback` | Patient with an unanswered outbound campaign context |
| `dropped_booking` | Patient with an incomplete call checkpoint |
| `new_patient` | No prior patient match |

Actual test numbers are injected through deployment secrets/configuration, not committed. Synthetic names and dates of birth may be committed if unmistakably fictitious.

### Cliniko bootstrap

The repository will provide an idempotent `scripts/bootstrap_cliniko.py` that:

1. validates it is pointed at the designated trial account;
2. verifies the one designated Cliniko business and reconciles application branch metadata;
3. maps the two existing practitioners and their branch ownership;
4. maps the four branch-prefixed appointment types and practitioner associations;
5. verifies that the business, practitioners, and appointment types are enabled for Cliniko Online Bookings before attempting an availability lookup;
6. creates synthetic patients and appointment history;
7. writes only Cliniko IDs to a generated local mapping file excluded from Git;
8. prints a redacted verification report.

The script must support `--dry-run`, require an explicit `--apply`, and never delete unknown Cliniko records. A separate cleanup command may archive only records carrying our deterministic demo marker.

Cliniko's documented patient filters do not support phone numbers. Production caller lookup must
therefore use a narrowly scoped, encrypted phone-to-Cliniko-ID mapping supplied by the deployment,
not a bulk read of patient records. The synthetic demo patient is identified by its project marker
and reserved `example.com` email; its remote ID is kept outside Git.

## 4. Source-of-truth boundaries

### Cliniko owns in the live environment

- businesses and branch metadata;
- practitioners and appointment types;
- synthetic patients and their appointment history;
- configured available times;
- final appointment records and cancellation state.

### PostgreSQL owns

- call sessions and recovery checkpoints;
- missed outbound call context;
- normalized caller constraints and their turn provenance;
- tool requests/results and latency;
- idempotency keys and operation state;
- short-lived local slot reservations;
- database-enforced overlap protection;
- Cliniko ID mappings and reconciliation state;
- outbox events, retries, dead letters, and follow-up requests;
- evaluation runs and scenario outcomes.

### Mock PMS owns in tests

The mock implements the same `PmsGateway` contract as Cliniko, including deterministic availability, patients, appointment lifecycle, idempotency, latency injection, timeouts, transient failures, validation failures, and conflicts.

It is not an in-memory dictionary. It uses the test PostgreSQL instance so process restarts and concurrent tests exercise durable behavior.

## 5. Booking consistency protocol

Availability is not a promise. Every mutation follows this protocol:

1. Fetch current Cliniko available times for all eligible business/practitioner combinations.
   Cliniko permits a maximum of seven calendar dates per `available_times` request, inclusive.
   Longer caller windows are split into seven-date chunks, paginated, merged, and deduplicated.
2. Remove slots covered by unexpired PostgreSQL reservations.
3. Return ranked choices with an opaque `availability_token` containing a query ID, not trusted slot data.
4. On booking, validate caller full name and all required fields.
5. Begin a PostgreSQL transaction and insert a short-lived reservation.
6. Let the GiST exclusion constraint atomically reject overlapping active reservations/appointments.
7. Re-fetch the selected slot from Cliniko.
8. If unavailable, cancel the reservation and return freshly ranked alternatives.
9. Create the Cliniko appointment through the idempotency/reconciliation wrapper.
10. Mark the local operation confirmed only after a definitive Cliniko success.
11. If the remote result is unknown, return `pending_verification`; never tell the caller it is confirmed.

Rescheduling creates the new reservation before cancelling the old appointment. It performs a compensating rollback if the new remote appointment cannot be established. Cancellation is idempotent and records policy disclosure separately from mutation.

## 6. PostgreSQL model

### Core tables

| Table | Purpose |
|---|---|
| `clinic_sources` | Field-level provenance and source retrieval metadata |
| `pms_entities` | Stable internal keys mapped to Cliniko/mock IDs |
| `patients_cache` | Minimal redacted lookup cache; Cliniko remains live authority |
| `call_sessions` | Call identity, language, state, status, disconnect/resume timestamps |
| `call_participants` | All candidate patients for a caller number |
| `call_constraints` | Date/time/branch/practitioner/service constraints with turn source |
| `outbound_contexts` | Missed campaigns and callback intent |
| `booking_operations` | Book/reschedule/cancel state machine and idempotency |
| `slot_reservations` | Time ranges that temporarily or permanently reserve capacity |
| `pms_attempts` | Remote request hash, attempt count, response and reconciliation state |
| `outbox_events` | Transactional events waiting for SQS publication |
| `follow_up_requests` | Honest human callback queue |
| `tool_calls` | Redacted request/result and latency spans |
| `evaluation_runs` | Version, language, scenario, metrics, artifact references |

### Reservation constraint

Conceptual migration:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE slot_reservations
ADD CONSTRAINT no_overlapping_practitioner_reservations
EXCLUDE USING gist (
  practitioner_key WITH =,
  tstzrange(reserved_from, reserved_until, '[)') WITH &&
)
WHERE (status IN ('held', 'pending_remote', 'confirmed'));
```

The stored range includes appointment duration and configured buffer. Expired holds are transitioned before reuse, but correctness must not depend solely on a cleanup job.

### Operation states

`received -> reserved -> remote_in_flight -> confirmed`

Terminal/exception states:

- `local_conflict`
- `remote_conflict`
- `pending_verification`
- `compensating`
- `cancelled`
- `failed_permanent`

State transitions are validated in the service layer and guarded with optimistic version columns so duplicate workers cannot advance an operation twice.

## 7. Backend boundaries

```text
api/
  HTTP authentication, request validation, stable tool envelopes
application/
  call bootstrap, availability, booking, rescheduling, cancellation, follow-up
domain/
  identity rules, scheduling constraints, operation state machines, policies
infrastructure/
  PostgreSQL repositories, Cliniko gateway, mock PMS gateway, SQS, telemetry
```

FastAPI handlers do not contain scheduling rules or remote orchestration. Domain code does not import FastAPI, SQLAlchemy, Bolna, Retell, or AWS SDK classes.

## 8. Voice tool contracts

Every production tool uses HTTPS POST, bearer/HMAC authentication, strict JSON schemas, and this
response envelope. The hosted assignment staging environment may use its generated ALB HTTP
endpoint when no controlled domain/certificate is available; authentication and schema protections
remain identical:

```json
{
  "status": "ok",
  "operation_id": "opaque-id",
  "spoken_summary": "Short language-neutral fact payload for the agent",
  "data": {},
  "next_actions": [],
  "retryable": false
}
```

`spoken_summary` contains facts, not polished dialogue. The agent renders it in the caller's current language.

### `bootstrap_call`

Input: platform call ID, direction, caller number, called number, optional campaign ID.

Output: new/returning/shared-number classification, candidate first names only, dropped-call checkpoint, missed-callback context, preferred language if known, and fields still required.

Rules:

- Never select a patient when multiple records share the number.
- A recognized number does not remove the full-name requirement.
- Resume only an eligible recent incomplete call, with a short acknowledgement.

### `search_availability`

Input: backend call-session ID, one to four targets (business, appointment type, and
eligible practitioners), and a timezone-aware date/time window. A named-branch request
uses one target; an earliest request includes every relevant branch target in one call.

Output: up to three globally ranked slots with session-bound availability tokens and
search-scope metadata (`target_count`, total/returned counts, and truncation state).

Rules:

- Always performs fresh PMS calls.
- `earliest` fans out across all eligible branches and practitioners, then globally sorts.
- Never reuses a prior result after any scheduling constraint changes.
- Named-branch queries must fail explicitly if branch mapping is invalid.

### `book_appointment`

Input: backend call-session ID, availability token, selected slot ID, full patient name, patient selector/new-patient data, and idempotency key.

Output: `confirmed`, `conflict`, `pending_verification`, or validation status, plus authoritative branch, practitioner, local date/time, and fee disclosure state.

### `list_patient_appointments`

Requires an unambiguous patient selection. Returns cancellable/reschedulable synthetic appointments without exposing unrelated patient information.

### `reschedule_appointment`

Input: selected existing appointment, new availability token/slot, idempotency key, and confirmation that any applicable fee was disclosed.

### `cancel_appointment`

Input: selected appointment, reason, idempotency key, and confirmation that applicable policy was disclosed.

### `save_call_checkpoint`

Stores only the durable workflow facts needed to resume. The model's entire free-form context is not treated as authoritative state.

### `log_follow_up`

Creates a callback request for human requests, clinical questions, unresolved PMS state, or unsupported workflows. It never claims that a live transfer occurred.

## 9. Date, policy, and language rules

- Resolve all caller-relative dates in `Asia/Kolkata` using the call start timestamp.
- Return ISO timestamps and explicit local display fields from tools.
- The LLM never calculates weekdays, fee windows, or UTC conversion.
- “Morning,” “afternoon,” “after work,” and weekday recurrence are normalized by deterministic backend rules with tests.
- The current date must be injected; never hardcode assignment example dates.
- Pure English turns receive English; pure Hindi turns receive Hindi; code-switch only when the caller does.
- Store language per turn for evaluation, but never rely on a translation dictionary.
- Normalize display names for pronunciation and retain source names separately.
- A fee is mentioned only when a deterministic policy evaluator says it applies.

## 10. Production AWS specification

### Network and compute

- One VPC spanning two availability zones.
- Public subnets for ALB; private application subnets for ECS; private database subnets for RDS.
- HTTPS listener using ACM; HTTP redirects to HTTPS.
- ECS Fargate service with two production tasks, rolling deployment, circuit breaker, health checks, graceful shutdown, and autoscaling.
- Separate worker deployment or Lambda consumers for asynchronous jobs; synchronous booking remains in the API request path until definitive/pending status is known.
- RDS PostgreSQL encrypted with KMS, Multi-AZ, automated backups, point-in-time recovery, deletion protection, and restricted security group.

### Egress choice

Private ECS tasks need outbound access to Cliniko, the voice platform, and model providers. Compare before applying:

| Choice | Benefit | Cost/risk |
|---|---|---|
| NAT gateway per AZ | Conventional HA egress | Highest fixed cost |
| One NAT gateway | Lower cost | Cross-AZ dependency and egress single point |
| Public-IP ECS tasks with strict security groups | Avoids NAT cost | Weaker isolation story |

Production profile uses one NAT gateway per AZ. A review/staging profile may use one NAT only when labelled as non-HA.

### Managed services

- SQS standard queue and DLQ for PMS reconciliation and follow-up delivery.
- Secrets Manager for all service credentials; ECS task role receives only named secrets.
- CloudWatch Logs with JSON events and retention policy.
- CloudWatch metrics/alarms for ALB 5xx, target health, p95 tool latency, ECS restarts, RDS connections/storage, queue age, DLQ messages, and pending PMS operations.
- CloudTrail enabled for control-plane audit.
- Route 53/custom domain is optional; the ALB endpoint is sufficient if stable and TLS-valid.
- WAF is a production hardening option; endpoint HMAC, rate limits, and strict schemas are mandatory regardless.

### Infrastructure as code

Terraform owns network, IAM, ALB, ECS, ECR, RDS, SQS/DLQ, KMS, Secrets Manager references, logs, alarms, and outputs. Secret values are injected outside Terraform state.

Environments:

| Profile | ECS | RDS | NAT | Purpose |
|---|---|---|---|---|
| `staging` | 1 task | Single-AZ | 1 | Cost-controlled integration and reviewer validation |
| `production` | 2+ tasks | Multi-AZ | 2 | Production-grade availability profile |

The submitted README must state which profile is actually live.

## 11. Security controls

- Never log full phone numbers, API keys, authorization headers, full transcripts, or dates of birth.
- Encrypt transport and storage.
- Verify webhook signature when supported; combine with replay window and event-ID uniqueness.
- HMAC-sign platform tool calls where configurable; otherwise use rotating bearer tokens and source restrictions.
- Separate API and migration database roles.
- Apply least-privilege IAM task/worker roles.
- Set explicit connect/read/write timeouts and bounded retries with jitter.
- Redact request/response samples before committing evaluation artifacts.
- Use synthetic patients only.
- Include dependency scanning, secret scanning, SAST, and container image scanning in CI.

## 12. Observability contract

Correlation identifiers:

```text
platform_call_id -> call_session_id -> tool_call_id
                 -> booking_operation_id -> pms_attempt_id
```

Each tool emits spans for request validation, PostgreSQL, each Cliniko request, queue publication, and total latency. Platform ASR/LLM/TTS traces are joined by call ID after the call.

No metric is reported without its unit, percentile, sample count, language bucket, environment, platform/provider versions, and measurement window.

## 13. Proposed repository structure

```text
2care-clinic-voice-agent/
  AGENTS.md
  README.md
  pyproject.toml
  compose.yaml
  .env.example
  .github/workflows/
    ci.yml
    security.yml
  app/
    api/
    application/
    domain/
    infrastructure/
    main.py
  migrations/
  tests/
    unit/
    integration/
    contract/
    concurrency/
  evals/
    scenarios/
    acoustic_manifest/
    reports/
    runner/
  data/
    clinic_source_manifest.yaml
    demo_clinic.yaml
  integrations/
    voice/
      common/
      bolna/
      retell/
    pms/
      cliniko/
      mock/
  infra/
    terraform/
      modules/
      environments/staging/
      environments/production/
  scripts/
    bootstrap_cliniko.py
    verify_deployment.py
  docs/
    architecture.md
    decisions/
    deployment.md
    evaluation.md
    prompt.md
    runbook.md
```

The repository name is proposed and may be changed before creation. Do not commit generated Cliniko mappings, secrets, recordings containing PII, Terraform state, or local evaluation caches.

## 14. Test-driven implementation sequence

### Slice 1: provenance and time

Write failing tests for source manifest validation, timezone conversion, weekday resolution, day-part parsing, and fee windows. Implement only enough domain code to pass.

### Slice 2: persistence and conflicts

Write migrations and PostgreSQL integration tests. Prove a 20-request race yields one reservation and nineteen explicit conflicts.

### Slice 3: mock PMS contract

Write gateway contract tests first. Implement patient lookup, availability, lifecycle, idempotent replay, timeout-after-write, transient failure, and conflict fixtures.

### Slice 4: application tools

Test every tool through HTTP with the mock PMS. Verify shared phones, full-name gate, global earliest search, stale-query rejection, branch matching, and honest pending responses.

### Slice 5: Cliniko adapter

Run the same contract suite against a sandbox/trial fixture where safe. Add rate-limit, pagination, timeout, and reconciliation behavior.

### Slice 6: durable call recovery

Test disconnect checkpoints, resumption eligibility, missed callbacks, duplicate webhook events, and follow-up creation.

### Slice 7: voice integration

Freeze the measured platform/providers. Provision the agent from versioned config where supported, then run prompt/tool and acoustic suites.

### Slice 8: AWS deployment

Deploy staging through Terraform, run migrations as a controlled one-off task, smoke-test externally, then deploy/validate the production profile.

## 15. Acceptance gates before submission

- Both branches and two practitioners visible through the mapped appointment types in Cliniko.
- Synthetic patients and histories exercise every identity scenario.
- Live number works independently in English, Hindi, and Hinglish.
- All core assignment scenarios pass on real calls.
- Exactly one winner in concurrent slot-race tests.
- No confirmation on unknown PMS outcome.
- Per-language reports include raw denominators and p50/p95/p99 latency.
- Fresh clone runs offline tests without Cliniko or voice credentials.
- Live environment profile and limitations are stated honestly.
- No secret or real patient data appears in Git history or artifacts.

## 16. Remaining decisions

Before implementation begins:

1. Approve or rename the proposed repository `2care-clinic-voice-agent`.
2. Set a monthly AWS and telephony budget.
3. Confirm whether the deployed environment must use the full production profile during the review window or whether staging may be live with the production profile demonstrated separately.
4. Obtain Bolna and Retell access for the measured selection.
5. Obtain Cliniko trial access and confirm its practitioner setup limits.
6. Approve this specification.
