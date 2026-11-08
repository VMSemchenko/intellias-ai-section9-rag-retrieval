---
id: api-auth-v4
title: "API reference: auth-svc v4 token endpoints"
doc_type: api
service: auth-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-06-09
---

# API reference: auth-svc v4 token endpoints

Base path `/v4`. All endpoints require TLS. Errors follow RFC 9457 problem details.

## POST /v4/token

Exchange a refresh token for an access token.

Request:

    { "refresh_token": "rt_...", "device_id": "d_01H..." }

Response `200`:

    { "access_token": "eyJ...", "token_type": "Bearer",
      "expires_in": 300, "scope": "orders:write catalog:read" }

`expires_in` is always 300 seconds. Do not hard-code it; read the field.

| Status | Meaning | Retry |
|---|---|---|
| `400` | malformed body | no |
| `401` | refresh token revoked, expired or unknown | no — re-authenticate |
| `403` | device id does not match the token binding | no |
| `429` | per-device exchange rate limit | yes, honour `Retry-After` |
| `503` | signing key unavailable | yes, per the ADR-0055 synchronous budget |

Rate limit: 20 exchanges per device per minute.

## GET /v4/.well-known/jwks.json

Public keys for local verification. `Cache-Control: max-age=600`. Consumers must cache
for the full 600 seconds and must tolerate an unreachable JWKS endpoint by continuing to
use the cached document — a fetch failure is not an authentication failure.

Key rotation publishes the new key here **before** it is used to sign, so a consumer with
a warm cache never sees an unknown `kid`. The rotation procedure is in the auth token
rotation runbook.

## POST /v4/token/revoke

Revokes a refresh token immediately. Access tokens already issued remain valid until they
expire — up to five minutes. This is the trade-off accepted in ADR-0042.
