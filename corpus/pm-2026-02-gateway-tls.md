---
id: pm-2026-02-gateway-tls
title: "Postmortem 2026-02-20: total outage from an expired TLS certificate"
doc_type: postmortem
service: gateway
version: v2
status: active
visibility: everyone
updated_at: 2026-02-22
---

# Postmortem 2026-02-20: total outage from an expired TLS certificate

**Duration:** 22 minutes of total unavailability.
**Impact:** All external traffic failed TLS handshake. No requests reached any service.

## Timeline

- **06:00** The wildcard certificate for the public domain expires.
- **06:00** Every client fails the handshake. The gateway is up and healthy; nothing gets
  past TLS. All service-level dashboards look perfect — traffic simply goes to zero.
- **06:03** Synthetic external probe alerts. This was the only alert that fired, and it is
  the only reason detection took 3 minutes rather than until business hours.
- **06:08** On-call confirms expiry with `openssl s_client`.
- **06:14** Renewal triggered manually. cert-manager had failed the automated renewal 30
  days earlier because a DNS-01 challenge could not complete after a change to the zone's
  delegation.
- **06:22** New certificate served. Traffic recovers immediately.

## Root cause

Automated renewal had been failing silently for 30 days. cert-manager recorded the failure
in a `CertificateRequest` condition and emitted a Kubernetes event; neither was wired to an
alert. The 30-day renewal window was consumed entirely by unnoticed failures.

The DNS delegation change that broke the challenge was made by a different team, for an
unrelated reason, and had no reason to know it would affect certificate issuance.

## What we changed

- `certmanager_certificate_expiration_timestamp_seconds` pages at 14 days and again at
  7 days, regardless of renewal state.
- A failing `CertificateRequest` pages immediately. A renewal that fails is an incident on
  the day it fails, not on the day the certificate expires.
- Certificate expiry is part of the "all routes failing at once" branch of the gateway
  triage runbook, because service dashboards cannot see this failure.

## What went well

The synthetic external probe was the only signal that worked. Everything measured from
inside the perimeter was blind to a failure at the perimeter.

## Lesson

Monitor the thing that expires, not the process that is supposed to renew it. And keep at
least one probe outside your own network.
