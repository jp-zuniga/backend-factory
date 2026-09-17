---
icon: lucide/circle-alert
---

# Errors

Every error this API returns — a bad body, a permission failure, a database
constraint refusing a write — ends up as the same shape:
`{"detail": str, "field_errors": {str: str} | null}`. `api_exceptions` is the
one place that owns both halves of that: the hierarchy of typed errors, and
the single handler that turns _any_ exception into one of them.

## `ApiError` and its subtypes

`ApiError` (`api_exceptions/errors/base.py`) is a plain `Exception` carrying
`detail`, `field_errors` and `http_status`, defaulting to `500`:

```python
class ApiError(Exception):
    default_detail: str = "Ha ocurrido un error inesperado."
    default_http_status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR
```

| Error                     | Status                       | Raised for                                 |
| ------------------------- | ---------------------------- | ------------------------------------------ |
| `BadRequestError`         | `400`                        | body/query/path/header validation failures |
| `UnauthorizedError`       | `401`                        | missing or rejected credentials            |
| `ForbiddenError`          | `403`                        | authenticated, but lacking the permission  |
| `NotFoundError`           | `404`                        | a lookup that matched no row               |
| `ConflictError`           | `409`                        | a constraint or trigger refusing a write   |
| `UnacceptableHeaderError` | `406`                        | an `Accept` header this API can't satisfy  |
| `UnsupportedMediaError`   | `415` (or remapped to `400`) | a body this API can't parse                |
| `ContentTooLargeError`    | `413`                        | a body/field/file count over the limit     |
| `ThrottleExceededError`   | `429`                        | a throttle tripped                         |

`BadRequestError`, `ConflictError`, `ContentTooLargeError` and
`UnsupportedMediaError` are `TypedApiError[T]` subclasses — each pairs with a
`StrEnum` of specific reasons (`ConflictErrorTypes.UNIQUE`,
`BadRequestErrorTypes.MISSING_FIELDS`, ...) declared in `api_exceptions.enums`.
When a `type=` is passed and no explicit `detail`, the enum's own value
_is_ the detail message — the enum exists so the space of possible messages
for a given status code is closed and grep-able, not just free text.

## Request scopes

`RequestScopes` (`BODY`, `COOKIES`, `FILES`, `HEADERS`, `PATH`, `QUERY`) names
which part of the request a field error points at. `ApiError.scoped(*crumbs)`
prefixes every key in `field_errors` with a dotted path built from those
crumbs, e.g. turning `{"email": "..."}` into `{"query.email": "..."}`.
`StrictQueryComponent` (see [Request lifecycle](request-lifecycle.md#parsing-and-validation))
uses this directly when it rejects a repeated query parameter:

```python
raise BadRequestError(
    field_errors=repeated,
    type=BadRequestErrorTypes.FAILED_VALIDATION,
).scoped(RequestScopes.QUERY)
```

`BadRequestError.from_validation_error` does the same thing structurally: it
maps a pydantic/`dmr` error's `loc` tuple — whose first element is the
internal parameter name (`parsed_body`, `parsed_query`, ...) — onto the
matching `RequestScopes` member via `DMR_SCOPE_MAPPER`, so a client always
sees `body.email` or `query.page`, never `parsed_body.email`.

## Mapping database and validation failures

`BadRequestError.from_validation_error` and `ConflictError.from_integrity_error`
are the two adapters that turn a lower-level exception into a typed `ApiError`:

- **Validation** — `pydantic.ValidationError` and `dmr.errors.ValidationError`
  both expose a list of per-field errors; each is translated through
  `PYDANTIC_TYPE_MAPPER` into a Spanish message (falling back to the raw
  input value or the library's own message if the error type isn't mapped).
  A bare Django `ValidationError` has no such structure, so it collapses to a
  single `FAILED_VALIDATION` detail with no field errors.
- **Conflicts** — `ConflictError.from_integrity_error` first checks for
  `RestrictedError`/`ProtectedError` (Django's own guard against deleting a
  `PROTECT`ed relation), then walks the exception's `__cause__`/`__context__`
  chain (`traverse_traceback`) looking for the underlying `psycopg.errors.IntegrityError`,
  and pattern-matches its concrete type
  (`ForeignKeyViolation`, `NotNullViolation`, `RestrictViolation`,
  `UniqueViolation`) onto a `ConflictErrorTypes` member. For foreign-key and
  uniqueness violations, it also parses the offending column name straight
  out of PostgreSQL's own error detail message (`(column)=(value)`) with a
  regex, so the response names the actual field — no manual mapping needed
  per constraint.

## What the handler does with the rest

`api_exceptions.handler.exc_handler` is registered once, globally, as
`Settings.global_error_handler` (`api_core/settings.py`) — see
[Request lifecycle](request-lifecycle.md#where-errors-become-payloads). It is
the _only_ function that knows how to turn a raw exception into an
`ApiErrorResponse`:

```python
if isinstance(exc, ApiError):
    parsed = exc
elif isinstance(exc, NotAcceptableError):
    parsed = UnacceptableHeaderError()
elif isinstance(exc, NotAuthenticatedError):
    add_www_authenticate(exc, endpoint.metadata.auth)
    parsed = UnauthorizedError()
elif oversized := ContentTooLargeError.unwrap(exc):
    parsed = oversized
elif isinstance(exc, RequestSerializationError):
    parsed = UnsupportedMediaError.from_serialization_error(controller, exc)
elif isinstance(exc, TooManyRequestsError):
    parsed = ThrottleExceededError()
elif isinstance(exc, GenericConflictError):
    parsed = ConflictError.from_integrity_error(exc)
elif isinstance(exc, GenericValidationError):
    parsed = BadRequestError.from_validation_error(exc)
```

If none of those `isinstance` checks match, `exc_handler` **re-raises the
original exception**. Nothing further down the chain the raise reaches (see
[Request lifecycle](request-lifecycle.md)) knows how to make a response out
of it, so it becomes an unhandled `500` with a real traceback — deliberately:
an exception this handler doesn't recognize is a bug, and should look like
one in the logs, not get silently flattened into a generic error body.

## Adding a new error type

Because `exc_handler` matches on Python types, adding an error that maps to
an _existing_ condition (say, another kind of `psycopg` violation) means
teaching the relevant `from_*` classmethod a new branch — the handler itself
never changes. Adding an entirely new failure mode means:

1. A new `ApiError` subclass (or `TypedApiError[SomeEnum]`, if it needs more
   than one specific reason) with its `default_detail` and `default_http_status`.
2. One `isinstance`/matching branch in `exc_handler`, if it wraps a third-party
   exception rather than being raised directly by your own code — code that
   raises the new `ApiError` itself needs no handler change at all, since the
   first branch (`isinstance(exc, ApiError)`) already covers it.
3. A `ResponseSpec` added to `api_exceptions.specs.ERROR_SPECS`, so the new
   status code is documented on every endpoint (see
   [OpenAPI](openapi.md#response-specs)).
