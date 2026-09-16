---
icon: lucide/network
---

# API

This section documents the HTTP surface the template ships with, for whoever is
*consuming* it — a frontend, a mobile app, or a script. If you are extending the
template instead, see [Concepts](../concepts/index.md) and [Guides](../guides/index.md).

## Base url and content types

Every endpoint below is mounted under the app's root; the auth surface itself
lives under an `/auth/` prefix (for example `/auth/login/web/` is wrong, the
real path is `/auth/web/login/` — namespace comes before the resource name).
Requests and responses are JSON (`application/json`); there is no other
content negotiation configured for the endpoints this template ships.

## Two ways to authenticate

The API answers the same operations through two parallel controller families:

- **Web** — the browser flavour. Tokens travel in `httponly` cookies, and
  every unsafe request must carry a CSRF header. See
  [Authentication](authentication.md).
- **Mobile** — the native/script flavour. Tokens travel as bearer strings in
  the request and response bodies, and the client stores them itself.

Pick one flavour per client; the two are not meant to be mixed on the same
session. Full detail, including cookie names and lifetimes, is on the
[Authentication](authentication.md) page.

## What ships in the box

| Group | Endpoints |
| --- | --- |
| Sessions | log in, refresh, verify, log out (web and mobile variants of each) |
| Email confirmation | register, confirm, resend |
| Two-factor | status, enroll, confirm, recover, disable, and the login-time challenge |
| Users | profile, staff-managed user list/detail, group and permission assignment |
| Groups & permissions | read/write groups, read-only permissions |

See [Sessions](sessions.md), [Email confirmation](email-confirmation.md),
[Two-factor authentication](two-factor.md) and [Users and permissions](users.md)
for the endpoint-by-endpoint detail.

## The machine-readable contract

The full OpenAPI document is served at `/openapi/` (built and served by
[dmr-docs] from the same controllers this section describes by hand — the
two should never disagree). Point a client generator or an API explorer at it
directly instead of hand-transcribing paths from these pages.

## Reading order

1. [Conventions](conventions.md) — the rules that hold for every endpoint, so
   the flow pages below don't repeat them.
2. [Authentication](authentication.md)
3. [Sessions](sessions.md)
4. [Email confirmation](email-confirmation.md)
5. [Two-factor authentication](two-factor.md)
6. [Users and permissions](users.md)
7. [Errors](errors.md)
