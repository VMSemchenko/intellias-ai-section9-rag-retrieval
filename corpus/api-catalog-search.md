---
id: api-catalog-search
title: "API reference: catalog-svc search"
doc_type: api
service: catalog-svc
version: v2
status: active
visibility: everyone
updated_at: 2026-05-06
---

# API reference: catalog-svc search

Base path `/v2/search`. Requires scope `catalog:read`.

## GET /v2/search

| Parameter | Default | Note |
|---|---|---|
| `q` | required | free text, max 200 chars |
| `filter` | — | repeatable, `field:value` |
| `sort` | `relevance` | or `price_asc`, `price_desc`, `newest` |
| `page_size` | 24 | max 100 |
| `cursor` | — | opaque; do not construct one |

Response `200` (v2 envelope):

    { "results": [ { "sku": "...", "title": "...", "price_minor": 4599,
                     "currency": "EUR", "score": 8.41 } ],
      "total_estimate": 1840,
      "next_cursor": "eyJ...",
      "index_lag_seconds": 4 }

`total_estimate` is an estimate above 1,000 results. Do not render it as an exact count.

`index_lag_seconds` reports how far behind the index is. Under ADR-0022 the incremental
target is 30 seconds; a value materially above that means the incremental consumer is
struggling and results are stale.

## The v1 envelope is superseded

v1 returned a bare array with a `X-Total-Count` header and no lag field. It is deprecated
with one remaining consumer; see the deprecation register. New clients must use v2.

## Do not use search for product detail

Search results are asynchronous and can be stale. Read a single product through
`GET /v2/products/{sku}`, which goes via the read-through cache in ADR-0071 and honours
read-your-writes.

## Pagination beyond 10,000

Cursor pagination stops at 10,000 results. Beyond that, narrow the query with filters.
There is no deep-paging escape hatch and asking for one will be refused — deep paging over
a distributed index is the operation most likely to take the cluster down.
