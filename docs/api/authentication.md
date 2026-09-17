---
icon: lucide/fingerprint
---

# Authentication

The API supports two authentication flavours side by side. A client picks
the one that matches how it runs; the endpoints, cookies, and headers below
are consistent across every flow described in [Sessions](sessions.md),
[Two-factor authentication](two-factor.md), and
[Users and permissions](users.md).

=== "Cookies"

    Meant for a browser client. The two tokens are set as `httponly`
    cookies by the API itself; no script on the page ever reads or stores
    them.

    | Cookie     |    Contents    | Lifetime |
    | :--------: | :------------: | :------: |
    | `access`   |  Access token  | 3 hours  |
    | `refresh`  | Refresh token  |  1 day   |

    Because the browser attaches these cookies to every request on its
    own, every unsafe request (`POST`, `PUT`, `PATCH`, `DELETE`) must also
    carry a CSRF header, or it is rejected with `403`:

    | Header         |                   Value                    |
    | :------------: | :-----------------------------------------: |
    | `x-csrftoken`  | The token handed out by `GET /auth/csrf/`  |

    ```http
    GET /auth/csrf/ HTTP/1.1
    ```

    Answers `204` and puts the current token in that same response
    header (the cookie carrying the CSRF token is `httponly`, so the
    header is the only way a browser script can ever read it). It should
    be called once before the first unsafe request, and again whenever a
    login/refresh/2FA endpoint rotates the token (each of those responses
    includes the header too).

=== "Bearer Token"

    Meant for a native client or a script. The API never sets cookies for
    this flavour; both tokens come back in the JSON response body, and the
    client is responsible for storing and sending them itself.

    | Header           |          Value           |
    | :--------------: | :-----------------------: |
    | `Authorization`  | `Bearer <access token>`  |

    There is no CSRF requirement here: a bearer token has to be
    deliberately attached by the client, so there is nothing for a
    third-party site to forge.

## The access/refresh pair

Both flavours issue the same kind of pair underneath. The access token
lasts 3 hours and is sent on every authenticated request. The refresh token
lasts 1 day and is spent once, at `/auth/{web,mobile}/refresh/`, to get a
brand new pair. Every pair shares a session id baked into both tokens'
claims, which is what lets logging out, or revoking one token, invalidate
the other half of the same pair in one move.

## Revocation

A revoked token is checked on every authenticated request, in addition to
the normal signature and expiry checks, so a token that's technically
still unexpired but was revoked, by a logout or by being spent as a
refresh token, is rejected as `401 Unauthorized`.

Logging out (`POST /auth/{web,mobile}/logout/`) revokes the whole
session: both the access and refresh token stop working immediately, even
though the access token's own expiry hasn't passed yet.

## What every authenticated request needs

The web flavour needs the `access` cookie present, plus the `x-csrftoken`
header on unsafe methods. The mobile flavour needs the
`Authorization: Bearer <access>` header. A missing or invalid credential
answers `401`; see [Errors](errors.md) for the response shape.
