# ADR 0004: Atomic Booking Persistence and Contention Control

Status: accepted on 2026-07-18.

## Context

The assignment requires conflict and double-booking protection at database write time. A check-then-insert flow is unsafe because concurrent callers can observe the same available slot.

Testing 20 simultaneous PostgreSQL GiST exclusion inserts also showed that conflicting index insertions can produce a deadlock between losing transactions. PostgreSQL preserves correctness, but callers need a stable conflict result rather than an avoidable database deadlock.

## Decision

- PostgreSQL's partial GiST exclusion constraint is the authoritative overlap guard for active `held`, `pending_remote`, and `confirmed` ranges.
- Appointment duration and buffer are represented by the stored half-open reservation range.
- The booking store takes a transaction-scoped advisory lock derived from `practitioner_key` before inserting a reservation. This serializes same-practitioner contenders and reduces GiST deadlocks; different practitioners remain concurrent.
- The advisory lock is an operational contention control, not the correctness boundary. A writer that omits it is still protected by the exclusion constraint.
- Booking operation, slot reservation, and outbox event are inserted in one transaction.
- No external PMS request is made while that transaction is open.
- `idempotency_key` is protected by a named unique constraint. Replays return the original operation and reservation without producing a second outbox event.
- A losing overlap rolls back its operation, reservation, and outbox together.

## Consequences

- The API can translate overlaps and rare deadlock SQL states into an explicit slot-conflict result.
- All booking writers must use the booking store unless they are migration/repair tooling with equivalent safety.
- Same-practitioner booking throughput is serialized for the short local transaction, which is acceptable because external calls occur afterward.
- Integration tests require real PostgreSQL; SQLite cannot validate the constraint or locking behavior.

## Evidence

- A 20-way real PostgreSQL race produces exactly one committed reservation.
- Sequential and ten-way concurrent idempotent requests produce one operation, one reservation, and one outbox event.
- A losing overlap leaves no orphan operation or outbox row.
