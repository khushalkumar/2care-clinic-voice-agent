# Voice Integrations

Retell is the live assignment platform. Bolna remains as the documented comparison baseline, but
the shipped implementation uses one Retell agent and one Twilio Elastic SIP Trunk.

Live inbound PSTN path:

```text
+1 417 742 8846 -> Twilio Elastic SIP Trunk 2care-retell-staging -> sip:sip.retellai.com -> Retell custom telephony number 2care Twilio staging -> 2care Physiotattva Bilingual Receptionist (Staging)
```

Outbound from this Retell custom number is intentionally left disabled until Retell identity
verification is complete.
