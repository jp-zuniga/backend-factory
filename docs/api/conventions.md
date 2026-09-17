---
icon: lucide/sliders-horizontal
---

# Conventions

Rules that hold for every endpoint in this API, so the flow-by-flow pages
that follow don't have to repeat them.

## Status codes

| Verb     | Success                 | Notes                                                                                             |
| -------- | ----------------------- | ------------------------------------------------------------------------------------------------- |
| `GET`    | `200`                   |                                                                                                   |
| `POST`   | `200`/`201`/`202`/`204` | Varies by endpoint — a challenge response uses `202`, a pure action (confirm, disable) uses `204` |
| `PUT`    | `200`                   | Full replace                                                                                      |
| `PATCH`  | `200`                   | Partial update                                                                                    |
| `DELETE` | `204`                   |                                                                                                   |

Calling a method a controller doesn't expose answers `405`, with an `Allow`
header listing what the controller _does_ accept.

## Pagination

List endpoints (`GET` on a collection, e.g. `/auth/user/`) return a paginated
envelope:

```json
{
  "next": true,
  "previous": false,
  "elements": 134,
  "pages": 7,
  "current": 1,
  "results": [
    /* … */
  ]
}
```

`next`/`previous` are booleans (whether another page exists in that
direction), not links. Two query parameters control paging on every list
endpoint:

| Param       | Default | Notes           |
| ----------- | ------- | --------------- |
| `page`      | `1`     |                 |
| `page_size` | `20`    | Capped at `100` |

Every list-shaped resource also ships an **unpaginated** twin at `.../all/`
(for example `/auth/user/all/`) that returns a bare JSON array with no
envelope and no `page`/`page_size` parameters — meant for populating a
dropdown or a select, not for browsing a large table. The `all` variant
typically returns a smaller "inline" shape of the resource rather than the
full detail shape.

## Filtering, searching, ordering

The same query string vocabulary applies wherever a resource declares it:
a `search` parameter does a case-insensitive, accent-insensitive substring
match across a handful of fields; individual field filters (`is_active`,
`email`, `group_id`, …) do exact or lowered matches; and `order` picks the
sort column, e.g. `?order=email` or `?order=-email` for descending. Which
fields are filterable/searchable/orderable is per-resource — see the flow
pages, or the OpenAPI document, for the exact set on a given endpoint.

## `PUT` versus `PATCH`

- **`PUT`** is a full replace: it uses the same schema as creating the
  resource, so every writable field is required. Omit one and the request
  fails validation with `400`.
- **`PATCH`** is a partial update: every field is optional, and an omitted
  field is left untouched on the row. Sending a field explicitly (even
  `null`, where the field allows it) does update it.

Both return the full resource on success, same as a `GET`.

## Sub-resource urls

Some resources hang off a parent, e.g. a user's groups at
`/auth/user/{id}/groups/`. A `404` on a sub-resource url usually means the
_parent_ wasn't found (or doesn't belong to you) rather than the child —
sub-resource lookups are scoped to their parent, so a real child row that
belongs to a different parent still reads as "not found," not "forbidden."

## Rate limits

Public, unauthenticated endpoints (login, register, refresh, and the rest of
the auth surface) are throttled per client address. A throttled request gets
`429 Too Many Requests` with:

| Header                  | Meaning                             |
| ----------------------- | ----------------------------------- |
| `Retry-After`           | Seconds until the limit resets      |
| `X-RateLimit-Limit`     | The limit's ceiling                 |
| `X-RateLimit-Remaining` | Requests left in the current window |
| `X-RateLimit-Reset`     | When the window resets              |

See [API → Errors](errors.md#status-codes) for the response body shape.

## Ids and timestamps

- Primary keys are either a UUID string or a positive integer, depending on
  the resource (check the concrete path in the flow pages — e.g. users are
  UUIDs, groups and permissions are integers, matching Django's built-in
  auth tables).
- Timestamps (`created_at`, `email_verified_at`, `confirmed_at`, …) are ISO
  8601 datetime strings.
