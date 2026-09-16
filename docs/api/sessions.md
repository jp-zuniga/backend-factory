---
icon: lucide/key-round
---

# Sessions

The endpoints that open, refresh, inspect and close a session. Every one of
them exists twice — once per [authentication flavour](authentication.md) —
under `/auth/web/…/` and `/auth/mobile/…/`.

## Logging in

```http
POST /auth/mobile/login/
Content-Type: application/json

{"username": "jdoe", "password": "hunter2"}
```

There are two possible outcomes:

=== "No second factor"

    ```json title="200 OK"
    {
      "access": "…",
      "refresh": "…",
      "user": { "id": "...", "username": "jdoe", "...": "..." }
    }
    ```

    (The web variant, `POST /auth/web/login/`, answers the same `200` but
    puts the tokens in cookies instead of the body — see
    [Authentication](authentication.md) — and the body only contains `user`.)

=== "Second factor enabled"

    ```json title="202 Accepted"
    {
      "challenge": "…",
      "expires_in": 300
    }
    ```

    The credentials were correct, but the account has
    [two-factor authentication](two-factor.md) enabled. No session exists
    yet; the client must redeem the `challenge` (a short-lived token, 5
    minutes by default) against `POST /auth/{web,mobile}/two-factor/` along
    with a TOTP or recovery code to actually get a token pair. The web
    variant sends the challenge as an `httponly` cookie instead of a body
    field.

## Refreshing

```http
POST /auth/mobile/refresh/
Content-Type: application/json

{"refresh": "…"}
```

Returns a brand new access/refresh pair. The refresh token just spent is
blocklisted as part of the same call — reusing it (say, after a client
retried a request twice) fails with `401`, because rotation is one-shot:
the old pair dies the instant the new one is issued, it never lives on to
be replayed. The web variant reads the refresh token from its cookie
instead of the body, and requires the [CSRF header](authentication.md).

## Verifying a token without spending it

```http
POST /auth/mobile/verify/
Content-Type: application/json

{"token": "…", "type": "access"}
```

Answers `204` if the token is a live, unrevoked token of the given `type`
(`access`, `refresh`, or `challenge`), `401` otherwise. This never rotates or
revokes anything — it's a pure check, useful for a client that wants to know
whether it needs to refresh before making the request it actually cares
about.

The web variant (`POST /auth/web/verify/`) takes no body — it reads whatever
`access`/`refresh` cookies are present and reports both independently:

```json title="200 OK"
{"access": true, "refresh": false}
```

## Logging out

```http
POST /auth/mobile/logout/
Content-Type: application/json

{"access": "…"}
```

Either token alone is enough — both name the same session, so sending
whichever one the client still has revokes the pair. Answers `204`. The web
variant takes no body (it reads the cookies) and additionally clears every
cookie the flow could have set (access, refresh, and the pending challenge
cookie if any), requiring [CSRF](authentication.md) like every other unsafe
web-flavour endpoint.

A client should discard **both** tokens locally after logging out — the
server has already revoked them, but nothing stops a script from holding a
stale copy and getting confusing `401`s later otherwise.

## Errors to expect

| Situation | Status | Notes |
| --- | --- | --- |
| Bad username/password | `401` | Deliberately generic — never says which was wrong |
| Unconfirmed email | `403` | See [Email confirmation](email-confirmation.md); only when `REQUIRE_EMAIL_VERIFICATION` is on |
| Revoked/expired/reused token | `401` | Covers a spent refresh token, a blocklisted session, and a plain expiry |
| Missing/invalid CSRF header (web) | `403` | See [Authentication](authentication.md) |

See [API → Errors](errors.md) for the response body shape.
