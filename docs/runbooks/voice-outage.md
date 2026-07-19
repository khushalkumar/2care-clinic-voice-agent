# Voice platform or number outage

1. Check Bolna status, execution logs, inbound number mapping, carrier status, and backend health separately.
2. If the backend is healthy, do not redeploy it to fix a carrier incident.
3. If tool calls fail authentication, compare timestamp skew, event IDs, configured headers, and key version without printing secrets.
4. Disable booking claims when tools are unavailable; the agent must not simulate confirmations.
5. Preserve missed-call context and create follow-ups for known outbound campaigns.
6. Restore routing with one English, one Hindi, and one Hinglish canary before general traffic.

If Bolna repeatedly fails a hard language/tool gate and the recorded Retell bake-off passes it,
execute the documented provider reversal rather than weakening acceptance criteria.
