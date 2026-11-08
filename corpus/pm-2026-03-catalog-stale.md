---
id: pm-2026-03-catalog-stale
title: "Postmortem 2026-03-11: catalog search served 6-day-old results"
doc_type: postmortem
service: catalog-svc
version: v1
status: active
visibility: everyone
updated_at: 2026-03-13
---

# Postmortem 2026-03-11: catalog search served 6-day-old results

**Duration:** 6 days undetected.
**Impact:** Search results, including price and availability, were up to six days stale.
Discontinued products remained findable and purchasable.

## Timeline

- **Mar 5, 02:14** The incremental index consumer crashes on a malformed change event
  (a product whose description contained a lone surrogate). The pod restarts, hits the same
  event, crashes again. It enters a crash loop and stops making progress.
- **Mar 5, 03:00** The hourly drift detector fires. Its alert routes to a Slack channel
  that was archived during a team reorganisation in January. Nobody sees it. It fires every
  hour for six days.
- **Mar 11, 09:40** A merchandiser reports that a discontinued product is still in search.
- **Mar 11, 10:05** Consumer crash loop found. Poison event skipped manually.
- **Mar 11, 10:20** Full reindex started per the reindex runbook.
- **Mar 11, 11:02** Alias swapped. Results current.

## Root cause

Two independent failures, neither sufficient alone:

1. The consumer had no poison-message handling. A single unparseable event could block the
   queue indefinitely. It had no dead-letter path.
2. The only detector that noticed was routed to an archived channel. The drift detector
   worked perfectly for six days and told nobody.

## Contributing factor

`index_lag_seconds` existed in the v2 search response but the customer-facing UI used the
v1 envelope, which has no lag field. The staleness was measurable and visible in the API,
and invisible in the product.

## What we changed

- Poison events go to a dead-letter topic after three failed parses. The consumer continues.
- Drift alerts page the on-call rotation instead of posting to a channel. Alert routing is
  validated by a synthetic alert every week.
- Added `catalog_index_lag_seconds` as a paging alert above 300 seconds.
- The UI moved to the v2 envelope and surfaces a "results may be delayed" banner above
  60 seconds of lag.

## Lesson

An alert nobody receives is worse than no alert, because it creates the belief that the
failure mode is covered. Alert routing needs its own test.
