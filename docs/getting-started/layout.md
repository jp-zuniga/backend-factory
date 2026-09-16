---
icon: lucide/list-tree
---

# Project layout

Everything lives under `src/`, as a flat list of Django apps rather than a
single monolithic one.

## `api_core`

The framework layer everything else builds on: the generic controller
families, the base schema classes and wire types, the operation objects that
talk to the database, the base models every table inherits from, the routing
helpers that turn a controller into a URL, and the Django project's own
`settings.py`, `urls.py` and `asgi.py`. If a concept applies to every app in
the project, it's defined here. See [Concepts](../concepts/index.md).

## `api_auth`

Authentication, users, groups and permissions — and the reference
implementation of every convention `api_core` defines. When in doubt about
how to shape a new model, schema, operation or controller, look at how
`api_auth` does it first. See [API](../api/index.md) for the endpoints it
exposes.

## `api_exceptions`

The error hierarchy (`ApiError` and its typed subclasses) and the single
exception handler that turns any of them — or anything unrecognised — into a
response body. See [Errors](../concepts/errors.md).

## `api_middlewares`

Two middlewares: one attaches request context (who, when, what) that
`pghistory` reads when writing audit rows, the other partitions cookies for
the two authentication flavours. See [Database](../concepts/database.md) and
[Authentication](../api/authentication.md).

## `api_utils`

Small, dependency-free helpers used across every other app: database lookups
and helpers (`db.py`), environment parsing (`env.py`), string utilities
(`strings.py`), shared typing helpers (`types.py`), and factory helpers used
by tests (`factories.py`). Nothing here imports from `api_core` or `api_auth`
— the dependency only ever goes the other way.

## `api_tests`

Where cross-app tests and shared fixtures live, alongside app-local
`tests/`-style modules. Fixtures here assume a running PostgreSQL and Redis —
see [Testing](../guides/testing.md).

## Adding a domain app

New apps follow the same naming convention as `api_core` and `api_auth`:
`api_<domain>`, with a matching Django app `label` of `api<domain>` (no
underscore — see `ApiCore`/`ApiAuth` in each app's `apps.py`) to keep
migration and content-type tables short. Register the app in
`INSTALLED_APPS` in `src/api_core/settings.py`, and shape it the way
`api_auth` is shaped: `models/`, `schemas/`, `controllers/`, `services/`, and
a `filtersets/` package if it exposes list endpoints. [Adding a
resource](../guides/new-resource.md) walks through building one end to end.
