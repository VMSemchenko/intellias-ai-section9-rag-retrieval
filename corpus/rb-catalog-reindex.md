---
id: rb-catalog-reindex
title: "Runbook: full catalog search reindex"
doc_type: runbook
service: catalog-svc
version: v1
status: active
visibility: everyone
updated_at: 2026-04-03
---

# Runbook: full catalog search reindex

Run this when the mapping changes, when drift exceeds 0.1%, or when the incremental
consumer has been stopped long enough to have lost change events.

Expect 40 minutes. It saturates the read replica — do not run it during a sale.

## Procedure

1. Announce in `#team-discovery`. A reindex during a mapping migration is a planned change,
   not an operational one.

2. Create the target index with the current mapping:

       catalog-cli index create --name products-$(date +%Y%m%d%H%M)

3. Start the backfill from the read replica. Never from the primary:

       catalog-cli reindex start --target <index> --source replica --concurrency 8

   Concurrency above 8 does not go faster; it just makes the replica lag.

4. **Leave the incremental consumer running.** It writes to both the live alias and any
   index currently being built. Stopping it means every change made during the 40 minutes
   is lost and you will need a second reindex.

5. Watch progress and replica lag together:

       catalog-cli reindex status --target <index>

   Abort if replica lag exceeds 60 seconds — something else is reading heavily.

6. Verify before swapping. Compare document counts and run the smoke query set:

       catalog-cli index verify --target <index> --against live

   A count difference under 0.05% is acceptable and reflects writes in flight.

7. Swap the alias atomically:

       catalog-cli alias move --alias products --to <index>

8. Keep the previous index for 24 hours. Rollback is another `alias move`.

## Rollback

Move the alias back. There is no state to unwind; the old index has been receiving
incremental updates the whole time, which is the reason for step 4.
