---
icon: lucide/fingerprint
---

# Authentication

The API supports two authentication flavours side by side. Pick the one that
matches your client; the endpoints, cookies and headers below are consistent
across every flow described in [Sessions](sessions.md),
[Two-factor authentication](two-factor.md) and [Users and permissions](users.md).

=== "Web (cookies)"

    Meant for a browser client. The two tokens are set as `httponly` cookies
    by the API itself — no script on the page ever reads or stores them.

    | Cookie | Contents | Lifetime |
    | --- | --- | --- |
    | `access` | Access token | 3 hours |
    | `refresh` | Refresh token | 1 day |

    Because the browser attaches these cookies to every request on its own,
    every unsafe request (`POST`, `PUT`, `PATCH`, `DELETE`) must also carry a
    CSRF header, or it is rejected with `403`:

    | Header | Value |
    | --- | --- |
    | `x-csrftoken` | The token handed out by `GET /auth/csrf/` |

    `GET /auth/csrf/` answers `204` and puts the current token in that same
    response header (the cookie carrying Django's own CSRF token is
    `httponly`, so the header is the only way a browser script can ever read
    it). Call it once before the first unsafe request, and again whenever a
    login/refresh/2FA endpoint rotates the token (each of those responses
    includes the header too).

=== "Mobile (bearer)"

    Meant for a native client or a script. The API never sets cookies for
    this flavour — both tokens come back in the JSON response body, and the
    client is responsible for storing and sending them itself.

    | Header | Value |
    | --- | --- |
    | `Authorization` | `Bearer <access token>` |

    There is no CSRF requirement here: a bearer token has to be deliberately
    attached by the client, so there is nothing for a third-party site to
    forge.

## The access/refresh pair

Both flavours issue the same kind of pair underneath:

- **Access token** — 3 hours. Sent on every authenticated request.
- **Refresh token** — 1 day. Spent once, at `/auth/{web,mobile}/refresh/`, to
  get a brand new pair.

Every pair shares a session id (`sid`) baked into both tokens' claims —
that's what lets logging out, or revoking one token, invalidate the other
half of the same pair in one move, without having to blocklist every jti a
session ever issued.

## Revocation

Revoked tokens are tracked in a Redis-backed blocklist keyed by that session
id (falling back to the bare `jti` for tokens that don't carry one, such as
the two-factor challenge). A token is checked against the blocklist on every
authenticated request, in addition to the normal signature/expiry checks —
so a token that's technically still unexpired but was blocklisted (by a
logout, or by being spent as a refresh token) is rejected as
`401 Unauthorized`.

**Logging out** (`POST /auth/{web,mobile}/logout/`) blocklists the whole
session: both the access and refresh token stop working immediately, even
though the access token's own expiry hasn't passed yet.

## What every authenticated request needs

| Flavour | Requirement                                                     |
| ------- | --------------------------------------------------------------- |
| Web     | `access` cookie present; `x-csrftoken` header on unsafe methods |
| Mobile  | `Authorization: Bearer <access>` header                         |

A missing or invalid credential answers `401`; see
[API → Errors](errors.md) for the response shape.
