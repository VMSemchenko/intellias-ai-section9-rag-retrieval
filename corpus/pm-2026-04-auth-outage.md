---
id: pm-2026-04-auth-outage
title: "Postmortem 2026-04-14: platform-wide 401s after signing key rotation"
doc_type: postmortem
service: auth-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-04-16
---

# Postmortem 2026-04-14: platform-wide 401s after signing key rotation

**Duration:** 9 minutes.
**Impact:** Every authenticated request across all services failed with `401` for the
first 6 minutes, tapering as consumer caches expired.

## Timeline

- **09:00** Quarterly key rotation begins. Engineer publishes the new public key to the
  JWKS document **and** switches the active signing key in the same deploy.
- **09:01** Consumers still holding a cached JWKS reject every new token: the `kid` in the
  header is not in their cached key set.
- **09:02** `auth_token_verify_failures_total` alert fires. Every service's error rate
  spikes simultaneously, which correctly pointed at auth rather than any single consumer.
- **09:04** Engineer recognises the cause and reverts the signing key to the old `kid`.
- **09:09** Verification failures return to zero as caches refresh.

## Root cause

Publishing a key and using it to sign are two changes that must be separated by longer
than the consumer JWKS cache TTL of 600 seconds. The runbook said so. The runbook was not
open during the change.

The contributing factor is that the rotation was a single Terraform apply — the tooling
made the wrong thing easy and the right thing manual.

## What we changed

- Rotation is now a two-stage pipeline with an enforced 15-minute wait between stages. It
  is not possible to publish and switch in one apply.
- The runbook's step order is duplicated as comments in the Terraform module.
- Added `auth_jwks_active_kid_age_seconds` so we can see how long a key has been published
  before it is used.

## What went well

Detection was immediate and the signal pointed at the right service. Revert took under
two minutes.

## Lesson

When a procedure's correctness depends on waiting, encode the wait in the tooling. A
documented wait is a wait that will eventually be skipped.
