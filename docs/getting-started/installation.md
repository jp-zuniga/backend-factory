---
icon: lucide/blocks
---

# Installation

Everything below is exactly what `just init-local` runs. Reading it once means
you understand what a second developer needs to change before they clone the
same repository.

## 1. Environment

```bash
just init-env
```

Copies `.env.example` to `.env`, and along the way replaces every value
literally equal to `"SECRET!!!"` — `SECRET_KEY` and `JWT_SECRET_KEY` — with a
random 128-character string. Nothing else in the file is touched: database
and Redis URLs, mail backend, TOTP issuer and Granian settings all keep their
example defaults.

## 2. Superuser credentials

`init-local` then prompts for `DJANGO_SUPERUSER_PASSWORD` and
`DJANGO_SUPERUSER_USERNAME` (the password prompt is silent) and writes both
into `.env`. They're read later, non-interactively, by `just mk-admin` — and
by the `justfile`'s own `get-token` recipe, which logs in as that superuser
whenever you use `just local-get`/`local-post`/etc. to hit the API from the
command line.

## 3. Dependencies, services, schema, seed data

In order:

```bash
just sync      # uv sync --frozen
just services  # docker compose up --detach --wait postgres redis
just migrate   # manage.py migrate
just mk-admin  # manage.py createsuperuser --noinput
just dj-man populate
```

`just prek install` also runs in between, wiring up the pre-commit hooks
defined in `.prek.toml`. `populate` is `api_core`'s management command for
local sample data — see [Seeding](../guides/seeding.md) for what it creates
and why it refuses to run when `DEPLOY=True`.

Run the whole sequence in one shot with:

```bash
just init-local
```

## 4. First run

```bash
just run
```

Starts Granian on `api_core.asgi:application` with `--reload`, after making
sure `services` are up and `manage.py check` (`just validate`) passes. Once
it's up:

- `GET /health/` — the health-check endpoint (database, cache, and anything
  else registered with `django-health-check`).
- `GET /openapi/` — the generated OpenAPI document, see
  [OpenAPI](../concepts/openapi.md).

## Before a second developer joins

- **Secrets.** `.env` is per-developer; regenerate `SECRET_KEY` and
  `JWT_SECRET_KEY` for each clone rather than sharing one `.env` file, and
  never commit it.
- **`FRONTEND_URL`.** Confirmation and password-reset links are built from
  this value — see [Email](../guides/email.md). Point it at wherever the
  frontend actually runs.
- **Mail.** The example `.env` ships with the console `EMAIL_BACKEND`, which
  prints messages to stdout instead of sending them. Set `EMAIL_HOST`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and the rest before anyone needs a
  real confirmation email.
