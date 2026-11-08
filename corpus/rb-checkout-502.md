---
id: rb-checkout-502
title: "Runbook: checkout returns 502 Bad Gateway"
doc_type: runbook
service: checkout-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-07-06
---

# Runbook: checkout returns 502 Bad Gateway

**Page trigger:** `checkout_edge_5xx_ratio > 0.02` for 5 minutes.

## What the user sees

The order review page fails to submit and the browser shows the generic error page. The
edge has returned `502 Bad Gateway`. `checkout-svc` may look healthy from the inside: its
own request logs can be almost empty, because the requests that fail never reached a
handler.

## Triage, in order

1. **Confirm where the 502 is produced.** Check the edge access log for the route. If the
   `upstream_status` field is `-` or `0`, the gateway never got a usable response and the
   fault is in `checkout-svc` or below it. If `upstream_status` is `502`, something
   *behind* checkout produced it and you are chasing the wrong service.

2. **Check the outbound pool before anything else.** This is the most common cause since
   the v4 migration. Look at `checkout_httpx_pool_pending` and the count of `PoolTimeout`
   errors. A non-zero pending queue with rising `PoolTimeout` means the pool is saturated,
   not that a dependency is down. The sizing decision and the reasoning behind it are in
   ADR-0061 — read it before changing any numbers.

3. **Check the auth token exchange.** `checkout-svc` calls `POST /v4/token` per token
   lifetime. If `auth-svc` is slow, every checkout request holds a pooled connection for
   longer and the pool saturates at a lower request rate than usual. Correlate with
   `auth_token_exchange_p99`. If that is elevated, treat this as an `auth-svc` incident
   and follow the auth runbook instead.

4. **Check the route deadline.** The edge cancels a request that exceeds the route
   deadline and reports it as a gateway error. Compare the p99 of the handler against the
   configured deadline for the route.

## Mitigations

- Pool saturation: raise `max_connections` via config and restart rolling. This is a
  stop-gap; the permanent fix is re-deriving the pool size per ADR-0061.
- `auth-svc` slow: no checkout-side mitigation. Escalate to the auth on-call.
- Bad deploy in the last 30 minutes: roll back. Follow the current checkout rollback
  runbook — note that the older blue/green rollback runbook is superseded and its steps
  will not work against the v4 deployment topology.

## Do not

Do not add retries to `PoolTimeout`. It is a saturation signal and retrying it makes the
outage worse. ADR-0061 explains why.
