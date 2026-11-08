---
id: pm-2026-06-security-scan
title: "Postmortem 2026-06-24: findings from the Q2 external penetration test"
doc_type: postmortem
service: platform
status: active
visibility: security-team
updated_at: 2026-06-28
---

# Postmortem 2026-06-24: findings from the Q2 external penetration test

**Restricted.** Visible to the security team only. Do not quote findings outside
`#team-security` until the remediation column reads "closed" for every row.

## Summary

An external firm tested the public perimeter and the partner API over two weeks. Four
findings, none rated critical, two rated high.

| # | Finding | Rating | Status |
|---|---|---|---|
| 1 | Rate limiter fails open on Redis unavailability, permitting unlimited login attempts during a Redis restart | high | mitigated |
| 2 | v3 session introspection response distinguishes "unknown session" from "expired session", enabling session-id enumeration | high | closed |
| 3 | Webhook signature verification example in partner docs parses JSON before verifying, encouraging partners to verify the wrong bytes | medium | closed |
| 4 | Error responses from the ledger internal API include the database role name | low | closed |

## Finding 1 in detail

The fail-open behaviour is deliberate and documented in ADR-0063: a rate limiter that fails
closed converts a Redis blip into a full outage. The tester's point is narrower and correct —
the *login* route should not inherit that trade-off, because for login the rate limiter is a
security control rather than a capacity control.

Mitigation: login and token exchange now enforce a local per-process fallback limit when
Redis is unavailable. The global fail-open behaviour is unchanged for all other routes.
ADR-0063's fail-open statement remains accurate for everything except these two routes, and
has been amended to say so.

## Finding 2 in detail

`POST /v3/session/introspect` returned `{"active": false}` for an expired session and a
`404`-shaped problem document for an unknown one. Both now return the identical
`{"active": false}` body. Closed.

## Actions still open

None. Finding 1 remains "mitigated" rather than "closed" pending the v3 sunset, after which
the login path moves entirely to v4 token exchange.

## Lesson

A trade-off that is correct for a whole system can be wrong for one route inside it.
"Documented and deliberate" is not the same as "right everywhere".
