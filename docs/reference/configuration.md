---
icon: lucide/gauge
---

# Configuration

Every setting the template reads lives on one class, `ApiConfig` in
`api_core/config.py`, instantiated once as `CONFIG`. It is a pydantic
`BaseSettings`, so every field below can be set as an environment variable or
in `.env`, and every field is validated at process start — a bad value fails
before the first request, not on the request that happens to touch it. See
[Decisions](../concepts/decisions.md) and the [installation guide](../guides/deployment.md)
for why it is shaped this way.

## Runtime flags

| Field          | Type                        | Default    | What it changes                                                                                                                                                                                                                                |
| -------------- | --------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DEBUG`        | `bool`                      | `False`    | Relaxes the cookie policy (`cookie_samesite`/`cookie_secure` below), turns on `dmr`'s request/response/negotiation validation (`Settings.validate_*` in `settings.py`), and tightens `SECURE_HSTS_*`/`SECURE_PROXY_SSL_HEADER` when it is off. |
| `DEPLOY`       | `bool`                      | `False`    | Forces the strict half of the cookie policy even with `DEBUG=True`, sets `USE_X_FORWARDED_HOST`, and turns on the two deployment-only checks below (`REDIS_SECRET_KEY` length, `DEFAULT_FROM_EMAIL`/`EMAIL_HOST` non-empty).                   |
| `SECRET_KEY`   | secret string, 64–256 chars | _required_ | Django's own `SECRET_KEY` — session/signing infrastructure unrelated to the JWTs below.                                                                                                                                                        |
| `SKIP_SEEDERS` | `bool`                      | `False`    | Read by each app's seed management command (`apiauthseed`, and `api_core`'s own seeder hook) to no-op instead of inserting rows.                                                                                                               |

## Database and cache

| Field              | Type                      | Default    | What it changes                                                                                                                                                                                                         |
| ------------------ | ------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`     | `PostgresDsn`             | _required_ | Parsed into Django's `DATABASES["default"]` via the derived `pg_database` property. Must carry a single host, a path (database name), a username and a password, or the config fails validation (`check_database_url`). |
| `REDIS_URL`        | `RedisDsn`                | _required_ | Host and port for Django's cache backend, via the derived `redis_cache` property.                                                                                                                                       |
| `REDIS_SECRET_KEY` | secret string, ≤256 chars | `""`       | Redis auth password, folded into `redis_cache["OPTIONS"]` when non-empty. **Required, ≥64 chars, when `DEPLOY=True`** (`check_redis_secret_key`).                                                                       |

## JWT

| Field                    | Type                            | Default    | What it changes                                                                                                                         |
| ------------------------ | ------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `JWT_ALGORITHM`          | `"HS256" \| "HS384" \| "HS512"` | `"HS256"`  | Signing algorithm for both the cookie and header JWT auth backends (`api_core/controllers/base.py`) and for `api_auth/services/jwt.py`. |
| `JWT_SECRET_KEY`         | secret string, 64–256 chars     | _required_ | Signing/verification secret for every token this API issues.                                                                            |
| `JWT_ACCESS_LIFETIME`    | `timedelta`                     | `3h`       | Lifetime of an access token; also the `Max-Age` of the access cookie for web clients.                                                   |
| `JWT_REFRESH_LIFETIME`   | `timedelta`                     | `1d`       | Lifetime of a refresh token; also the `Max-Age` of the refresh cookie.                                                                  |
| `JWT_CHALLENGE_LIFETIME` | `timedelta`                     | `5m`       | Lifetime of the two-factor challenge token issued by login when a second factor is enabled, and of its cookie on the web flow.          |

All four lifetimes must be strictly positive (`check_lifetimes`), together with `EMAIL_VERIFICATION_LIFETIME` below.

## Two-factor

| Field                 | Type                   | Default | What it changes                                                                                         |
| --------------------- | ---------------------- | ------- | ------------------------------------------------------------------------------------------------------- |
| `TOTP_DIGITS`         | `6 \| 8`               | `6`     | Length of a generated and accepted TOTP code (`api_auth/services/totp.py`).                             |
| `TOTP_ISSUER`         | string, 1–64 chars     | `"api"` | The `issuer` embedded in the `otpauth://` enrollment URI, and half of its `label`.                      |
| `TOTP_PERIOD`         | positive int (seconds) | `30`    | The time-step a code is derived from and validated against.                                             |
| `TOTP_TOLERANCE`      | non-negative int       | `1`     | How many periods on either side of "now" a submitted code is still accepted for, to absorb clock drift. |
| `TOTP_MAX_FAILURES`   | positive int           | `5`     | Consecutive failed codes before a device is locked (`api_auth/services/twofactor.py`).                  |
| `TOTP_LOCKOUT`        | `timedelta`            | `15m`   | How long a device stays locked after hitting `TOTP_MAX_FAILURES`.                                       |
| `TOTP_RECOVERY_CODES` | positive int           | `10`    | How many one-time recovery codes are generated on enrollment and on each rotation.                      |

## Email

