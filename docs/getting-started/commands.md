---
icon: lucide/monitor
---

# Commands

Every recipe below is defined in the `justfile` at the repository root. Run
`just` with no arguments to list them all.

## Quality

The loop you run before every commit:

| Recipe            | Runs                                                     |
| ----------------- | -------------------------------------------------------- |
| `just check`      | `ty check` — the type checker.                           |
| `just lint`       | `ruff check --unsafe-fixes` and `tombi lint` (TOML).     |
| `just fmt`        | `ruff format`, `tombi format`, and `prettier --write .`. |
| `just full-check` | `check` then `lint`.                                     |
| `just full-fix`   | `check --fix`, then `lint --fix`, then `fmt`.            |

`just fix` runs only `ruff check --unsafe-fixes --fix` on its own, if you want
lint fixes without a full type check.

## Django

| Recipe               | Runs                                                                                           |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| `just dj-man <args>` | `manage.py <args>` — the escape hatch for any Django management command.                       |
| `just migrate`       | `manage.py migrate`.                                                                           |
| `just mk-migrations` | `manage.py makemigrations`, then `just fix` and `just fmt` on the result.                      |
| `just validate`      | `manage.py check`.                                                                             |
| `just run`           | `services` + `validate`, then Granian with `--reload`, `DEBUG=True` by default — daily driver. |
| `just serve`         | the same, without `--reload` and with `DEBUG=False` — closer to production.                    |
| `just dj-repl`       | `manage.py shell`.                                                                             |

## Services and images

| Recipe                 | Runs                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| `just services`        | brings up `postgres` and `redis` via `docker compose`, only if nothing is already running. |
| `just build [profile]` | builds the `dev` or `prod` Compose profile's image (`dev` by default).                     |
| `just up [profile]`    | builds, runs `migrate`, then brings the chosen profile's `api-*` service up.               |

## Tests

| Recipe             | Runs                                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `just test <args>` | `services`, then `pytest <args>`.                                                                                                                 |
| `just pre-commit`  | `lint --fix`, `fmt`, `check`, `validate --deploy --fail-level WARNING`, then `test` — everything a hook needs before a commit is allowed through. |

See [Testing](../guides/testing.md) for what the suite expects to be running
and what it asserts against `--deploy` validation.

## Docs

```bash
just zen
```

Runs `zensical serve` — serves this site locally with live reload.

## Daily

For a newcomer, the recipes worth memorizing from day one are `just run`,
`just test`, `just full-check`, and `just fmt`. Everything else — `dj-repl`,
the `local-*`/`remote-*` API helpers, `mk-migrations` — comes up as needed.

## Next

With the API answering locally and the daily loop memorized, move on to
[Concepts](../concepts/index.md) to see how a request actually travels
through `api_core` — from routing to controller to schema to operation to
model — and why `api_auth` is shaped the way it is.
