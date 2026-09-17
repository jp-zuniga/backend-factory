---
icon: lucide/play
---

# Getting started

`backend-factory` is a Django template, not a single app. Clone it and you already
have a working authentication system: registration with email confirmation,
login with optional two-factor, JWT-backed sessions in two flavours (cookies
for browsers, bearer tokens for mobile), users, groups and permissions, an
append-only audit trail, and a generated OpenAPI schema — all wired up and
tested.

What it deliberately does not have is _your_ domain. `api_auth` exists to be
read, not extended: it is the reference implementation of every convention
described under [Concepts](../concepts/index.md), so that the app you write
next — `api_billing`, `api_inventory`, whatever it turns out to be — can copy
its shape instead of inventing one.

This section is for someone who has just cloned the repository and has no
database running yet. Read it in order:

1. [Requirements](requirements.md) — what has to be installed before anything else works.
2. [Installation](installation.md) — from a fresh clone to an API answering on `localhost`.
3. [Project layout](layout.md) — where each package's responsibilities end and the next one's begin.
4. [Commands](commands.md) — the `justfile` recipes you'll run every day after that.
