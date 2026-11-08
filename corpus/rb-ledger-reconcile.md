---
id: rb-ledger-reconcile
title: "Runbook: manual ledger reconciliation"
doc_type: runbook
service: ledger-svc
version: v2
status: active
visibility: everyone
updated_at: 2026-06-26
---

# Runbook: manual ledger reconciliation

**Page trigger:** `ledger_invariant_failures_total > 0`, or a settlement mismatch flagged
by the hourly job that is still open after 4 hours.

Two people. One drives, one reviews every command before it runs. This is not ceremony —
the June 2026 drift incident was made worse by a single operator running a correction
against the wrong date range.

## Step 1: classify the discrepancy

    ledger-cli recon show --since 26h --status open

| Class | Meaning | Action |
|---|---|---|
| Timing | we recorded a capture the provider has not settled yet | wait one more cycle, do nothing |
| Provider correction | the provider changed a settled amount | post a correcting transaction |
| Missing entry | we have no transaction for a provider movement | investigate upstream first |
| Imbalance | a transaction's debits do not equal its credits | **stop** — this should be impossible |

An imbalance means the deferred constraint from ADR-0044 was bypassed, which means someone
wrote to the database directly. Escalate to the Money tech lead and the platform on-call
before touching anything.

## Step 2: never edit, always oppose

Entries are append-only and the application role has no `UPDATE` or `DELETE` grant. A
correction is a new transaction with opposing entries and `kind = 'correction'`:

    ledger-cli correct --transaction <id> --reason "<provider ref>" --dry-run
    ledger-cli correct --transaction <id> --reason "<provider ref>"

Both the original and the correction appear on the statement. That is intended.

## Step 3: closed days

A day closed by the 03:15 UTC job is frozen. A correction against a closed day requires:

1. Finance controller approval, recorded in the ticket.
2. `ledger-cli day unfreeze --date <YYYY-MM-DD> --ticket <id>`.
3. The correction.
4. `ledger-cli day close --date <YYYY-MM-DD>` — re-runs the close and re-verifies.

Never leave a day unfrozen at the end of a shift.

## Step 4: verify

    ledger-cli verify --date <YYYY-MM-DD>

Must report zero imbalances and a settlement delta within the provider's stated tolerance.
Re-run the hourly job manually rather than waiting for :20.
