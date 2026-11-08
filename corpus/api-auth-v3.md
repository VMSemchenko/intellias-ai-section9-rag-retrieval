---
id: api-auth-v3
title: "API reference: auth-svc v3 session endpoints"
doc_type: api
service: auth-svc
version: v3
status: superseded
visibility: everyone
updated_at: 2025-01-22
---

# API reference: auth-svc v3 session endpoints

**Superseded.** Use the v4 token endpoints. These endpoints return `Deprecation: true`
and `Sunset: Wed, 31 Dec 2026 23:59:59 GMT` on every response.

Base path `/v3`.

## POST /v3/session

Authenticate and receive a session cookie.

Response `204` with `Set-Cookie: sid=...; Secure; HttpOnly; SameSite=Lax; Max-Age=43200`.

## POST /v3/session/introspect

Resolve a session cookie to a subject. This is the call ADR-0042 removed from the hot
path.

Request:

    { "sid": "s_01H..." }

Response `200`:

    { "active": true, "subject": "u_01H...", "tenant": "t_01H...",
      "roles": ["customer"], "expires_at": "2026-08-26T18:00:00Z" }

An inactive session returns `200` with `{"active": false}` — not `401`. Callers that
treat any `200` as authenticated have a security bug; check the `active` field.

Response is cacheable for 30 seconds. Longer caching defeats immediate revocation, which
was the entire reason for choosing opaque sessions in ADR-0031.

## DELETE /v3/session

Logout. Deletes the session record; revocation is immediate.

## Migration notes

There is no direct equivalent of `introspect` in v4 — that is the point. Verify the
signature locally against the JWKS instead of asking `auth-svc`. See ADR-0042 and the v4
API reference.
