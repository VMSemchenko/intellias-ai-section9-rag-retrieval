---
id: pm-2026-06-ledger-drift
title: "Postmortem 2026-06-08: six days of undetected settlement drift"
doc_type: postmortem
service: ledger-svc
version: v2
status: active
visibility: everyone
updated_at: 2026-06-12
---

# Postmortem 2026-06-08: six days of undetected settlement drift

**Duration:** 6 days.
**Impact:** €41,280 of provider corrections unrecorded across 1,904 transactions. No
customer-visible error; the discrepancy was internal until the monthly close.

## Timeline

- **Jun 2** The payment provider begins sending settlement corrections in a new field
  (`adjustment_minor`) alongside the existing `settled_minor`. This was announced in a
  changelog we do not subscribe to.
- **Jun 2 – Jun 8** The hourly settlement match job compares `settled_minor` only. It sees
  matching amounts and reports no drift. The corrections are silently ignored.
- **Jun 8, 09:30** Monthly close preparation surfaces a €41k gap.
- **Jun 8, 11:00** New provider field identified as the cause.
- **Jun 8, 16:40** Backfill of 1,904 correcting transactions completed and verified.

## Root cause

The reconciliation job checked one field for equality. A provider change that added
information — rather than changing existing information — was invisible to it, because the
job had no notion of "the payload contains something I do not understand".

The job was working exactly as written. Its assumption, that the settlement payload's shape
is stable, was never stated anywhere and therefore never reviewed.

## Contributing factors

- Nobody subscribed to the provider's changelog. There was no owner for that.
- The internal invariant check passed the whole time, correctly — our own books balanced.
  Internal consistency and external agreement are different properties and only one of them
  was being checked frequently.

## What we changed

- The settlement job rejects payloads containing unrecognised fields rather than ignoring
  them. An unknown field is now a flagged discrepancy.
- Provider changelog subscription is an explicit Money team responsibility, recorded in the
  service ownership policy.
- ADR-0067 gained the 26-hour overlapping window so a single missed run cannot hide a
  discrepancy.
- The backfill was posted as 1,904 correcting transactions, not as edits. The gap and its
  correction are both on the statement, per ADR-0044.

## Lesson

A reconciliation that only compares the fields you thought of will confirm agreement that
does not exist. Treat an unknown field as a mismatch.
