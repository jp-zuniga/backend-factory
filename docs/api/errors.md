---
icon: lucide/circle-alert
---

# Errors

The internal error hierarchy and the handler that renders it live under
[Concepts → Errors](../concepts/errors.md). This page is the client-facing
view: what a failure actually looks like on the wire.

## Response shape

Every error response, regardless of status code, is the same shape:

```json
{
  "detail": "Human-readable summary of what went wrong.",
  "field_errors": {
    "body.username": "Este campo es requerido."
  }
}
```

- **`detail`** — always present. A short, human-readable message. For
  several error types it doubles as a machine-checkable classification
  (e.g. `"Uno o más campos no se pudieron validar."` for a failed
  validation) — treat it as informational text, not as a stable enum, unless
  a specific endpoint's docs say otherwise.
- **`field_errors`** — present only when the failure can be pinned to
  specific fields; `null`/absent otherwise. Keys are dotted paths that name
  *which part of the request* the field lives in, then the field itself.

## Where a field error points

| Prefix | Part of the request |
| --- | --- |
| `body.*` | JSON request body |
| `query.*` | Query string |
| `path.*` | URL path parameters |
| `cookies.*` | Cookies |
| `headers.*` | Request headers |
| `files.*` | Uploaded files |

So `"body.username": "Este campo es requerido."` means the `username` field
of the JSON body was missing; `"cookies.csrftoken": "..."` means the problem
was with a cookie, not the body, even though both can appear on the same
request.

## Status codes

| Status | When | Retry? |
| --- | --- | --- |
| `400` Bad Request | Body/query/path failed validation | Yes, after fixing the request |
| `401` Unauthorized | Missing, invalid, expired, or revoked credentials | Only after re-authenticating |
| `403` Forbidden | Authenticated, but not permitted; or CSRF failed; or email unconfirmed | No, unless the underlying condition changes |
| `404` Not Found | No matching row (or a foreign key pointed at one that doesn't exist) | No |
| `405` Method Not Allowed | The controller doesn't expose that verb | No |
| `406` Not Acceptable | Invalid `Accept` header | Yes, with a valid header |
| `409` Conflict | Uniqueness/foreign-key/check constraint, or a locked row | Depends — a duplicate needs different data, a lock may resolve on retry |
| `413` Content Too Large | Body/fields/files exceed limits | No, unless the request shrinks |
| `415` Unsupported Media Type | Body couldn't be parsed at all (bad encoding, wrong content type) | Yes, with a fixed request |
| `429` Too Many Requests | Rate limit exceeded | Yes, after `Retry-After` seconds |
| `500` Internal Server Error | Unhandled failure | Not meaningfully — treat as a bug to report |

## Worked examples

=== "Failed validation (400)"

    ```json
    {
      "detail": "La solicitud contiene datos inválidos.",
      "field_errors": {
        "body.password1": "Este campo debe tener un mínimo de 8 caracter(es).",
        "body.email": "'not-an-email' no es un valor válido."
      }
    }
    ```

=== "Conflict (409)"

    ```json
    {
      "detail": "Hay un conflicto con el estado actual del recurso.",
      "field_errors": {
        "username": "Ya existe un registro con el valor proporcionado."
      }
    }
    ```

    A duplicate-key or foreign-key violation from the database is translated
    into this shape automatically — see
    [Concepts → Operations](../concepts/operations.md) for how.

=== "Forbidden (403)"

    ```json
    {
      "detail": "No tiene permiso para realizar esta acción."
    }
    ```

    No `field_errors` — the request was well-formed, the caller just isn't
    allowed to make it.

=== "Throttled (429)"

    ```http
    HTTP/1.1 429 Too Many Requests
    Retry-After: 42
    X-RateLimit-Limit: 10
    X-RateLimit-Remaining: 0
    X-RateLimit-Reset: 1758000000
    ```

    ```json
    {
      "detail": "Ha superado el límite de uso establecido para este recurso."
    }
    ```

    See [Conventions → Rate limits](conventions.md#rate-limits) for what the
    headers mean.
