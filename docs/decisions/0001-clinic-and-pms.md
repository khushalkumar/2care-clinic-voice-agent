# ADR 0001: Sourced Clinic and PMS Ownership

Status: accepted on 2026-07-18.

## Decision

Use a limited demonstration of Physiotattva's Jayanagar and Indiranagar branches. Public branch, practitioner, and service facts carry field-level provenance. Schedules, patients, appointments, and operational mappings are synthetic.

Cliniko is the live operational PMS. PostgreSQL provides local reservation conflicts, idempotency, call state, audit, and recovery. A contract-compatible mock PMS makes the repository independently testable.

## Consequences

- The project must display a no-affiliation and synthetic-data disclaimer.
- The agent must never describe synthetic availability as the clinic's real schedule.
- Clean-clone tests cannot require Cliniko credentials.
