---
id: rb-gateway-timeouts
title: "Runbook: gateway 5xx and timeout triage"
doc_type: runbook
service: gateway
version: v2
status: active
visibility: everyone
updated_at: 2026-06-15
---

# Runbook: gateway 5xx and timeout triage

**Page trigger:** `gateway_5xx_ratio > 0.01` over 5 minutes on any route.

This runbook decides *which team owns the incident*. It rarely ends with a gateway change.

## Step 1: separate 502 from 504

They have different causes and different owners.

    logcli query '{app="gateway"} | json | status>=500' --since 15m \
      | jq -r '[.route, .status, .upstream_status] | @tsv' | sort | uniq -c | sort -rn

- **504** — the upstream did not respond before the route deadline from ADR-0019. The
  upstream is slow. Owner: the route's team.
- **502 with `upstream_status` empty or `0`** — the gateway could not get a usable response
  at all: connection refused, reset, or an unparseable body. Owner: the route's team, but
  the fault is below the request handler. Connection pool saturation lands here.
- **502 with `upstream_status: 502`** — the upstream itself returned 502. You are one hop
  too high; go to that service's dependency.
- **503 with `Retry-After`** — no healthy instances. Owner: whoever owns the deployment.

## Step 2: is it one route or all of them?

Group by route. One route means a service problem. All routes at once means the gateway,
TLS, or something shared — check certificate expiry, the shared middleware version, and
the global rate limiter before assuming a service is at fault.

## Step 3: hand off with evidence

Page the owning team from the service ownership policy. Include the route, the 502/504
split, the `upstream_status` distribution and the time the ratio crossed the threshold.
"The gateway is returning 5xx" is not an actionable handoff.

For checkout specifically, the most common cause since the v4 migration is outbound
connection pool saturation, not a dependency being down. Point the owner at the checkout
502 runbook rather than making them rediscover it.

## Do not

Do not raise a route deadline to make a page stop. It converts a fast failure into a slow
one, holds client connections open longer, and hides the real problem. Deadline changes go
through the route's team and ADR-0019.
