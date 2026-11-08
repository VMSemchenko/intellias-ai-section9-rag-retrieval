---
id: api-notify-webhooks
title: "API reference: notify-svc webhook subscriptions and delivery headers"
doc_type: api
service: notify-svc
version: v3
status: active
visibility: everyone
updated_at: 2026-06-22
---

# API reference: notify-svc webhook subscriptions and delivery headers

## POST /v3/subscriptions

    { "url": "https://partner.example.com/hooks",
      "events": ["order.submitted", "order.captured"],
      "secret": "whsec_..." }

Response `201` returns the subscription id. The URL must be HTTPS and must respond to a
probe request within 3 seconds before the subscription is activated.

## Headers we send on every delivery

| Header | Example | Meaning |
|---|---|---|
| `X-Event-Id` | `evt_01H...` | stable across retries — deduplicate on this |
| `X-Event-Type` | `order.captured` | |
| `X-Sequence` | `1184` | per-subscription ordering; use instead of arrival order |
| `X-Attempt` | `3` | 1-based attempt counter |
| `X-Signature` | `v1=<hex>` | HMAC-SHA256 over the raw body with the subscription secret |
| `X-Timestamp` | `1756230000` | reject deliveries older than 5 minutes |

Verify the signature over the **raw** bytes before parsing JSON. Re-serialising the body
changes the bytes and the signature will not match.

## What we expect back

Any `2xx` within 5 seconds is success. Anything else is a failed attempt and enters the
retry schedule defined in ADR-0055 — `notify-svc` does not define its own retry counts or
intervals, so do not look for them here.

A `410 Gone` is treated as terminal on the first occurrence: the subscription is disabled
immediately with no further attempts. Use it deliberately when a destination is retired.

## GET /v3/subscriptions/{id}/deliveries

Recent attempts with status and response code. Retained for 7 days. Attempts beyond the
retention window are only visible in the dead-letter queue, if they got that far.
