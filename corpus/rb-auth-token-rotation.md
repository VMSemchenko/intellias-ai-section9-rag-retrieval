---
id: rb-auth-token-rotation
title: "Runbook: rotating the auth-svc token signing keys"
doc_type: runbook
service: auth-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-05-02
---

# Runbook: rotating the auth-svc token signing keys

Scheduled quarterly, and immediately on suspected compromise.

## Why the order matters

Consumers cache the JWKS document for 600 seconds and verify locally. If you sign with a
key that is not yet in every consumer's cached JWKS, every request carrying a new token
fails verification. The April 2026 outage was exactly this mistake.

## Procedure

1. Generate the new EdDSA keypair in the HSM. Note the new `kid`.
2. **Publish first.** Add the public key to the JWKS document. Do not change the signing
   key yet.
3. **Wait 15 minutes.** Longer than the 600-second consumer cache TTL, with margin. Verify
   `auth_jwks_fetch_total` shows a full cycle of refreshes across consumers.
4. Switch the active signing key to the new `kid`. New access tokens are signed with it.
5. **Wait 10 minutes** — longer than the 300-second access token lifetime. Every token
   signed by the old key has now expired.
6. Remove the old public key from the JWKS document.
7. Destroy the old private key in the HSM.

## Emergency rotation

On suspected key compromise you cannot wait 15 minutes. Accept the failures:

1. Publish the new key and switch signing in one change.
2. Immediately revoke all refresh tokens: `POST /v4/token/revoke/all`. Every user
   re-authenticates.
3. Expect a spike of `401` for up to 600 seconds while consumer JWKS caches expire.
4. Announce in `#incident` before you start. This is a user-visible logout event.

## Verification

`auth_token_verify_failures_total` must return to zero within 15 minutes of step 4. If it
does not, at least one consumer is not refreshing its JWKS cache — find it via the
`consumer` label and page its owning team.
