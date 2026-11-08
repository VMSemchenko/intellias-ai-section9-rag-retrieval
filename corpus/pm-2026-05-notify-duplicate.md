---
id: pm-2026-05-notify-duplicate
title: "Postmortem 2026-05-19: duplicate order notifications sent to partners"
doc_type: postmortem
service: notify-svc
version: v3
status: active
visibility: everyone
updated_at: 2026-05-21
---

# Postmortem 2026-05-19: duplicate order notifications sent to partners

**Impact:** 11,400 duplicate webhook deliveries to 3 partners over 40 minutes. One partner
created 380 duplicate fulfilment records.

## Timeline

- **11:05** A `notify-svc` deploy rolls out a change to the delivery worker's
  acknowledgement path.
- **11:07** Deliveries begin succeeding at the destination but failing to record the
  acknowledgement locally, because the new code wrote the ack after committing the
  outbound span rather than before.
- **11:08** The retry scheduler sees unacknowledged events and re-attempts them. Every
  event is now delivered on every pass of the schedule.
- **11:31** Partner reports duplicate fulfilment records.
- **11:44** Rollback completes. Duplicate deliveries stop.
- **12:10** Partner reconciliation script run jointly with the partner.

## Root cause

The acknowledgement write moved to after a network call that could fail independently. A
successful delivery with a failed ack is indistinguishable, to the scheduler, from a
failed delivery. Under an at-least-once guarantee the scheduler did exactly what it is
designed to do.

The amplifying factor is that the affected partner was not deduplicating on `X-Event-Id`,
despite it being documented as the deduplication key. ADR-0038 is explicit that consumers
will see duplicates; this partner's integration predates that document.

## What we changed

- The ack write happens before any non-essential work in the delivery path, and is the
  only thing that can mark an event delivered.
- Added `notify_delivered_without_ack_total`. A non-zero value is now an alert, not a
  curiosity.
- Partner integration checklist now requires demonstrating `X-Event-Id` deduplication
  before a subscription is activated.

## What we did not change

We did not move to exactly-once delivery. It is not available over an unreliable network,
and pretending otherwise would move the duplicate handling somewhere less visible.

## Lesson

Under at-least-once, the acknowledgement is the most safety-critical write in the system.
Treat reordering it as a change to the delivery guarantee itself.
