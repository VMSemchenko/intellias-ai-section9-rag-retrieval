---
id: api-checkout-orders
title: "API reference: checkout-svc orders"
doc_type: api
service: checkout-svc
version: v4
status: active
visibility: everyone
updated_at: 2026-07-15
---

# API reference: checkout-svc orders

Base path `/v4/orders`. Requires a v4 Bearer access token with scope `orders:write`.

## POST /v4/orders

Headers:

| Header | Required | Note |
|---|---|---|
| `Authorization` | yes | `Bearer <access token>` |
| `Idempotency-Key` | yes | see ADR-0048 — a missing key is a `400` |
| `Content-Type` | yes | `application/json` |

Request:

    { "cart_id": "c_01H...", "payment_method_id": "pm_01H...",
      "shipping_address_id": "a_01H...", "currency": "EUR" }

Response `201`:

    { "order_id": "o_01H...", "status": "submitted",
      "total_minor": 4599, "currency": "EUR",
      "ledger_entry_id": "le_01H..." }

| Status | Meaning | Client action |
|---|---|---|
| `400` | missing or malformed `Idempotency-Key` | fix the client |
| `401` | expired or invalid access token | exchange a new token, retry once |
| `409` | same idempotency key still in flight | wait `Retry-After`, retry |
| `422` | idempotency key reused with a different payload | fix the client |
| `502` | edge could not get a usable response from checkout | see the checkout 502 runbook |
| `503` | checkout shedding load | retry per the ADR-0055 synchronous budget |

## GET /v4/orders/{order_id}

Returns the order with its current status. Statuses: `submitted`, `authorised`,
`captured`, `failed`, `cancelled`. Poll no faster than once per second.

## POST /v4/orders/{order_id}/cancel

Cancellable only while `submitted` or `authorised`. A `captured` order requires a refund
through the ledger, not a cancellation.
