---
id: rb-checkout-rollback
title: "Runbook: rolling back a checkout deploy (blue/green)"
doc_type: runbook
service: checkout-svc
version: v3
status: superseded
visibility: everyone
updated_at: 2025-09-30
---

# Runbook: rolling back a checkout deploy (blue/green)

**Superseded.** `checkout-svc` no longer runs a blue/green topology. These steps reference
load balancer target groups that no longer exist. Use the current checkout rollback
runbook. This document is retained only because two other runbooks still link to it.

## Procedure (historical)

1. Identify the currently active colour: `aws elbv2 describe-listeners --listener-arn ...`
   and read the forwarded target group.
2. Confirm the standby colour is healthy — all targets `healthy` in
   `describe-target-health`.
3. Flip the listener rule to the standby target group. Traffic moves in under 5 seconds.
4. Do not terminate the failed colour. Keep it for inspection until the incident review.
5. Announce the flip in `#incident` with the two commit SHAs.

## Why this was replaced

Blue/green required double capacity for checkout at all times, which was expensive, and
the flip was all-or-nothing: a bad deploy affected 0% or 100% of traffic with nothing in
between. Rolling deploys with a canary stage let us catch a bad build at 5% of traffic.

The v4 deployment topology also introduced per-pod token exchange state that does not
survive an instant traffic flip cleanly.
