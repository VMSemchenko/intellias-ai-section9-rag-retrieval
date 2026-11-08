---
id: policy-deprecation
title: "Policy: API deprecation and the current deprecation register"
doc_type: policy
service: platform
status: active
visibility: everyone
updated_at: 2026-08-11
---

# Policy: API deprecation and the current deprecation register

## The rule

An interface is deprecated by an ADR that names its replacement. From the date that ADR
is accepted:

- No new consumers. A new dependency on a deprecated interface requires a written
  exception from the owning team.
- Minimum 6 months before removal, or one quarter after the last consumer migrates,
  whichever is later.
- The owning team publishes a migration guide before, not after, the deprecation lands.
- Deprecated endpoints return a `Deprecation` and a `Sunset` header on every response.

## Current deprecation register

### v3 session cookie authentication (ADR-0031 → ADR-0042)

Deprecated 2026-05-18. Target removal 2026-12-31.

Services still calling `POST /v3/session/introspect` as of the last audit:

| Service | Owner team | Migration status | Blocker |
|---|---|---|---|
| catalog-svc | Discovery | not started | needs partner-facing token support |
| notify-svc | Messaging | in progress | webhook signing still reads the session subject |
| ledger-svc | Money | not started | no owner capacity allocated this quarter |
| admin-console | Internal Tools | in progress | — |

`checkout-svc` and `gateway` completed migration in July 2026.

Team names above are informal. The authoritative owner, on-call rotation and escalation
contact for each service are in the service ownership policy — do not page a team based
on this table alone.

### v1 catalog search response envelope (ADR-0022 → ADR-0071)

Deprecated 2026-02-02. Target removal 2026-09-30. One remaining consumer:
`partner-feed-exporter`, owned by Discovery.

### Legacy webhook fan-out from notify-svc (ADR-0038 → ADR-0080)

Not yet deprecated. ADR-0080 is a draft and the register will be updated when it is
accepted. Do not treat the draft as a deprecation.

## Exceptions granted

None currently open.
