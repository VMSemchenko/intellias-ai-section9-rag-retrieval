---
id: pm-2026-07-checkout-latency
title: "Postmortem 2026-07-01: checkout p99 latency and 502s after the v4 auth migration"
doc_type: postmortem
service: checkout-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-07-04
---

# Postmortem 2026-07-01: checkout p99 latency and 502s after the v4 auth migration

**Duration:** 47 minutes of degraded checkout, 11 minutes of hard failure.
**Impact:** ~4,100 order submissions failed with a gateway error. No data loss.

## Timeline

- **14:12** `checkout-svc` v4 token exchange rollout completes to 100% of pods.
- **14:39** First `checkout_edge_5xx_ratio` alert. Edge 502 rate 0.6%.
- **14:44** On-call joins. `checkout-svc` dashboards show normal handler latency and an
  almost flat error rate. This cost us the next twenty minutes.
- **15:02** 502 rate reaches 8%. Checkout is effectively down for one request in twelve.
- **15:08** On-call notices `checkout_httpx_pool_pending` climbing since 14:20 and a
  growing count of `PoolTimeout`. The connection pool, not a dependency, is the problem.
- **15:14** `max_connections` raised from the library default to 200 by config push.
  Pending queue drains within 90 seconds.
- **15:26** Error ratio back to baseline. Incident closed.

## Root cause

The v4 token exchange added one outbound HTTPS request per token lifetime that did not
exist under the v3 cookie flow. `checkout-svc` was still using the inherited `httpx`
default of 10 keepalive connections. Under afternoon load the pool saturated, requests
queued for a connection, and once the queue wait exceeded the client timeout they failed
while *acquiring* a connection rather than during the request.

Two things made this hard to see:

1. The failures never reached a request handler, so `checkout-svc`'s own error rate and
   latency histograms looked healthy. The only place the failure was visible was the
   edge, which reports it as a generic upstream gateway error.
2. Our retry policy treated the acquisition failure as a transport error and retried it
   immediately, adding load to an already saturated pool.

## What we changed

- Pool sizes are derived from measured concurrency. See ADR-0061.
- `PoolTimeout` is excluded from the retry classifier.
- `checkout_httpx_pool_pending` is now a first-class alert, not a dashboard panel.
- The checkout 502 runbook now begins with "check the outbound pool", because the
  service-level dashboards will lie to you in this failure mode.

## What we did not change

We did not revert to v3. The migration is correct; the capacity work that should have
accompanied it was missing.

## Lesson

A migration that adds an outbound call is a capacity change, not just a code change. The
pre-migration checklist now includes re-deriving outbound pool limits.
