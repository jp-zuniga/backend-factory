---
icon: lucide/waypoints
---

# Controllers

A controller is a `dmr.Controller` subclass: a class whose methods
(`get`, `post`, `put`, `patch`, `delete`) become HTTP method handlers, wired up
automatically at class-creation time. `api_core.controllers` adds one base and
a family of generics on top so that most controllers in this codebase declare
type parameters and a handful of class attributes, never a method body.

## `BaseController`

```python
class BaseController[Serializer: BaseSerializer](
    HandleNotAllowedMixin,
    Controller[Serializer],
):
```

Every controller in the project — including ones with no model behind them,
like `RootController` or `CsrfController` — ultimately subclasses this.
It fixes, for the whole application:

- **`auth`** — both authentication flavours at once, in order:
  `JwtCookieAsyncAuth` (browsers), then `JwtHeaderAsyncAuth` (native clients).
  See [Authentication](../api/authentication.md).
- **`throttling`** — the three-tier default (10/s, 100/min, 1000/h) from
  `build_throttle`, keyed on the caller's address.
- **`parsers` / `renderers`** — `MsgspecJsonParser` / `MsgspecJsonRenderer`
  only; this API speaks JSON.
- **`error_model`** — `ApiErrorResponse` (see [Errors](errors.md)), so `dmr`
  knows what shape an error payload takes when it builds the OpenAPI spec.
- **`endpoint_cls`** — `PathOperationIdEndpoint`, which derives OpenAPI
  operation ids from the url instead of requiring one per method (see
  [OpenAPI](openapi.md)).

It also mixes in `HandleNotAllowedMixin`, so a `405` from any controller in
this project carries the same body as every other error, not `dmr`'s default.

## `ModelController` and its type parameters

`ModelController[Serializer, Model, Get]` is what every CRUD controller
actually inherits from. It resolves its type parameters into class attributes
— `model`, `schema` — at `__init_subclass__` time via `resolve_type_args`, so
a declaration like:

```python
class WidgetDetailController(
    ModelDetailController[
        CustomPydanticFastSerializer,
        Widget,
        WidgetGet,
        WidgetPut,
        WidgetPatch,
    ],
): ...
```

