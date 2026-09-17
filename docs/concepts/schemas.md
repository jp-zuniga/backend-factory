---
icon: lucide/ruler
---

# Schemas

Every request and response shape in this template is a
[Pydantic](https://docs.pydantic.dev/) model rooted in `api_core.schemas.base.DTO`. Two things follow from that: the
shapes are declarative (a controller's type parameters _are_ its contract), and
they are strict by default — a schema rejects what it does not recognise rather
than silently dropping it.

## `DTO` and `PermissiveDTO`

```python
class DTO(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        field_title_generator=(lambda s, _: s.lower()),
        from_attributes=True,
        frozen=True,
        str_strip_whitespace=True,
    )


class PermissiveDTO(DTO):
    model_config = ConfigDict(extra="ignore")
```

`DTO` is the strict base every request and response schema ultimately inherits:

- `extra="forbid"` — an unknown field in the payload is a validation error, not
  a silent no-op.
- `frozen=True` — once validated, an instance cannot be mutated. A controller
  or operation that wants a changed payload builds a new one.
- `str_strip_whitespace=True` and `allow_inf_nan=False` close off two classes
  of input that look valid but are not: padded strings, and `NaN`/`Infinity`
  sneaking in through a numeric field.
- `from_attributes=True` is what lets a schema validate directly off a Django
  model instance (see [Operations → the `map` step](operations.md)), not just
  off a `dict`.

`PermissiveDTO` only relaxes `extra` to `"ignore"`. It exists for the one case
where forbidding unknown fields is actively wrong: reading cookies. A browser
sends every cookie it holds on the domain, not just the ones the API set, so
`api_auth.schemas.session.SessionCookies` extends `PermissiveDTO` — otherwise
an unrelated cookie in the request would fail validation for a request that
never even looks at it. There is no third, intermediate tier in the current
codebase; a schema is either fully strict or ignores unknown input, and the
choice is made per schema, not per field.

## Read schemas

`api_core.schemas.get.BaseGet` is the root of every response schema:

```python
type PrimaryKey = UUID | PositiveInt


class BaseGet[PK: PrimaryKey = UUID](DTO):
    id: PK
```

It is generic over the primary key type, defaulting to `UUID` since that is
what [`ApiModel`](models.md) uses; a model keyed by a `PositiveInt` (a Django
`Group` or `Permission`, which this template does not own) parameterises it
explicitly — see `GroupInlineGet(BaseGet[PositiveInt])` in `api_auth`.

The **inline vs. full** split shows up as separate classes rather than a
single schema with optional fields. `api_auth.schemas.user`:

```python
class ApiUserInlineGet(BaseGet):
    is_active: bool
    first_name: str
    last_name: str
    username: str
    email: str
    email_verified_at: datetime


class ApiUserGroupsGet(BaseGet):
    groups: tuple[GroupInlineGet, ...]


class ApiUserPermissionsGet(BaseGet):
    permissions: tuple[PermissionGet, ...]


class ApiUserGet(ApiUserGroupsGet, ApiUserPermissionsGet, ApiUserInlineGet):
    pass
```

`ApiUserInlineGet` is what a _related_ object embeds — the fields of a user
another schema nests, with no relations of its own. `ApiUserGet` is what the
user's own detail endpoint returns, adding the nested `groups` and
`permissions`. The nesting is not free: `api_core.services.relations`
inspects a schema's annotations to decide what a queryset must
`select_related` or `prefetch_related` before it can be mapped —
`RelationResolver.fk_paths` walks nested `DTO` fields for `select_related`,
and `RelationResolver.m2m_names` finds list-of-`BaseGet` fields for
`prefetch_related`, recursing up to `MAX_PREFETCH_DEPTH` (3) so an inline
schema never triggers unbounded joins by accident. In short: every extra
level of nesting in a `Get` schema is an extra join or an extra prefetch
query at read time, so keep inline schemas inline (no relations on relations)
unless the depth is deliberate.

## Write schemas and the `build_put_schema` / `build_patch_schema` factories

A resource is hand-written as a `Post` (or `Write`) schema — the shape a
`201 Created` accepts — and `PUT`/`PATCH` are _derived_ from it rather than
written by hand:

```python
def build_put_schema[Post: type[DTO]](dto: Post) -> Post:
    return create_model(
        dto.__name__.replace("Post", "Put").replace("Write", "Put"),
        __base__=dto,
    )


def build_patch_schema[Put: type[DTO]](dto: Put) -> Put:
    kwargs = {"__base__": dto} | {
        name: (
            field.annotation
            if not field.metadata
            else Annotated[field.annotation, *field.metadata],
            None,
        )
        for name, field in dto.model_fields.items()
    }

    return create_model(dto.__name__.replace("Put", "Patch"), **kwargs)
```

`build_put_schema` renames the class (`GroupPost` → `GroupPut`,
`ApiUserWrite` → `ApiUserPut`) and otherwise reuses the post schema exactly —
a `PUT` in this template means "send the full representation again",
including required fields. `build_patch_schema` takes that `Put` schema and
rebuilds every field with the same type and validators but a default of
`None`, so a `PATCH` body only has to carry the fields it actually changes;
`UpdateOperation.dump` (see [Operations](operations.md)) then calls
`model_dump(exclude_unset=True)` so an omitted field is never confused with
one explicitly cleared. `api_auth.schemas.group`:

```python
class GroupPost(DTO):
    name: Annotated[str, StringConstraints(max_length=150, min_length=1)]
    permissions: list[PositiveInt] | None = None


GroupPut = build_put_schema(GroupPost)
GroupPatch = build_patch_schema(GroupPut)
```

Three classes, one written by hand.

## Wire types

A strict `DTO` does not coerce anything Pydantic wouldn't coerce on its own,
which means a handful of small, purpose-built pieces exist to keep validation
strict _and_ forgiving of how a client actually sends data:

- `api_core.schemas.validators` defines `coerce_date`, `coerce_datetime` and
  `coerce_uuid` — each takes whatever the client sent, and if it is a string,
  tries to parse it as the target type; anything that fails, or that was
  never a string, is handed back untouched so the field's own validator
  produces the error message. These are the building blocks for a wire type:
  wrap the target type in `Annotated[..., BeforeValidator(coerce_date)]` and
  a date field accepts an ISO string the same way Pydantic already accepts
  one for plain, non-strict models.
- `empty_or_email` and `empty_or_url` are the same idea applied to optional
  fields that are either blank or a valid value — `ApiUserBaseWrite.email`
  is typed `Email = ""`, and `empty_or_email` is what lets `""` and a real
  address both pass while a malformed one still fails, with a Spanish message
  (see [Decisions](decisions.md)).
- Relations are not typed as nested objects on write — they are typed as the
  target's bare primary key. `GroupPost.permissions: list[PositiveInt] | None`
  and `ApiUserGroupsWrite.groups: list[PositiveInt] | None` are both "send the
  ids, not the objects"; `api_core.services.relations.resolve_fk_attnames`
  and the `ForeignKey*Operation` classes (see [Operations](operations.md)) are
  what turn a bare id back into a column the ORM accepts. This is the
  mechanism the outline elsewhere calls a "related id" field: there is no
  separate named type for it, just a plain `PositiveInt` or `UUID` annotation
  on the field the relation actually is.

If a project needs a genuinely new wire type — a phone number, a currency
amount — the pattern to follow is `coerce_date`: a small function that either
returns a parsed value or hands the input back unchanged, wrapped in
`Annotated[Target, BeforeValidator(...)]` next to the other types in
`api_auth.schemas.types` (or an equivalent module in a new app).

## Path schemas

`api_core.schemas.path` builds the schemas a controller uses to parse url
parameters, on top of `BaseGet`:

```python
type InstancePath = IntInstancePath | UuidInstancePath


class RelatedPath[PK: PrimaryKey = UUID, RelatedPK: PrimaryKey = PositiveInt](
    BaseGet[PK]
):
    related: RelatedPK
```

`IntInstancePath` and `UuidInstancePath` are the two shapes a detail
endpoint's `{id}` segment parses into, depending on the primary key type.
`RelatedPath` (and its `UuidToIntRelatedPath` / `UuidToUuidRelatedPath`
aliases) is the shape a link endpoint's `{id}/{related}` parses into — see
[Controllers](controllers.md) for the relation family that consumes it.

Sub-resources use `build_scoped_path` instead of a hand-written path schema:

```python
def build_scoped_path(
    model: type[DatabaseModel],
    parent_field: str,
    *,
    base: type[InstancePath] = UuidInstancePath,
) -> type[InstancePath]:
    field = model._meta.get_field(parent_field)
    hint = UUID if isinstance(field.target_field, UUIDField) else PositiveInt
    parent = parent_field.replace("_", " ").title().replace(" ", "")

    return create_model(
        f"{model.__name__}{parent}Path",
        __base__=base,
        **{field.attname: (hint, ...)},
    )
```

It reads the _actual_ Django field behind `parent_field` to decide whether the
parent's key parses as a `UUID` or a `PositiveInt`, and names the generated
class after the model and the relation (`CommentPostPath`, for a `Comment`
scoped under `post`). See [Sub-resources](../guides/sub-resources.md) for the
guide-level walkthrough.

## Filter and pagination queries

`api_core.schemas.filters.FilterQuery` is an abstract `DTO` with one method,
`get_filters()`, that turns validated query parameters into the `dict` a
`django-filter` `FilterSet` accepts. `PaginatedFilterQuery` combines it with
`PageQuery` (`page`, `page_size`, capped at 100) and excludes the pagination
fields from `get_filters()`; `UnpaginatedFilterQuery` is the same without
pagination, for the `/all` variants (see [Conventions](../api/conventions.md)).

Both are base classes for `build_filter_query`, which turns an existing
`django-filter` `FilterSet` into a query schema instead of asking anyone to
redeclare its fields:

```python
ApiUserFilterQuery = build_filter_query(PaginatedFilterQuery, ApiUserFilterSet)
ApiUserFilterAllQuery = build_filter_query(UnpaginatedFilterQuery, ApiUserFilterSet)
```

It walks `FilterSet.base_filters`, maps each `django-filter` field type to a
Python type (`BooleanFilter` → `bool`, `UUIDFilter` → `UUID`, a range filter
into a `_before`/`_after` or `_min`/`_max` pair, and so on), and raises
`TypeError` at import time for filter types it does not consider meaningful
in a REST query string (`MultipleChoiceFilter`, `AllValuesFilter`, and a few
others). The `exclusive` and `inclusive` keyword arguments attach
`model_validator`s that reject or require pairs of parameters together — see
the function for the exact Spanish messages they raise. Because this all
happens once, at import time, a mistake in a filterset surfaces immediately
rather than at request time.

## When to hand-write instead of generating

The factories exist to keep a write schema, its `PUT`/`PATCH` variants, and
its filter query in lock-step with the fields actually declared once, on the
`Post` schema or the `FilterSet`. Hand-write a schema instead when the shape
you need does not correspond to a generated variant at all: a schema for
cookies (`PermissiveDTO`), a schema that combines fields from more than one
model in ways a single `FilterSet` cannot express, or a response schema for
an endpoint that is not a plain resource read (a login response, a two-factor
challenge). If you find yourself hand-writing a `PUT` or `PATCH` schema that
happens to mirror its `Post` schema field-for-field, that is a sign to reach
for `build_put_schema`/`build_patch_schema` instead.
