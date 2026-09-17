set dotenv-load
set quiet

########################################################################################

just_dir := justfile_directory() + "/"

########################################################################################

django_host := env("DJANGO_HOST", "127.0.0.1")
django_pass := env("DJANGO_SUPERUSER_PASSWORD", "")
django_port := env("DJANGO_PORT", "8080")
django_remote := env("DJANGO_REMOTE", "")
django_user := env("DJANGO_SUPERUSER_USERNAME", "")

########################################################################################

django_local := "http://" + django_host + ":" + django_port

########################################################################################

manage_py := just_dir + "src/manage.py"
prek_toml := just_dir + ".prek.toml"
request_json := just_dir + ".request.json"

########################################################################################

[private]
default:
    @just --list --list-heading "" --list-prefix ""

########################################################################################

[private]
check-dep cmd pretty="":
    #!/usr/bin/env bash
    set -euo pipefail

    PRETTY="{{ pretty }}"

    if [ -z "$PRETTY" ]; then
      PRETTY="{{ cmd }}"
    fi

    if ! command -v {{ cmd }} > /dev/null 2>&1; then
      echo "\`$PRETTY\` debe estar instalado." >&2
      exit 1
    fi

[private]
pre-commit $DEBUG="False":
    @just lint --fix
    @just fmt
    @just check
    @just validate --deploy --fail-level WARNING
    @just test

[private]
run-frozen *cmd: (check-dep "uv")
    uv run --frozen {{ cmd }}

[private]
services: (check-dep "docker")
    #!/usr/bin/env bash
    set -euo pipefail

    if [ -z "$(docker compose ps -q)" ]; then
      docker compose up --detach --wait postgres redis
    fi

########################################################################################

[group("uv")]
check *args="":
    @just run-frozen ty check --no-progress {{ args }}

[group("uv")]
full-check: check lint

[group("uv")]
full-fix:
    @just check --fix
    @just lint --fix
    @just fmt

[group("uv")]
fix *args="":
    @just lint --fix {{ args }}

[group("uv")]
fmt *args="": (check-dep "prettier")
    @just run-frozen ruff format {{ args }}
    @just run-frozen tombi format
    prettier --write .

[group("uv")]
lint *args="":
    @just run-frozen ruff check --unsafe-fixes {{ args }}
    @just run-frozen tombi lint

[group("uv")]
prek *args:
    @just run-frozen prek -c {{ prek_toml }} {{ args }}

[group("uv")]
repl *args="":
    @just run-frozen python {{ args }}

[group("uv")]
sync: (check-dep "uv")
    uv sync --frozen

[group("uv")]
test *args="": services
    @just run-frozen pytest {{ args }}

[group("uv")]
zen:
    @just run-frozen zensical serve

########################################################################################

[group("django")]
dj-man *args="":
    @just run-frozen {{ manage_py }} {{ args }}

[group("django")]
dj-repl *args="":
    @just run-frozen {{ quote(manage_py) }} shell {{ args }}

[group("django")]
init-env:
    #!/usr/bin/env bash
    set -eu

    EXAMPLE=".env.example"
    ENV=".env"
    TMP=".env.tmp"

    if [[ ! -f "$EXAMPLE" ]]; then
      echo "\`$EXAMPLE\` no existe." >&2
      exit 1
    fi

    > "$TMP"

    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" == *'"SECRET!!!"'* ]]; then
        NEW=$(tr -dc 'a-zA-Z0-9-_' < /dev/urandom | head -c 128)

        echo "${line/\"SECRET!!!\"/\"$NEW\"}" >> "$TMP"
      else
        echo "$line" >> "$TMP"
      fi
    done < "$EXAMPLE"

    mv "$TMP" "$ENV"

[group("django")]
init-local: init-env
    #!/usr/bin/env bash
    set -euo pipefail

    PASS_VAR="DJANGO_SUPERUSER_PASSWORD"
    USER_VAR="DJANGO_SUPERUSER_USERNAME"

    read -srp "$PASS_VAR=" PASS_ANS
    echo

    if [[ -z "$PASS_ANS" ]]; then
      echo "Debe ingresar una contraseña para el superuser local." >&2
      exit 1
    fi

    read -rp "$USER_VAR=" USER_ANS
    echo

    if [[ -z "$USER_ANS" ]]; then
      echo "Debe ingresar un usuario para el superuser local." >&2
      exit 1
    fi

    sed -i.bak "s|^$PASS_VAR=.*|$PASS_VAR=\"$PASS_ANS\"|" .env
    sed -i.bak "s|^$USER_VAR=.*|$USER_VAR=\"$USER_ANS\"|" .env

    rm -f .env.bak

    just sync
    just prek install
    just services
    just migrate
    just mk-admin
    just dj-man populate

[group("django")]
migrate *args="": services
    @just run-frozen {{ manage_py }} migrate {{ args }}

