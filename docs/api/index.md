---
icon: lucide/network
---

# API

This section documents the HTTP surface the API exposes: a frontend, a
mobile app, or a script.

The API answers the same operations through two parallel endpoint
families. The web flavour is meant for browsers: tokens travel in
`httponly` cookies, and every unsafe request must carry a CSRF header. The
mobile flavour is meant for native clients and scripts: tokens travel as
bearer strings in the request and response bodies, and the client stores
them itself. A given client should pick one flavour per session; the two
are not meant to be mixed. Full detail, including cookie names and
lifetimes, is on the [Authentication](authentication.md) page.

The full OpenAPI document is served at `/openapi/`, built from the same
endpoints this section describes by hand, so the two should never
disagree. Pointing a client generator or an API explorer at it directly is
preferable to hand-transcribing paths from these pages.
