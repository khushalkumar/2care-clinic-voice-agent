# Database restore and disaster recovery

Target policy: production RDS Multi-AZ, 14-day backups, encrypted snapshots, and point-in-time
recovery. Actual RPO/RTO remain unverified until a staging restore rehearsal is timed.

1. Disable new voice mutations while preserving an informational outage message.
2. Restore the latest approved snapshot/PITR into an isolated subnet and security group.
3. Run `alembic current`, then apply only forward migrations required by the deployed image.
4. Verify call sessions, idempotency keys, reservations, outbox, and pending operations.
5. Reconcile every pending PMS operation before enabling writes.
6. Run synthetic bootstrap, search, booking race, cancellation, and callback recovery tests.
7. Point a staging task at the restored database, observe alarms, then promote through review.
8. Record measured recovery point and recovery time; update this runbook with results.
