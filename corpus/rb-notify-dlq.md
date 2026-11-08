---
id: rb-notify-dlq
title: "Runbook: draining the notify-svc dead-letter queue"
doc_type: runbook
service: notify-svc
version: v3
status: active
visibility: everyone
updated_at: 2026-05-27
---

# Runbook: draining the notify-svc dead-letter queue

**Page trigger:** `notify_dlq_depth > 500` or any single subscription contributing more
than 200 messages.

## Understand before you replay

Messages reach the dead-letter queue only after the full asynchronous retry schedule from
ADR-0055 has been exhausted — eight attempts spread across 24 hours. A growing queue
therefore means a destination has been unavailable for at least a day, or is rejecting our
payloads outright.

Group by subscription before doing anything:

    notify-cli dlq stats --group-by subscription --since 48h

One subscription dominating means a partner problem. Spread evenly across subscriptions
means the problem is ours — check the signing key and the payload schema version first.

## Replay

1. Verify the destination is actually healthy now. Replaying into a still-broken endpoint
   burns the retry budget again and refills the queue.

       notify-cli probe --subscription <id>

2. Replay in bounded batches. The per-destination concurrency cap of 4 in flight still
   applies, so a large replay takes time by design — do not raise the cap to speed it up.

       notify-cli dlq replay --subscription <id> --limit 200 --dry-run
       notify-cli dlq replay --subscription <id> --limit 200

3. Watch `notify_delivery_success_total` for that subscription. If failures resume,
   stop the replay rather than draining the whole queue into a broken endpoint.

4. Clear the degraded flag once a batch succeeds:

       notify-cli subscription undegrade <id>

## Discarding

Messages older than the retention window in the data retention policy may be discarded
with owner approval. Record the count and the subscription in the incident channel.
Discarding is irreversible and consumers have no way to detect the gap.

## Duplicates

Replay can deliver an event the consumer already processed — see the duplicate
notification postmortem. This is expected under at-least-once delivery. Tell the partner
before a large replay; do not attempt to deduplicate on our side.
