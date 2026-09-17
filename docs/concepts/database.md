---
icon: lucide/database
---

# Database

The application layer validates shapes and orchestrates writes; PostgreSQL is
trusted to make a handful of guarantees hold _no matter who or what writes to
a table_ — the ORM, a management command, a migration, or a human with
`psql`. This template leans on triggers and constraints for exactly the rules
that would otherwise have to be re-checked in every operation, every
migration, and every one-off script, forever. See
[Decisions](decisions.md) for why that trade was made, and
[Models](models.md) for the bases that install these triggers.

## Triggers as the last line of defence

Every trigger in this template comes from
[`django-pgtrigger`](https://django-pgtrigger.readthedocs.io/), attached
declaratively in a model's `Meta.triggers`. Four kinds recur:

- **Protect** — reject an operation outright. `Protect(operation=Truncate)`
  on `ApiModel` itself rejects `TRUNCATE` on every table; `Protect(operation=Delete)`
  on `ApiProtectedModel` rejects deletes; `Protect(operation=(Delete | Update))`
  on `ApiAppendOnlyModel` rejects both. Narrower, hand-written `Protect`
  triggers exist too — `ApiUserTotpDevice` protects `secret` from being
  changed once `confirmed_at` is set, and protects `confirmed_at` itself
  from being cleared once set, each guarded by a `pgtrigger.Q` condition
  comparing `old__*` to `new__*`.
- **ReadOnly** — reject a change to _specific columns_ while allowing others.
  `ApiModel` uses it on `id`; `VerificationCode` uses it on every field that
  is set at creation and never meant to move again (`api_user`, `email`,
  `token_hash`, `expires_at`, `purpose`, `created_at`), leaving only the two
  outcome timestamps (`consumed_at`, `invalidated_at`) writable.
- **SoftDelete** — rewrite a `DELETE` into an `UPDATE`. `ApiSoftDeleteModel`
  uses `SoftDelete(field="is_active", value=False)`; see
  [Models](models.md) for what this does to Django's own delete-count.
- **Touch** — a plain `Before`/`Update` trigger with a hand-written `func`
  body, used for exactly one thing here: `trg_touch_updatedat` on
  `ApiTimestampedModel`, which sets `NEW.updated_at = NOW()` on any change.

Because these run in the database, they hold even against a bulk `.update()`
or a raw `pgbulk` call that bypasses `Model.save()` entirely — which is
precisely the case `api_core.services.operations.nested` relies on for
writing large collections (see [Operations](operations.md)).

## Constraints

- **Expression uniqueness**: `ApiUser` enforces case-insensitive uniqueness
  with `UniqueConstraint(Lower("email"), condition=..., name="unq_%(class)s_email")`
  rather than a plain `unique=True` on the column, since Postgres compares
  the raw bytes by default and this template's usernames and emails are
  meant to collide case-insensitively.
- **Partial uniqueness**: the same constraint is also conditional —
  `condition=Q(email__len__gt=0, is_active=True)` — so a soft-deleted user
  and an empty email do not hold a slot that blocks a new signup from using
  it. `VerificationCode` does the same for its "one live code per user and
  purpose" rule: `UniqueConstraint(F("purpose"), Lower("email"), condition=LIVE, name="unq_%(class)s_live")`,
  where `LIVE = Q(consumed_at__isnull=True, invalidated_at__isnull=True)` — a
  spent or invalidated code frees the slot for a new one.
- **Check constraints**: `VerificationCode` also declares
  `CheckConstraint(condition=Q(purpose__in=VerificationPurposes.values), ...)`,
  `CheckConstraint(condition=Q(expires_at__gt=F("created_at")), ...)`, and one
  enforcing that a code cannot be both consumed _and_ invalidated
  (`Q(consumed_at__isnull=True) | Q(invalidated_at__isnull=True)`) — three
  invariants that would otherwise need re-checking in every code path that
  touches the table.

## Deferred constraints and `set_immediate_constraints`

`api_utils.db.set_immediate_constraints` runs `SET CONSTRAINTS ALL IMMEDIATE`
against the current connection:

```python
def set_immediate_constraints() -> None:
    """
    Should only ever be called from within a django.db.transaction.atomic block.
    The query is rolled back at the end of the transaction.
    """
    with get_connection().cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
```

It is called from `api_core.services.operations.nested` and `.m2m` right
before the write that could violate a constraint. The reason it matters: a
constraint declared `DEFERRABLE INITIALLY DEFERRED` is only checked at
`COMMIT`, not at the statement that violates it — which means an
`IntegrityError` raised at commit time carries no useful context about which
row or column caused it, well after the code that could build a precise
`409` has already returned. Forcing an immediate check right after the write
means any deferred constraint fails _inside_ `exec_nested_post` /
`exec_m2m_post`, while `exc_handler` (see [Operations](operations.md)) still
has the lookup and the row in scope to build a field-scoped error. As shipped,
no model in this template currently declares a `deferrable=` constraint — the
guard exists for the day a project adds one (a swap of two rows' unique sort
keys is the textbook case), and it is a no-op otherwise.

## History via `pghistory`

Every `@track_table`-decorated model (see [Models](models.md)) writes an
append-only `<Model>Event` row on every insert and update, via triggers
`pghistory` installs itself. What ties an event back to _why_ it happened is
context, attached per request by `api_middlewares.history.contextful_history`:

```python
async with context(url=request.path):
    return await get_response(request)
```

every request that reaches this middleware opens a `pghistory.context()`
block tagged with the request path; `api_auth.security` calls
`build_user_context` after authenticating a request to add the user's `id`
and `username` (and `email`, if set) into that same context. Both end up in
the event row's `pgh_context` JSON column, which is what `track_table`'s
generated indexes are tuned to query: a GIN index over the whole column, a
trigram GIN index over the `url` key specifically, and a plain index over
`context->user->id` — "every change a given user made" and "every change
that happened during a request to this path" are both index-backed lookups,
not full scans.

## Advisory locks and retries

`api_core.services.locks.lock_instance` is how an operation gets exclusive
access to a row it is about to mutate as part of a larger, multi-statement
write:

```python
def lock_instance(*, lookup: dict, model: type[DatabaseModel]) -> DatabaseModel:
    with guarded_lock():
        try:
            return model._default_manager.select_for_update(no_key=True).get(**lookup)
        except ObjectDoesNotExist as o:
            raise NotFoundError(...) from o
```

`select_for_update(no_key=True)` takes a `FOR NO KEY UPDATE` lock rather than
a plain `FOR UPDATE`, so a concurrent insert of a _new_ row referencing this
one via foreign key is not blocked by the lock — only a concurrent update to
this same row is. `guarded_lock` wraps the wait in
[`django-pglock`](https://django-pglock.readthedocs.io/)'s
`timeout` (5 seconds, `LOCK_TIMEOUT`) and turns a Postgres lock-wait timeout
specifically (`psycopg.errors.LockNotAvailable`) into a `409 (LOCKED)`
`ConflictError` instead of hanging the request or surfacing a raw
`OperationalError`. `exec_m2m_update` and `exec_nested_update` (see
[Operations](operations.md)) both lock the parent this way before reading
and rewriting its relations, and both are wrapped in
[`django-pgtransaction`](https://django-pgtransaction.readthedocs.io/)'s
`atomic` with `REPEATABLE_READ` isolation and
`RETRIES = 3` automatic retries — the combination that makes a concurrent
update to the same parent's relations fail fast and safe rather than
silently interleave.

## Extensions

Two migrations in `api_core.migrations` install everything this template
needs beyond a stock PostgreSQL:

- `0001_postgres_extensions.py` installs `pg_trgm` (`TrigramExtension`) and
  `unaccent` (`UnaccentExtension`) — the trigram indexes `track_table` and
  `ApiUser` both rely on for fuzzy, case- and accent-insensitive search need
  both.
- `0002_immutable_unaccent.py` wraps `unaccent()` in a hand-written
  `IMMUTABLE`/`PARALLEL SAFE`/`STRICT` SQL function,
  `public.immutable_unaccent`, because Postgres will not let a
  non-`IMMUTABLE` function be used inside an index expression — this is what
  `api_utils.db.ImmutableUnaccent` (a `django.db.models.Transform`) exposes
  to the ORM, and what `ApiUser`'s username/email GIN indexes are built on.

`uuid7()` itself needs no extension — it comes from
`django.db.models.functions.UUID7`, computed by Django/Postgres 18's own
built-in support, not a third-party extension.
