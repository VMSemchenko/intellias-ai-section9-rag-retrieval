---
id: policy-data-retention
title: "Policy: data retention windows"
doc_type: policy
service: platform
status: active
visibility: everyone
updated_at: 2026-08-05
---

# Policy: data retention windows

Deletion is automated. A dataset with no entry in this table has no automated deletion and
is therefore a compliance gap — report it rather than assuming it is intentional.

| Dataset | Retention | Then |
|---|---|---|
| Edge access logs | 30 days | deleted |
| Application logs | 14 days | deleted |
| Webhook delivery attempt records | 7 days | deleted |
| Dead-letter queue messages | 30 days | deleted, count recorded |
| Idempotency key records | 24 hours | deleted |
| Session records (v3) | 12 h sliding | deleted on expiry |
| Refresh tokens (v4) | 90 days idle | revoked and deleted |
| Ledger transactions and entries | 10 years | archived to cold storage, never deleted |
| Order records | 7 years | archived |
| Customer PII on account deletion | 30 days | hard-deleted, ledger references pseudonymised |
| Heap dumps and profiles | 7 days | deleted |

## The ledger is the exception

Ledger entries are never deleted, because a financial record that can be deleted is not a
financial record. Account deletion pseudonymises the customer reference on the entry and
leaves the amounts intact.

## Dead-letter queue interaction

A dead-lettered webhook is deleted 30 days after it was dead-lettered, which is 31 days
after the original event. The notify dead-letter runbook allows discarding earlier with
owner approval. Nothing in either direction extends the window.

## Backups

Backups follow the retention of the dataset they contain, with one exception: a backup taken
before a hard deletion is purged within 35 days so a deletion request cannot be defeated by
restoring an old snapshot.

## Requesting an extension

Extensions require a documented legal or contractual basis and are recorded here. There are
currently none.
