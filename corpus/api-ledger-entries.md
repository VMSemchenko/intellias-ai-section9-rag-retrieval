---
id: api-ledger-entries
title: "API reference: ledger-svc transactions and entries"
doc_type: api
service: ledger-svc
version: v2
status: active
visibility: everyone
updated_at: 2026-04-30
---

# API reference: ledger-svc transactions and entries

Internal only. Not exposed at the edge. Requires scope `ledger:write` or `ledger:read`.

## POST /v2/transactions

Creates a transaction and its entries atomically. Rejected unless the entries balance per
currency.

    { "kind": "order_capture",
      "external_ref": "o_01H...",
      "idempotency_key": "01H...",
      "occurred_at": "2026-08-26T12:00:00Z",
      "entries": [
        { "account_id": "acc_customer_01H", "direction": "debit",  "amount_minor": 4599, "currency": "EUR" },
        { "account_id": "acc_revenue_eu",   "direction": "credit", "amount_minor": 4599, "currency": "EUR" }
      ] }

| Status | Meaning |
|---|---|
| `201` | created |
| `200` | idempotent replay — same `idempotency_key`, same fingerprint, returns the original |
| `409` | same `idempotency_key`, different entries |
| `422` | entries do not balance, or `amount_minor` is not a positive integer |

There is no `PATCH` and no `DELETE`. This is not an omission — entries are append-only per
ADR-0044. Corrections are new transactions with `kind: "correction"` and a
`corrects_transaction_id`.

## GET /v2/accounts/{account_id}/balance

    { "account_id": "acc_...", "balance_minor": -12045, "currency": "EUR",
      "as_of": "2026-08-26T12:04:11Z", "snapshot_id": "snap_..." }

The balance is derived from entries, not stored. `as_of` is the moment it was computed;
concurrent writes may have landed since. For anything a customer will see, quote `as_of`.

## GET /v2/transactions?external_ref=...

Look up by upstream reference — how checkout finds the ledger entry for an order.
