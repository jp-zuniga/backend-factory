---
icon: lucide/route
---

# Routing

A controller class carries almost everything a url needs — its model, its
family, its parent relation — so `api_core.controllers.routers` derives the
url instead of asking you to write one.

## `route_controllers` and per-family inference

```python
route_controllers(*ctrls, prefix="")
```

calls `route_inferred_controller` for each controller, which switches on the
controller's family (checked with `issubclass`, most specific first):

1. **`ParentScopedMixin`** subclasses → `route_scoped_controller` (see
   [below](#route_scoped_controller)).
2. **Detail controllers** (`ModelDetailController`, `ModelReadOnlyDetailController`,
   `ModelReadUpdateDetailController`) → an endpoint at the model's resource
   name plus an instance parameter, url name suffixed `detail`.
3. **`ModelListAllController`** → the same resource name plus a literal `all`
   segment.
4. **List controllers** (`ModelListController`, `ModelReadOnlyListController`)
   → the resource name with no instance parameter, url name suffixed `list`.
5. **Anything else** (`RootController`, `CsrfController`, and other
   non-model controllers) → `get_controller_endpoint`, which strips the
   `variant` prefix and `Controller` suffix off the class name and
   kebab-cases what's left (e.g. `WebLoginController` with `variant = "Web"`
   becomes `login`).

A model controller's resource name comes from `get_model_endpoint`: the
model's class name with its `Api` prefix stripped, kebab-cased
(`ApiUser` → `user`).

## What each url looks like

`route_controller` assembles the final pattern from these pieces:

| Shape | Pattern | Produced for |
| --- | --- | --- |
| Collection | `<prefix>/<resource>/` | list controllers |
| Instance | `<prefix>/<resource>/<pk:id>/` | detail controllers |
| Sub-resource collection | `<prefix>/<parent>/<pk:parent_id>/<child>/` | `ScopedListController` |
| Sub-resource instance | `<prefix>/<parent>/<pk:parent_id>/<child>/<pk:id>/` | `ScopedDetailController` |
| Link | `<prefix>/<parent>/<pk:id>/<relation>/<pk:related>/` | `ModelLinkController` |

`<pk:...>` is typed per the model's actual primary key —
`get_pk_type` returns `"uuid"`, `"int"`, or `"str"` by inspecting
`model._meta.pk`, so a url segment always matches the column it looks up.

## `route_scoped_controller`

A scoped controller only declares `parent_field`; routing derives the rest.
`get_parent_model` reads the FK's `related_model` off `model._meta`, so the
parent's own resource name and primary-key type come from the *relation*, not
from anything written on the scoped controller itself:

```python
route_scoped_controller(
    ctrl=ChildDetailController,
    prefix="parents",
)
# → parents/<pk:parent_id>/children/<pk:id>/
```

The child's own path segment (`tail`) defaults to the child model's resource
name, and the url name suffix defaults to `{tail}-{detail,list}` — enough to
keep the name unique even when the same child model is scoped under two
different parents in the same router.

## Url names and disambiguation

Every url name is the route with `/` replaced by `-`
(`join_route(...).replace("/", "-")`), plus an optional `-<suffix>` on top.
The three list/detail/scoped branches above set a default suffix
(`detail`, `list`, `{tail}-detail`/`{tail}-list`) specifically so that a
model exposed through more than one controller — a normal list plus an
`/all` variant, say — doesn't collide on the same url name.

## When to pass `endpoint`, `tail` or `suffix` explicitly

`route_inferred_controller` and `route_scoped_controller` both forward
unrecognized keyword arguments straight to `route_controller`, so you can
override any inferred piece without writing the route by hand:

- **`endpoint`** — when the url segment shouldn't be the model's or
  controller's derived name at all. `api_auth.api` uses this for
  `ApiUserGroupsController`/`ApiUserPermissionsController`, which live under
  `auth/user/{id}/groups/` and `.../permissions/` rather than any name derived
  from a `Group`/`Permission` model.
- **`tail`** — the trailing path segment, when it shouldn't match the (scoped)
  model's own resource name — same example: `tail="groups"`.
- **`suffix`** — an explicit url name suffix, when the derived one would still
  collide (two scoped children with the same tail under different prefixes,
  for instance).

`route_link_controller` is the equivalent entrypoint for `ModelLinkController`s,
and always needs the controller's `parent`/`related`/`relation` attributes
already set — it has no non-link mode.

## Assembling routers per app

Each app builds its own `dmr.routing.Router` in an `api.py` module and lists
every controller it owns. `api_auth.api` is the concrete example:

```python
router: Final[Router] = Router(
    prefix="",
    tags=["auth"],
    urls=sort_urls((
        *route_controllers(
            ApiUserDetailController, ApiUserListController, ...,
            prefix="auth",
        ),
        route_inferred_controller(
            ctrl=ApiUserGroupsController,
            prefix="auth", suffix="groups", tail="groups",
        ),
        route_link_controller(ApiUserGroupsLinkController, "auth"),
        ...
    )),
)
```

`sort_urls` orders patterns by their route string, purely so the generated
list (and the OpenAPI paths built from it) is stable across runs. `api_core.api`
then mounts every app router under the root router:

```python
router: Final[Router] = Router(prefix="")
router.include(api_auth.api.router)   # keeps api_auth's own tags
schema: Final[OpenAPI] = build_schema(router)
```

`Router.include` (as opposed to concatenating `.urls`) is what keeps each
app's `tags` attached to its own operations in the generated OpenAPI document
— see [OpenAPI](openapi.md). Finally, `api_core.urls` hand-writes three paths
(`api-root`, `health/`, `openapi/`) ahead of `*router.urls`, so those three
are never subject to inference at all.

A new domain app follows the same shape: its own `api.py`, its own `Router`,
included into `api_core.api.router` next to `api_auth.api.router`.