needs no body at all — `model = Widget` and `schema = WidgetGet` are set for
you from the generic arguments. The same `__init_subclass__` also validates
any operation overrides: if you assign `create_operation = SomethingElse`,
it must subclass the expected operation base (`CreateOperation`, etc, from
`OPERATIONS` in `api_core/controllers/models/base.py`) and must not be
abstract, or class creation raises `TypeError` immediately — see
[misdeclaration errors](#misdeclaration-errors) below.

`ModelController` also provides:

- **`resolver`** / **`qs`** (cached properties) — the queryset for this
  request, built through `RelationResolver` (see [Operations](operations.md)
  and [Schemas](schemas.md) for how nested/related fields turn into `select_related`/`prefetch_related`).
- **`build_operation(operation_cls, **kwargs)`** — constructs an operation
instance with `mapper`, `schema`and`qs`already filled in from the
controller. Every controller method is, in the end, a call to`build_operation(...).run(...)`.

## The CRUD family

All declared in `api_core/controllers/models/detail.py` and `list.py`, all
generic over `ModelController`:

| Controller                        | Methods                      | Use it for                                                                                                                                                                                 |
| --------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ModelDetailController`           | `GET` `PUT` `PATCH` `DELETE` | a fully editable, deletable row                                                                                                                                                            |
| `ModelReadUpdateDetailController` | `GET` `PUT` `PATCH`          | a row that can change but never be deleted                                                                                                                                                 |
| `ModelReadOnlyDetailController`   | `GET`                        | a row clients may only read                                                                                                                                                                |
| `ModelListController`             | `GET` `POST`                 | a paginated collection, creatable                                                                                                                                                          |
| `ModelListAllController`          | `GET`                        | the same rows, unpaginated (`/all`); refuses to expose any nested many-to-many field — see [Schemas](schemas.md#many-to-many) — because that would mean unpaginated nested collections too |
| `ModelReadOnlyListController`     | `GET`                        | a paginated collection, read-only                                                                                                                                                          |

Pick the detail/list pair that matches what the underlying [model base](models.md)
actually allows — pairing e.g. `ApiSoftDeleteModel` with `ModelDetailController`
means `DELETE` reaches an operation that flips `is_active`, not a real row
deletion. [Choosing a base model](../guides/base-models.md) has the full
pairing table.

## The relation family

- **`ModelNestedDetailController` / `ModelNestedListController`** — same CRUD
  surface, but writes go through `NestedUpdateOperation` / `NestedCreateOperation`,
  which accept nested object bodies for related rows instead of bare ids.
- **`ModelManyToManyDetailController` / `ModelManyToManyListController`** —
  writes go through `ManyToManyUpdateOperation` / `ManyToManyCreateOperation`.
  The detail controller's `put`/`patch` additionally accept an `overwrite`
  query flag (`PutManyToManyQuery` / `PatchManyToManyQuery`, parsed as
  `StrictQuery`) controlling whether the write replaces or merges the m2m set.
- **`ModelRelationController`** — a `ModelManyToManyDetailController` with
  `delete` removed and `put`/`patch` pinned to `overwrite=True` /
  `overwrite=False` respectively; the shape used for a related-collection
  sub-endpoint like `/users/{id}/groups/`.
- **`ModelLinkController`** — not a CRUD controller at all: `GET` inspects
  whether a specific `related` row is linked to a specific `parent` row,
  `PUT` attaches it, `DELETE` detaches it (all `204` except `GET`). Declares
  `parent`, `related` and `relation` as the three field names involved, and
  derives `parent_model()` / `related_model()` from them via
  `model._meta.get_field(...)`. Default permissions are `view`/`add`/`delete`
  on the _relation_, from `api_auth.services.permissions`. Used for endpoints
  like `/users/{id}/groups/{related}/`.

## The scoped family

`ScopedDetailController`, `ScopedListController` and `ScopedReadOnlyListController`
(`api_core/controllers/models/scoped.py`) mix `ParentScopedMixin` into the
corresponding non-scoped controller, for sub-resources like
`/parents/{parent_id}/children/`:

- `ParentScopedMixin.parent_field` names the FK to the parent; everything else
  — the url parameter, the path schema field, the queryset filter — is derived
  from it via `collect_fk_attnames`, so the three can never drift apart (see
  [Sub-resources](../guides/sub-resources.md)).
- `build_qs` is overridden to filter by `{parent_field: self.parent_id}`, so a
  row filed under a different parent is invisible — it answers `404`, exactly
  like a row that doesn't exist.
- `ScopedListController.post` passes `defaults={parent_param(): parent_id}` to
  its (`ScopedCreateOperation`) create operation, so the parent is taken from
  the path and can never be overridden from the request body.
- `ScopedDetailController` uses `ForeignKeyUpdateOperation` as its update
  operation, since a scoped detail row's parent FK is fixed by the url, not by
  the body.

## Mixins

From `api_core/controllers/mixins.py`:

- **`PublicControllerMixin`** — sets `auth = None`, opening a controller to
  unauthenticated clients (still subject to throttling).
- **`StrictThrottlingMixin`** — replaces the default three-tier throttle with
  a single 10/minute limit, for endpoints worth rate-limiting harder (login,
  password reset, and similar).
- **`OpenReadMixin` / `OpenCreateMixin` / `ReadOnlyMixin`** — permission
  presets built on top of `DEFAULT_PERMISSIONS`; see
  [Permissions](../guides/permissions.md) for what each expands to.
- **`DefaultOrderMixin`** — orders the queryset by `pk`, for controllers that
  don't otherwise need a specific order.
- **`HandleNotAllowedMixin`** — the `405` override every `BaseController`
  already gets; listed separately here because it's a `QuerySetProvider`/`HandleNotAllowedProvider`-style
  mixin, not model-specific.
- **`ParentScopedMixin`** — described above, under the scoped family.

## Misdeclaration errors

`ModelController.__init_subclass__` raises `TypeError` — in Spanish, matching
the rest of this API's user-facing text (see [Decisions](decisions.md)) — in
three cases:

1. An operation override (`create_operation`, `update_operation`, ...) that
   doesn't subclass the operation type it's replacing.
2. An operation override that's still abstract (missing an
   `__abstractmethods__` implementation).
3. A concrete (non-abstract) controller that doesn't resolve every attribute
   `ModelController` expects (`model`, `schema`, and whatever else the
   specific family requires) — this is what catches a controller declared
   with the wrong number or order of type parameters.

`ParentScopedMixin.parent_param()` raises a similar `TypeError` if
`parent_field` doesn't name an actual foreign key on `model`. All three fail
at import time (class-body execution), not at request time — a misdeclared
controller breaks `manage.py check`, not a client's request.
