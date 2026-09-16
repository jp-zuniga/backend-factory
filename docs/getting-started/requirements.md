---
icon: lucide/clipboard-check
---

# Requirements

## Runtime

| Requirement | Version | Why |
| --- | --- | --- |
| Python | 3.14 | pinned in `.python-version`; `uv` installs it if it's missing. |
| [PostgreSQL][postgres-docs] | 18 | the only supported database — the template relies on triggers, expression indexes and advisory locks that don't have a portable equivalent. |
| Redis | 8 | backs the JWT blocklist and the throttling counters. |

## Tooling

| Tool | Used for |
| --- | --- |
| [`uv`][uv-docs] | dependency resolution and running everything inside the project's virtualenv (`just run-frozen`, under the hood, is `uv run --frozen`). |
| `just` | the task runner — every recipe in [Commands](commands.md) is a `just` recipe. |
| `docker` (with `docker compose`) | runs PostgreSQL and Redis locally, and builds the image described in [Deployment](../guides/deployment.md). |
| `prettier` | formats every file `just fmt` touches that isn't Python or TOML (Markdown, YAML, JSON). |

## Optional

Nix with direnv picks up `.envrc` (`use flake`) and drops you into the shell defined in `flake.nix`, which pins `docker-compose`, `jq`, `prettier`, `just`, `railway` and `uv` to the exact versions the template was built against. Nothing in the template requires it — install the tools above yourself if you'd rather not use Nix.

## Missing a tool?

Recipes that shell out to something outside the Python environment guard themselves with a private `check-dep` recipe first. Run one without the dependency installed and you get a Spanish error and a non-zero exit instead of a confusing failure further down:

```console
$ just fmt
`prettier` debe estar instalado.
```

The message names the missing binary; install it and re-run the recipe.
