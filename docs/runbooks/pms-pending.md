# PMS failure and pending verification

Trigger: elevated PMS errors/rate limits, or a booking operation remains
`pending_verification` beyond the alert threshold.

1. Use the operation ID to inspect status, attempt code, local reservation, and outbox state.
2. Check Cliniko status and rate-limit headers. Never retry a create blindly with a new key.
3. Run the reconciliation worker with the original idempotency key and persisted provider IDs.
4. If the remote appointment exists, record its ID and confirm locally. If definitively absent
   and retries are safe, retry once through the gateway. If still unknown, keep it pending.
5. Create or retain a human follow-up and tell callers only that verification is in progress.
6. Release capacity only after remote absence is definitive. Never delete audit records.

For 401/403, stop mutation traffic and rotate/fix credentials. For 429, honor reset time and
reduce worker concurrency. For malformed responses or repeated 5xx, preserve the queue and use
the mock fault suite to reproduce before deploying a fix.
