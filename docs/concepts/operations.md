---
icon: lucide/layers
---

# Operations

A controller never touches the ORM directly. It hands a validated schema to an
**operation**, and the operation is the only thing in the request path that
runs a query with side effects. That separation is what lets the same
controller family serve a flat resource, a foreign-key resource, a scoped
sub-resource and a many-to-many relation — only the operation class changes.

## The `ModelOperation` contract

Every operation in `api_core.services.operations` is a `ModelOperation[Get]`:

```python
class ModelOperation[Get: DTO](ABC):
    __slots__ = ("fields", "mapper", "qs", "schema")

    scope: ClassVar[RequestScopes] = RequestScopes.BODY

    def dump(self, dto: DTO) -> dict:
        return dto.model_dump()

    @abstractmethod
    async def execute(self, *args, **kwargs): ...

    def map(self, obj: DatabaseModel) -> Get:
        return self.mapper(obj, self.schema)

    @abstractmethod
    async def run(self, *args, **kwargs): ...
```

Four methods, three of them fixed by the family and one the framework calls:

- **`dump`** turns a validated input schema into the `dict` a query needs.
  The base implementation is a plain `model_dump()`; `UpdateOperation`
  overrides it to `model_dump(exclude_unset=True)` when the operation is
  partial, so a `PATCH` never overwrites a field the client did not send —
  see [Schemas → write schemas](schemas.md) for why that field is `None` by
  default rather than absent.
- **`execute`** is the one method every concrete leaf operation implements —
  it is where the actual `QuerySet` call lives (`acreate`, `aupdate`, a raw
  `pgbulk` call, an `M2M.add()`). It is also the one method a custom
  operation almost always overrides.
- **`map`** hands a Django model instance and the operation's `schema` to a
  `ModelMapper` (`api_core.services.mappers.instance_mapper` by default),
  which validates the schema `from_attributes=True` off the instance and
  resolves any many-to-many field into a nested tuple of `Get` schemas along
  the way.
- **`run`** is what the controller actually calls. It is defined once per
  _shape_ (create, retrieve, update, destroy — in `base.py`) and is **not**
  meant to be overridden: it owns error translation (`exc_handler`, below)
  and the call order of `dump` → `execute` → `map`. A custom operation
  overrides `execute`, not `run`.

`ModelOperation.exc_handler` is a context manager every `run` wraps its
database call in:

```python
@classmethod
@contextmanager
def exc_handler(cls, lookup: dict | None = None) -> Iterator[None]:
    try:
        yield
    except IntegrityError as i:
        raise ConflictError.from_integrity_error(i).scoped(cls.scope) from i
    except ObjectDoesNotExist as o:
        raise NotFoundError(field_errors=lookup).scoped(RequestScopes.PATH) from o
```

This is the single place a Postgres `IntegrityError` becomes a `409` and a
missing row becomes a `404` — see [Errors](errors.md) for how `ApiError`
subclasses carry their status code and field errors, and
[Database](database.md) for the constraints that raise the `IntegrityError`
in the first place.

## Flat operations

`FlatCreateOperation`, `FlatRetrieveOperation`, `FlatUpdateOperation` and
`FlatDestroyOperation` are the plain case: one table, no relations to
resolve. `FlatCreateOperation.execute` is `await self.qs.acreate(**data)`
followed by a re-fetch by `pk` (so the returned object carries whatever a
trigger or `db_default` computed); `FlatUpdateOperation.execute` is an
`aupdate(**data)` filtered by the path lookup, raising `NotFoundError` itself
if zero rows matched (an `aupdate` that touches nothing does not raise on its
own). `FlatDestroyOperation.execute` is worth reading closely:

```python
async def execute(self, lookup: dict) -> int:
    target = self.qs.prefetch_related(None).select_related(None).filter(**lookup)
    deleted, _ = await target.adelete()

    if deleted:
        return deleted

    # a soft delete trigger rewrites the statement into an update,
    # so postgres reports no deleted rows for a row that did exist
    return int(await target.aexists())
```

Against an [`ApiSoftDeleteModel`](models.md), the `DELETE` a client asked for
is rewritten by a Postgres trigger into `UPDATE ... SET is_active = false`,
so Django's own row count comes back `0` even though the row was found and
handled — the fallback `exists()` check is what tells `DestroyOperation.run`
whether to raise `404` or return `204`.

`ForeignKeyCreateOperation` and `ForeignKeyUpdateOperation` extend the flat
pair for schemas whose relations are sent as bare ids (see
[Schemas](schemas.md)): they run
`api_core.services.relations.resolve_fk_attnames` over the payload first,
rewriting `{"parent": uuid}` into `{"parent_id": uuid}` so a bare
`create`/`update` call accepts it, then defer to the flat implementation.

## Scoped create

`ScopedCreateOperation` extends `ForeignKeyCreateOperation` with one addition:
a `defaults` dict, merged into the payload _after_ the client's data:

```python
async def execute(self, data: dict) -> DatabaseModel:
    return await super().execute(data | self.defaults)
```