| Field                         | Type                      | Default                                            | What it changes                                                                                                    |
| ----------------------------- | ------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `EMAIL_BACKEND`               | string                    | `"django.core.mail.backends.console.EmailBackend"` | Django's `EMAIL_BACKEND` — swap for an SMTP backend in a deployment.                                               |
| `EMAIL_HOST`                  | string                    | `""`                                               | SMTP host. **Required (non-empty) when `DEPLOY=True`** (`check_email_delivery`).                                   |
| `EMAIL_PORT`                  | positive int              | `587`                                              | SMTP port.                                                                                                         |
| `EMAIL_HOST_USER`             | string                    | `""`                                               | SMTP username.                                                                                                     |
| `EMAIL_HOST_PASSWORD`         | secret string, ≤256 chars | `""`                                               | SMTP password.                                                                                                     |
| `EMAIL_USE_TLS`               | `bool`                    | `True`                                             | Whether the SMTP connection is upgraded with TLS.                                                                  |
| `DEFAULT_FROM_EMAIL`          | string                    | `"no-reply@localhost"`                             | The `From` address on every message the API sends. **Required (non-empty) when `DEPLOY=True`.**                    |
| `REQUIRE_EMAIL_VERIFICATION`  | `bool`                    | `True`                                             | Whether a freshly registered account must confirm its email before it can log in (`api_auth/services/account.py`). |
| `EMAIL_VERIFICATION_LIFETIME` | `timedelta`               | `24h`                                              | How long a confirmation/resend token stays valid.                                                                  |

## Frontend

| Field          | Type      | Default                   | What it changes                                                                                                                                   |
| -------------- | --------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FRONTEND_URL` | `HttpUrl` | `"http://localhost:3000"` | Base url used to build links in outgoing email (verification, etc.); exposed trimmed of a trailing slash via the derived `frontend_url` property. |

## Required vs. deployment-only

Four fields have no default and are always required: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `SECRET_KEY`. Three more have a default but are enforced non-empty/long-enough only when `DEPLOY=True`: `REDIS_SECRET_KEY` (≥64 chars), `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`. All of this is enforced by `pydantic`'s `model_validator`s on `ApiConfig` itself — a misconfigured deployment fails at import time (`CONFIG = ApiConfig()` at the bottom of `config.py`), before Django finishes booting. See [Deployment](../guides/deployment.md) for what else `DEPLOY=True` tightens outside of `ApiConfig` (HSTS, cookie policy).

## Derived values

These are not settings — they are `@cached_property` values computed from the fields above, read by `settings.py` and by `api_auth/security.py`/`services/csrf.py`:

| Property                  | Derived from                    | Value                                                     |
| ------------------------- | ------------------------------- | --------------------------------------------------------- |
| `cookie_secure`           | `DEBUG`, `DEPLOY`               | `not DEBUG or DEPLOY`                                     |
| `cookie_samesite`         | `DEBUG`, `DEPLOY`               | `"Lax"` only when `DEBUG` and not `DEPLOY`, else `"None"` |
| `cookie_samesite_policy`  | `cookie_samesite`               | The same value, lowercased, for `dmr.cookies.CookieSpec`  |
| `csrf_cookie_name`        | —                               | `"csrftoken"`                                             |
| `csrf_header`             | `csrf_cookie_name`              | `f"x-{csrf_cookie_name}"`, i.e. `x-csrftoken`             |
| `frontend_url`            | `FRONTEND_URL`                  | Stringified, trailing slash stripped                      |
| `pg_database` / `pg_host` | `DATABASE_URL`                  | Django's `DATABASES["default"]` dict                      |
| `redis_cache`             | `REDIS_URL`, `REDIS_SECRET_KEY` | Django's `CACHES["default"]` dict                         |

There is also a `cookie_samesite == "None" and not cookie_secure` guard (`check_cookie_policy`): the combination is illegal to browsers, so `ApiConfig` refuses to construct with it rather than shipping cookies no client will accept.

## `.env.example` keys

Most keys map onto a field of the same name:

`DEBUG`, `DEPLOY`, `SKIP_SEEDERS`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `SECRET_KEY`, `REDIS_SECRET_KEY`, `FRONTEND_URL`, `REQUIRE_EMAIL_VERIFICATION`, `DEFAULT_FROM_EMAIL`, `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_PASSWORD`, `EMAIL_HOST_USER`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `TOTP_ISSUER`.

Two groups of keys in `.env.example` do **not** map onto `ApiConfig` at all:

- `GRANIAN_*` (`GRANIAN_HOST`, `GRANIAN_INTERFACE`, `GRANIAN_LOG_ACCESS_ENABLED`, `GRANIAN_PORT`, `GRANIAN_RELOAD_PATHS`, `GRANIAN_WORKERS`, `GRANIAN_WORKING_DIR`, `GRANIAN_WS`) configure the `granian` ASGI server directly, read by `granian` itself from the environment rather than through `ApiConfig`.
- `DJANGO_SUPERUSER_PASSWORD` / `DJANGO_SUPERUSER_USERNAME` are read by Django's own `createsuperuser` management command at `just mk-admin` time, not by `ApiConfig`.

See [Commands](../getting-started/commands.md) and [Installation](../getting-started/installation.md) for where those two groups are actually used.
