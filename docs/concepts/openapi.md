---
icon: lucide/scroll-text
---

# OpenAPI

Nothing under `docs/api/` describes the wire format by hand for long — the
authoritative contract is generated from the same controllers and schemas
that serve the requests, so it can't drift from what the API actually does.

## Where it's built and served

`api_core.api` builds the document once, at import time:

```python
router: Final[Router] = Router(prefix="")
router.include(api_auth.api.router)
schema: Final[OpenAPI] = build_schema(router)
```

`api_core.urls` serves it at `/openapi/` through `dmr`'s `OpenAPIJsonView`:

```python
path(
    name="openapi-schema",
    route="openapi/",
    view=OpenAPIJsonView.as_view(
        schema=schema,
        skip_validation=(not CONFIG.DEBUG),
    ),
)
```

`skip_validation` is tied to `CONFIG.DEBUG`: in development the document is
validated against the OpenAPI meta-schema on every request (so a mistake
surfaces immediately), and in a deployment that check is skipped for
latency — the document was already validated during development.

## Operation ids

`BaseController.endpoint_cls = PathOperationIdEndpoint`
(`api_core/controllers/endpoints.py`) derives an operation id from the path
and method instead of requiring one per handler:

```python
operation_id = "-".join((*segments, action))
```

`segments` are the url's non-parameter parts (`{id}`-style segments dropped);
`action` is the HTTP method lowercased, *unless* the controller is a
`ModelController`, in which case `ModelOperationIdEndpoint` maps method +
instance-vs-collection onto a friendlier verb:

| Method | Collection | Instance |
| --- | --- | --- |
| `GET` | `list` | `retrieve` |
| `POST` | `create` | `append` |
| `PUT` | `replace` | `update` |
| `PATCH` | `merge` | `modify` |
| `DELETE` | `clear` | `destroy` |

So `GET /auth/user/{id}/` becomes `auth-user-retrieve`, and
`GET /auth/user/` becomes `auth-user-list`. Every generated id is registered
with `context.registries.operation_id`; a second controller producing the
same id — most likely two controllers accidentally routed to the same path —
raises `ValueError` at schema-build time, not at request time.

## Response specs

A `ResponseSpec` declares one possible status code for an endpoint, along
with its schema, headers and cookies. `api_exceptions.specs.ERROR_SPECS`
declares one per `ApiError` subtype this API can raise — including headers
that only apply to that error, such as:

```python
ThrottleExceededSpec = ResponseSpec(
    headers={
        "Retry-After": HeaderSpec(skip_validation=True),
        "X-RateLimit-Limit": HeaderSpec(skip_validation=True),
        "X-RateLimit-Remaining": HeaderSpec(skip_validation=True),
        "X-RateLimit-Reset": HeaderSpec(skip_validation=True),
    },
    return_type=ApiErrorResponse.from_exc(ThrottleExceededError),
    status_code=ThrottleExceededError.default_http_status,
)
```

`ERROR_SPECS` is registered once, globally, as `Settings.responses` in
`api_core.settings.DMR_SETTINGS` — every endpoint's documented responses
therefore include the *entire* error catalog automatically, not just the
subset a given handler happens to raise explicitly. A controller only adds
`ResponseSpec`s of its own for successful, non-default status codes (a `204`
from a `delete`, for instance is handled by `dmr`'s `@modify(status_code=...)`
decorator rather than a full spec).

## Security schemes

Each `AsyncAuth` in a controller's `auth` sequence contributes its own
`security_schemes` and `security_requirement` to the document, keyed by
`security_scheme_name`:

- **`JwtCookieAsyncAuth`** contributes *two* schemes: an `apiKey`-in-cookie
  scheme named after `cookie_name` (`"jwtCookie"`), and a second `apiKey`-in-header
  scheme for the CSRF header (`CONFIG.csrf_header`) — because a browser client
  authenticated by cookie must also present a CSRF token (see
  [Authentication](../api/authentication.md)). Its `security_requirement`
  explicitly lists both.
- **`JwtHeaderAsyncAuth`** contributes one `http`-`bearer` scheme
  (`"jwtHeader"`), no CSRF requirement — a native client authenticated by
  `Authorization: Bearer` has no cookie to forge a request with.

Since `BaseController.auth` lists both in sequence, every endpoint's generated
spec documents both flavours as alternatives — a client may authenticate
either way, and the schema says so without either flavour needing its own
controller subclass.

## Failure modes at schema-build time

`build_schema(router)` runs during import (`api_core.api` module load), so
these fail fast, before the process ever serves a request:

- **Duplicate operation ids** — two endpoints resolving to the same id, raised
  from `PathOperationIdEndpoint.get_operation_id` as described above.
- **Unsolvable serializer/type arguments** — a controller whose generic
  parameters `dmr` can't infer (`UnsolvableAnnotationsError`), usually a
  controller declared without a concrete serializer type argument anywhere in
  its MRO.
- **Response schema validation failures**, in `DEBUG`, the first time
  `/openapi/` is hit and `OpenAPIJsonView` validates the generated document
  against the OpenAPI meta-schema.

All three are development-time signals: a broken controller declaration or a
broken response contract, not something a client request can trigger.