[group("django")]
mk-admin: services
    #!/usr/bin/env bash
    set -euo pipefail

    just run-frozen {{ manage_py }} createsuperuser --noinput

[group("django")]
mk-migrations *args="": services
    @just run-frozen {{ manage_py }} makemigrations {{ args }}
    @just fix
    @just fmt

[group("django")]
run $DEBUG="True" *args="": services validate
    @just run-frozen granian api_core.asgi:application --reload {{ args }}

[group("django")]
serve $DEBUG="False" *args="": services validate
    @just run-frozen granian api_core.asgi:application {{ args }}

[group("django")]
validate *args="": services
    @just run-frozen {{ manage_py }} check {{ args }}

########################################################################################

[group("api")]
[private]
api-action target method endpoint args data: (check-dep "jq")
    #!/usr/bin/env bash
    set -euo pipefail

    TOKEN=$(just get-token {{ target }})

    URL=""
    ARGS={{ quote(args) }}

    if [ "{{ target }}" == "local" ]; then
      URL="{{ django_local }}"
    else
      URL="{{ django_remote }}"
    fi

    URL="$URL/{{ endpoint }}"

    if [ -n "$ARGS" ]; then
      URL="$URL/?$ARGS"
    else
      URL="$URL/"
    fi

    just request "$URL" "{{ method }}" {{ quote(data) }} "$TOKEN"

[group("api")]
[private]
get-token target: (check-dep "jq")
    #!/usr/bin/env bash
    set -euo pipefail

    if [ "{{ target }}" == "local" ]; then
      BASE="{{ django_local }}"
    else
      BASE="{{ django_remote }}"
    fi

    LOGIN="$BASE/auth/mobile/login/"

    CT="Content-Type: application/json"

    JSON=$(jq -nc --arg u {{ quote(django_user) }} --arg p {{ quote(django_pass) }} '{username: $u, password: $p}')

    RESPONSE=$(curl -s -X "POST" "$LOGIN" -H "$CT" -d "$JSON")

    JWT=$(echo "$RESPONSE" | jq -r '.access // empty')

    if [ -z "$JWT" ]; then
      echo "Error al obtener el token JWT." >&2
      echo "La respuesta fue:" >&2
      echo "$RESPONSE" >&2
      exit 1
    fi

    echo "$JWT"

[group("api")]
[private]
request url method data token:
    #!/usr/bin/env bash
    set -euo pipefail

    AUTH="Authorization: Bearer {{ token }}"
    CT="Content-Type: application/json"

    DATA={{ quote(data) }}

    ARGS=(-so "{{ request_json }}" -w "%{http_code}" -X "{{ method }}" "{{ url }}" -H "$CT" -H "$AUTH")

    if [[ -n "$DATA" ]]; then
      ARGS+=(-d "$DATA")
    fi

    HTTP=$(curl "${ARGS[@]}")

    echo "$HTTP"

    if [ -z "{{ request_json }}" ]; then
      exit 0
    fi

    if command -v prettier > /dev/null 2>&1; then
      prettier --ignore-path "" --write {{ request_json }} > /dev/null 2>&1
    fi

    if command -v zeditor > /dev/null 2>&1; then
      zeditor {{ request_json }} > /dev/null 2>&1
      exit 0
    elif command -v code > /dev/null 2>&1; then
      code -r {{ request_json }} > /dev/null 2>&1
      exit 0
    fi

########################################################################################

[group("api-local")]
local-del endpoint:
    @just api-action local DELETE "{{ endpoint }}" "" ""

[group("api-local")]
local-get endpoint="health" args="":
    @just api-action local GET "{{ endpoint }}" "{{ args }}" ""

[group("api-local")]
local-patch endpoint data="":
    @just api-action local PATCH "{{ endpoint }}" "" {{ quote(data) }}

[group("api-local")]
local-post endpoint data="":
    @just api-action local POST "{{ endpoint }}" "" {{ quote(data) }}

[group("api-local")]
local-put endpoint data="":
    @just api-action local PUT "{{ endpoint }}" "" {{ quote(data) }}

########################################################################################

[group("api-remote")]
remote-del endpoint:
    @just api-action remote DELETE "{{ endpoint }}" "" ""

[group("api-remote")]
remote-get endpoint="health" args="":
    @just api-action remote GET "{{ endpoint }}" "{{ args }}" ""

[group("api-remote")]
remote-patch endpoint data="":
    @just api-action remote PATCH "{{ endpoint }}" "" {{ quote(data) }}

[group("api-remote")]
remote-post endpoint data="":
    @just api-action remote POST "{{ endpoint }}" "" {{ quote(data) }}

[group("api-remote")]
remote-put endpoint data="":
    @just api-action remote PUT "{{ endpoint }}" "" {{ quote(data) }}
