---
id: rb-checkout-rollback-v4
title: "Runbook: rolling back a checkout deploy (rolling + canary)"
doc_type: runbook
service: checkout-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-07-08
---

# Runbook: rolling back a checkout deploy (rolling + canary)

**Active.** Supersedes the blue/green rollback runbook, whose target-group steps no longer
apply.

## Decide first: roll back or roll forward

Roll back if the fault is in the new build. Roll forward if the fault is configuration or
capacity — a rollback will not fix a pool that is sized too small, and you will lose 20
minutes discovering that. See ADR-0061 and the checkout 502 runbook.

## Rollback

1. Find the previous known-good revision:

       kubectl -n checkout rollout history deploy/checkout-svc

2. Halt the in-flight rollout first. Rolling back while a rollout is progressing produces
   a mixed fleet:

       kubectl -n checkout rollout pause deploy/checkout-svc

3. Undo to the previous revision:

       kubectl -n checkout rollout undo deploy/checkout-svc --to-revision=<N>
       kubectl -n checkout rollout resume deploy/checkout-svc
       kubectl -n checkout rollout status deploy/checkout-svc --timeout=5m

4. Watch `checkout_edge_5xx_ratio` and `checkout_httpx_pool_pending` for 5 minutes. A
   rollback that fixes the error rate but leaves the pending queue climbing means you had
   two problems.

5. Announce in `#incident`: the two image tags, the revision number, and whether the
   database migration state is compatible.

## Migrations are the trap

A rollback does **not** revert database migrations. If the bad deploy ran a migration,
check that the previous build tolerates the new schema before step 3. Checkout migrations
are required to be forward- and backward-compatible for one release, which gives you
exactly one revision of rollback headroom — not two.

## Canary

The rollout stops at 5% for 4 minutes. If the canary error ratio exceeds 1%, the rollout
aborts on its own and no manual rollback is needed. Confirm this happened before running
the steps above; undoing an already-aborted rollout takes you back one revision too far.