The parent id in `defaults` comes from the url path, resolved by the
controller before the operation ever runs — a client cannot put a different
parent id in the body and have it win, because `data | self.defaults` puts
`defaults` last. This is the mechanism behind
[sub-resource isolation](../guides/sub-resources.md): the path, not the body,
decides which parent a child belongs to.

## Nested and many-to-many operations

`NestedCreateOperation`/`NestedUpdateOperation` and
`ManyToManyCreateOperation`/`ManyToManyUpdateOperation` both split the
payload in two — the flat fields go straight to `qs.create`/`qs.filter().update`,
and the relation fields (found via `ctrl.resolver.nested_names` or
`ctrl.resolver.m2m_names`, from `api_core.services.relations.RelationResolver`)
are handled separately, inside the same `pgtransaction`-wrapped function:

- **Many-to-many** (`m2m.py`) validates that every id sent actually exists
  (`validate_existing_ids`, one query per relation, raising a `400` naming
  the missing id) before touching the join table, then either `.set()`s or
  `.add()`s depending on whether the operation is an overwriting `PUT` or an
  additive `PATCH` (`overwrite`, threaded from
  `PutManyToManyQuery`/`PatchManyToManyQuery` — see
  [Schemas → query.py](schemas.md)).
- **Nested** (`nested.py`, one-to-one and reverse foreign key relations)
  writes children after the parent exists, and on update either creates
  (`write_child`/`write_collection`, `replace=False`) or replaces
  (`replace=True`, deleting first for a collection, `pgbulk.upsert` for a
  singular child) depending on whether the parent was being created or
  updated. A collection of 32 or more items (`COPY_THRESHOLD`) is written
  with `pgbulk.copy` instead of `bulk_create`, when the child model's fields
  allow it (`supports_copy` — no `db_default` without a matching Python
  `default`, since a `COPY` bypasses column defaults entirely).

Both call `set_immediate_constraints()` before writing (see
[Database](database.md)) and both run inside `pgtransaction.atomic` with
`RETRIES` (3) automatic retries — nested and many-to-many writes are the
operations most likely to race with a concurrent update to the same parent,
which is also why `exec_m2m_update` and `exec_nested_update` take the
`REPEATABLE_READ` isolation level and lock the parent row with
`lock_instance` (`api_core.services.locks`, `SELECT ... FOR NO KEY UPDATE`
with a 5-second timeout, turned into a `409 (LOCKED)` rather than hanging)
before reading it back.

## Link operations

`LinkAttachOperation`, `LinkDetachOperation` and `LinkInspectOperation`
operate on the _through_ row of a many-to-many relation directly, addressed
by both ends of the relation (`RelatedInstancePath`, see
[Schemas → path schemas](schemas.md)). Their `build_lookup` turns the two
path segments into `{"parent_id": ..., "related_id": ...}`; on a conflict or
missing row, `find_missing` queries each side independently to say _which_
id does not exist, rather than a generic "not found". `FlatLinkAttachOperation`
uses `aget_or_create` (attaching twice is not an error — it returns the
existing row); `FlatLinkDetachOperation` deletes by that lookup; and
`FlatLinkInspectOperation` is a plain `aget` — this is the operation family
behind the _link_ controllers in [Controllers](controllers.md).

## Integrity errors and the transaction boundary

A flat create or update runs inside whatever transaction Django's request
handling already provides and relies on `exc_handler` to catch the
`IntegrityError` a constraint violation raises. Nested and many-to-many
writes are more deliberate about it: `exec_nested_post`, `exec_nested_update`,
`exec_m2m_post` and `exec_m2m_update` are each wrapped in
`pgtransaction.atomic` explicitly, so that a parent write and every child
write it triggers commit or roll back together — a child conflict after the
parent was created rolls the parent back too, rather than leaving an
orphaned parent row. `scope_child_conflict` in `nested.py` goes one step
further: on a bulk write, it re-plays the conflicting batch one row at a
time (`probe_conflict_index`) to find _which_ item in the list caused the
`IntegrityError`, so the `409` response's field error names the offending
index instead of just the field.

## Writing your own operation

Subclass the leaf that matches the write shape you need
(`FlatCreateOperation`, `ForeignKeyUpdateOperation`, and so on) and override
`execute` — that is almost always the only method to touch. Do not override
`run`: it is what wires `dump`, `execute`, `map` and `exc_handler` together
consistently across every operation family, and a controller's default
operation resolution (see [Controllers](controllers.md)) expects that
contract to hold. Override `dump` only if the input needs transforming
before it becomes a `dict` at all (the base and `UpdateOperation` versions
already cover `model_dump()` and the partial-update case). If the new
operation needs extra constructor arguments — the way `ScopedCreateOperation`
needs `defaults` or `LinkOperation` needs `parent`/`related` — extend
`__init__`, call `super().__init__(*fields, mapper=mapper, schema=schema, qs=qs)`
first, and remember to declare `__slots__` for the new attributes, matching
every existing operation in the module.
