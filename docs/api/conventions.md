---
icon: lucide/sliders-horizontal
---

# Conventions

## Pagination

List endpoints (`GET` on a collection, e.g. `/auth/user/`) return a
paginated envelope:

```json
{
  "next": true,
  "previous": false,
  "elements": 134,
  "pages": 7,
  "current": 1,
  "results": [
    /* ... */
  ]
}
```

`next` and `previous` are booleans, whether another page exists in that
direction, not links. Two query parameters control paging on every list
endpoint: `page`, defaulting to `1`, and `page_size`, defaulting to `20`
and capped at `100`.

Every list-shaped resource also ships an unpaginated twin at `.../all/`
(for example `/auth/user/all/`) that returns a bare JSON array with no
envelope and no `page`/`page_size` parameters, meant for populating a
dropdown or a select, not for browsing a large table. The `all` variant
typically returns a smaller inline shape of the resource rather than the
full detail shape.

## Filtering, searching, ordering

The same query string vocabulary applies wherever a resource declares it.
A `search` parameter does a case-insensitive, accent-insensitive
substring match across a handful of fields; individual field filters
(`is_active`, `email`, `group_id`, and others) do exact or lowered
matches; and `order` picks the sort column, for example `?order=email` or
`?order=-email` for descending. Which fields are filterable, searchable,
or orderable is per-resource; see the flow pages, or the OpenAPI
document, for the exact set on a given endpoint.

## `PUT` versus `PATCH`

`PUT` is a full replace: it uses the same schema as creating the resource,
so every writable field is required, and omitting one fails validation
with `400`. `PATCH` is a partial update: every field is optional, an
omitted field is left untouched on the row, and sending a field
explicitly, even `null` where the field allows it, does update it. Both
return the full resource on success, the same as a `GET`.

## Sub-resource urls

Some resources hang off a parent, for example a user's groups at
`/auth/user/{id}/groups/`. A `404` on a sub-resource url usually means the
parent wasn't found, or doesn't belong to the caller, rather than the
child, since sub-resource lookups are scoped to their parent: a real child
row that belongs to a different parent still reads as not found, not
forbidden.

## Rate limits

Public, unauthenticated endpoints (login, register, refresh, and the rest
of the auth surface) are throttled per client address. A throttled
request gets `429 Too Many Requests`, with `Retry-After` naming the
seconds until the limit resets, `X-RateLimit-Limit` the limit's ceiling,
`X-RateLimit-Remaining` the requests left in the current window, and
`X-RateLimit-Reset` when the window resets. See
[Errors](errors.md#status-codes) for the response body shape.
