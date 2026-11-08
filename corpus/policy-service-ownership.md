---
id: policy-service-ownership
title: "Policy: service ownership and escalation contacts"
doc_type: policy
service: platform
status: active
visibility: everyone
updated_at: 2026-08-19
---

# Policy: service ownership and escalation contacts

Every production service has exactly one owning team. The owning team holds the on-call
rotation, the error budget and the final say on architectural change.

| Service | Owning team | Tech lead | Slack | Escalation after 15 min |
|---|---|---|---|---|
| auth-svc | Identity | Nadia Yurchenko | `#team-identity` | Identity manager, then platform on-call |
| checkout-svc | Payments | Bohdan Reshetnyk | `#team-payments` | Payments manager, then incident commander |
| catalog-svc | Discovery | Iryna Palamar | `#team-discovery` | Discovery manager |
| notify-svc | Messaging | Taras Levchuk | `#team-messaging` | Messaging manager |
| ledger-svc | Money | Olena Kravets | `#team-money` | Money manager, then finance controller |
| gateway | Platform | Serhii Voznyi | `#team-platform` | Platform on-call, always |
| admin-console | Internal Tools | Kateryna Bilyk | `#team-internal-tools` | Internal Tools manager |
| partner-feed-exporter | Discovery | Iryna Palamar | `#team-discovery` | Discovery manager |

## Cross-cutting ownership

`gateway` is owned by Platform but its route configuration is owned by the team behind
each route. A gateway change that only touches one route is that team's change to make;
anything touching shared middleware, TLS or global rate limits belongs to Platform.

Shared libraries — the HTTP client wrapper that implements the ADR-0055 retry budget, the
JWKS verification helper from ADR-0042 — are owned by Platform. A bug in them is a
Platform incident even when it surfaces in someone else's service.

## Unowned services

A service with no entry in this table must not be deployed to production. If you find one
running, open a Platform ticket; do not adopt it informally.

## Keeping this current

This table is reviewed at the start of every quarter and on any team reorganisation. Other
documents — including the deprecation register — sometimes name teams informally. This
table wins.
