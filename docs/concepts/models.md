---
icon: lucide/boxes
---

# Models

Every table in this template inherits from one of five abstract bases in
`api_core.models.base`, each adding fields, indexes and `pgtrigger` triggers
on top of the last. Choosing between them is choosing what the database — not
the application — refuses to let happen; see [Database](database.md) for how
the triggers themselves work, and
[Choosing a base model](../guides/base-models.md) for the decision guide.

## The four (plus the root)

| Base | Adds | A row may be | Deleted by a client means |
|---|---|---|---|
| `ApiModel` | `id` (uuid7, immutable) | inserted, updated, deleted | a real `DELETE` |
| `ApiTimestampedModel` | `created_at`, `updated_at` (trigger-maintained) | inserted, updated, deleted | a real `DELETE` |
| `ApiAppendOnlyModel` | — (drops `updated_at`) | inserted only | never — the trigger rejects it |
| `ApiProtectedModel` | — | inserted, updated | never — the trigger rejects it |
| `ApiSoftDeleteModel` | `is_active` (trigger-maintained on delete) | inserted, updated, deleted | `is_active = False`, row survives |

### `ApiModel`

```python
class ApiModel(Model):
    id = UUIDField(db_default=UUID7(), default=uuid7, primary_key=True)

    class Meta:
        abstract = True
        triggers = (
            Trigger(name="trg_protect_truncate", operation=Truncate, when=Before, ...),
            ReadOnly(fields=["id"], name="trg_readonly_primarykey"),
        )
```

The root every other base extends. Two things happen here and nowhere else:
the primary key is a **uuid7**, generated identically by Postgres
(`db_default=UUID7()`) and by the ORM (`default=uuid7`) so an unsaved
instance already has a real, sortable id before it ever reaches the database
— see [Decisions](decisions.md) for why uuid7 over a serial integer. And the
primary key is made **immutable** by a `ReadOnly` trigger, plus a
statement-level trigger that turns `TRUNCATE` into a raised exception on
every table, regardless of which base a model further down the chain uses.

### `ApiTimestampedModel`

Adds `created_at`/`updated_at`, both database-defaulted to `now()` and kept
in sync by a trigger — `trg_touch_updatedat` rewrites `updated_at` to `NOW()`
on any change, so it stays correct no matter what writes the row: the ORM, a
management command, a migration, or `psql` by hand. It also sets
`ordering = ("-id",)`, relying on the fact that a uuid7 is monotonically
increasing, so "newest first" and "highest id first" are the same ordering
without a second index.

### `ApiAppendOnlyModel`

Drops `updated_at` (there is nothing to update) and adds one trigger:
`Protect(operation=(Delete | Update))`, name `trg_append_only`. A row, once
inserted, cannot be changed or removed by *anything* — application code,
a bug, or an operator with a `psql` shell. Used for rows that are a record
of something having happened, not a piece of current state.

### `ApiProtectedModel`

The opposite half of the same idea: `Protect(operation=Delete)` only. Rows
may be edited freely but never removed — for records other tables, an audit
trail, or a human are expected to keep referring to by id indefinitely.

### `ApiSoftDeleteModel`

Adds `is_active` (default `True`) and a `SoftDelete` trigger
(`field="is_active", value=False`) that intercepts a `DELETE` statement and
rewrites it into `UPDATE ... SET is_active = false` at the database level —
the ORM, and the client, asked for a delete and got one; the row simply did
not disappear. `ApiUser` is built on this base. Because the row still exists,
every query against a soft-deleted table has to filter `is_active=True`
explicitly wherever "deleted" should mean gone — the base does not do this
for you, and neither does `FlatDestroyOperation` verify it beyond checking
`exists()` (see [Operations → flat operations](operations.md), which spells
out why a soft delete makes Django's own delete-count come back `0`).

## Pairing a base with a controller family

The base a model uses is only half of the guarantee — the other half is
which controller sits in front of it. A base that raises `Protect` on
`DELETE` still lets a client's `DELETE /resource/{id}/` request reach the
database and fail as a trigger error (a `500`, since nothing in the request
path expected it) unless the *controller* itself does not expose a `destroy`
endpoint in the first place. Pick the controller family
([Controllers](controllers.md)) that matches the base up front, so an
unsupported method comes back as a clean `405` — this pairing is spelled out
in [Choosing a base model](../guides/base-models.md).

## Naming rules

Every constraint, index and trigger name in this template is deterministic
and derived from the concrete model, using Django's `%(class)s`
interpolation for constraints and indexes:

- Indexes: `idx_%(class)s_<column>` (`idx_apiuser_isactive`).
- Unique constraints: `unq_%(class)s_<column(s)>` (`unq_apiusergroups_apiuser_group`).
- Check constraints: `chk_%(class)s_<what>` (`chk_verificationcode_lifetime`).
- GIN indexes: `gin_%(class)s_<column>` (`gin_apiuser_username`).
- Triggers: `trg_<lowercase model name>_<what>` (`trg_apiusertotpdevice_readonly`,
  `trg_verificationcode_protect_settled`) — triggers cannot use `%(class)s`
  since they are declared on `pgtrigger.Trigger` objects, not Django's
  constraint/index machinery, so the model name is spelled out by hand,
  lowercase and without underscores.

The payoff is that a database error message or a `\d` in `psql` tells you
which model and which rule without cross-referencing migrations.

## `track_table`: history via `pghistory`

`api_utils.db.track_table` is a decorator, not a base class — it can be
stacked onto a model built on any of the five bases:

```python
def track_table[Table: type[DatabaseModel]](
    exclude: Sequence[str] | None = None,
    meta: dict | None = None,
) -> Callable[[Table], Table]:
    ...
    return track(
        obj_field=None,
        context_field=None,
        context_id_field=None,
        append_only=True,
        exclude=exclude,
        model_name=f"{model.__name__}Event",
        meta=meta,
    )(model)
```

It wraps `pghistory.track` with this template's defaults: the generated event
model is always named `<Model>Event`, always append-only (see
[Decisions](decisions.md) for why history is append-only rather than
mutable audit columns), and always carries five indexes tuned for how the
history is actually queried — a GIN index over `pgh_context` for containment
lookups, a trigram GIN index over the request `url` stashed in that context
(see [`api_middlewares.history`](../concepts/request-lifecycle.md)), a plain
index on the `user.id` key inside that context, and indexes on
`pgh_created_at` and `pgh_label`. `exclude` is how a model keeps a secret out
of its own history — `ApiUserTotpDevice` excludes `secret`,
`VerificationCode` excludes `token_hash` — so a compromised history table
does not also leak what it was protecting. The event model itself
(`api_core.models.event.ApiEvent`) mirrors `ApiModel`'s uuid7 primary key
convention onto `pghistory`'s own event row.
