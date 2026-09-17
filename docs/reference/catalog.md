---
icon: lucide/list
---

# Catalog

Everything the template ships, one table per family. `Serializer` is elided
from every type-parameter list below — every controller in this project is
parameterized with `CustomPydanticFastSerializer`. See [Controllers](../concepts/controllers.md),
[Operations](../concepts/operations.md), [Models](../concepts/models.md) and
[Schemas](../concepts/schemas.md) for what these families mean and how they
compose.

## Controllers

Concrete controllers actually routed by the template (`api_auth/controllers/`), plus the two public ones `api_core` ships directly (`RootController`, `HealthCheckController`). "Methods" excludes `OPTIONS`/`HEAD`, which every controller answers.

| Controller                         | Methods                         | Type parameters                                                                                        | Default operations                                                                                     |
| ---------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `RootController`                   | `GET`                           | —                                                                                                      | — (returns API title/version/description)                                                              |
| `HealthCheckController`            | `GET`                           | —                                                                                                      | — (probes cache, database, storage)                                                                    |
| `CsrfController`                   | `GET`                           | —                                                                                                      | — (hands back a CSRF header, no body)                                                                  |
| `EmailConfirmController`           | `POST`                          | —                                                                                                      | — (calls `confirm_email`)                                                                              |
| `EmailResendController`            | `POST`                          | —                                                                                                      | — (calls `resend_verification`)                                                                        |
| `RegisterController`               | `POST`                          | `ApiUser, ApiUserGet`                                                                                  | create → `UserCreateOperation`                                                                         |
| `ProfileController`                | `GET`                           | `ApiUser, ApiUserGet`                                                                                  | retrieve → `FlatRetrieveOperation`                                                                     |
| `MobileLoginController`            | `POST`                          | `MobileLoginPost`                                                                                      | — (`dmr` `ObtainTokensAsyncController`)                                                                |
| `WebLoginController`               | `POST`                          | `WebLoginPost, WebLoginResponse`                                                                       | — (`dmr` `CookieObtainTokensAsyncController`)                                                          |
| `MobileLogoutController`           | `POST`                          | —                                                                                                      | — (calls `close_session`)                                                                              |
| `WebLogoutController`              | `POST`                          | —                                                                                                      | — (`dmr` `CookieLogoutAsyncController`)                                                                |
| `MobileRefreshController`          | `POST`                          | `MobileRefreshPost, MobileRefreshResponse`                                                             | — (`dmr` `RefreshTokenAsyncController`)                                                                |
| `WebRefreshController`             | `POST`                          | —                                                                                                      | — (`dmr` `CookieRefreshTokensAsyncController`)                                                         |
| `MobileVerifyController`           | `POST`                          | `MobileVerifyPost`                                                                                     | — (`dmr` `VerifyTokenAsyncController`)                                                                 |
| `WebVerifyController`              | `POST`                          | —                                                                                                      | — (calls `inspect_session`)                                                                            |
| `MobileTwoFactorController`        | `POST`                          | —                                                                                                      | — (calls `resolve_challenge`)                                                                          |
| `WebTwoFactorController`           | `POST`                          | —                                                                                                      | — (calls `resolve_challenge`, hand-written cookies)                                                    |
| `TwoFactorController`              | `GET`                           | —                                                                                                      | — (reports enrollment status)                                                                          |
| `TwoFactorSetupController`         | `POST`                          | —                                                                                                      | — (calls `start_enrollment`)                                                                           |
| `TwoFactorConfirmController`       | `POST`                          | —                                                                                                      | — (calls `confirm_enrollment`)                                                                         |
| `TwoFactorRecoveryController`      | `POST`                          | —                                                                                                      | — (calls `rotate_recovery_codes`)                                                                      |
| `TwoFactorDisableController`       | `POST`                          | —                                                                                                      | — (calls `disable_two_factor`)                                                                         |
| `ApiUserDetailController`          | `GET`, `PUT`, `PATCH`, `DELETE` | `ApiUser, ApiUserGet, ApiUserPut, ApiUserPatch`                                                        | retrieve/update/destroy → `FlatRetrieveOperation`/`FlatUpdateOperation`/`FlatDestroyOperation`         |
| `ApiUserListController`            | `GET`, `POST`                   | `ApiUser, ApiUserFilterSet, ApiUserFilterQuery, ApiUserGet, ApiStaffPost, Paginated[ApiUserGet]`       | create → `UserCreateOperation`                                                                         |
| `ApiUserListAllController`         | `GET`                           | `ApiUser, ApiUserFilterSet, ApiUserFilterAllQuery, ApiUserInlineGet, list[ApiUserInlineGet]`           | —                                                                                                      |
| `ApiUserGroupsController`          | `GET`, `PUT`, `PATCH`           | `ApiUser, ApiUserGroupsGet, ApiUserGroupsPut, ApiUserGroupsPatch`                                      | retrieve/update → `FlatRetrieveOperation`/`ManyToManyUpdateOperation`                                  |
| `ApiUserGroupsLinkController`      | `GET`, `PUT`, `DELETE`          | `ApiUserGroups, ApiUserGroupsLinkGet, UuidToIntRelatedPath`                                            | attach/detach/inspect → `FlatLinkAttachOperation`/`FlatLinkDetachOperation`/`FlatLinkInspectOperation` |
| `ApiUserPermissionsController`     | `GET`, `PUT`, `PATCH`           | `ApiUser, ApiUserPermissionsGet, ApiUserPermissionsPut, ApiUserPermissionsPatch`                       | retrieve/update → `FlatRetrieveOperation`/`ManyToManyUpdateOperation`                                  |
| `ApiUserPermissionsLinkController` | `GET`, `PUT`, `DELETE`          | `ApiUserPermissions, ApiUserPermissionsLinkGet, UuidToIntRelatedPath`                                  | attach/detach/inspect → `Flat*` link operations                                                        |
| `GroupDetailController`            | `GET`, `PUT`, `PATCH`, `DELETE` | `Group, GroupGet, GroupPut, GroupPatch, IntInstancePath`                                               | retrieve/update/destroy → `FlatRetrieveOperation`/`ManyToManyUpdateOperation`/`FlatDestroyOperation`   |
| `GroupListController`              | `GET`, `POST`                   | `Group, GroupFilterSet, GroupFilterQuery, GroupGet, GroupPost, Paginated[GroupGet]`                    | create → `ManyToManyCreateOperation`                                                                   |
| `GroupListAllController`           | `GET`                           | `Group, GroupFilterSet, GroupFilterAllQuery, GroupInlineGet, list[GroupInlineGet]`                     | —                                                                                                      |
| `PermissionDetailController`       | `GET`                           | `Permission, PermissionGet, DTO, DTO, IntInstancePath`                                                 | retrieve → `FlatRetrieveOperation` (`put`/`patch`/`delete` set to `None`)                              |
| `PermissionListController`         | `GET`                           | `Permission, PermissionFilterSet, PermissionFilterQuery, PermissionGet, DTO, Paginated[PermissionGet]` | — (`post` set to `None`)                                                                               |
| `PermissionListAllController`      | `GET`                           | `Permission, PermissionFilterSet, PermissionFilterAllQuery, PermissionGet, list[PermissionGet]`        | —                                                                                                      |

## Operations

`api_core/services/operations/`. Rows without a "used by default" entry are abstract contracts other operations extend.

| Operation                                                                                | What it writes                                                                     | Used by default in                                                                                                                        |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `ModelOperation`                                                                         | — (the `dump`/`execute`/`run`/`map` contract)                                      | —                                                                                                                                         |
| `CreateOperation` / `DestroyOperation` / `RetrieveOperation` / `UpdateOperation`         | — (per-verb ABCs)                                                                  | —                                                                                                                                         |
| `FlatCreateOperation`                                                                    | A plain insert                                                                     | `ModelListController.create_operation` default                                                                                            |
| `FlatRetrieveOperation`                                                                  | — (select by pk)                                                                   | `ModelDetailController`/`ModelReadOnlyDetailController`/`ModelReadUpdateDetailController.retrieve_operation` default; `ProfileController` |
| `FlatUpdateOperation`                                                                    | A plain update                                                                     | `ModelDetailController`/`ModelReadUpdateDetailController.update_operation` default                                                        |
| `FlatDestroyOperation`                                                                   | A plain delete                                                                     | `ModelDetailController.destroy_operation` default                                                                                         |
| `ForeignKeyCreateOperation`                                                              | An insert accepting related rows as bare ids                                       | base for `ScopedCreateOperation`                                                                                                          |
| `ForeignKeyUpdateOperation`                                                              | An update accepting related rows as bare ids                                       | `ScopedDetailController.update_operation` default                                                                                         |
| `LinkOperation` / `LinkAttachOperation` / `LinkDetachOperation` / `LinkInspectOperation` | — (link ABCs)                                                                      | —                                                                                                                                         |
| `FlatLinkAttachOperation`                                                                | One row of a through table                                                         | `ModelLinkController.attach_operation` default                                                                                            |
| `FlatLinkDetachOperation`                                                                | Deletes one row of a through table                                                 | `ModelLinkController.detach_operation` default                                                                                            |
| `FlatLinkInspectOperation`                                                               | — (reads one row of a through table)                                               | `ModelLinkController.inspect_operation` default                                                                                           |
| `ManyToManyOperation` / `ManyToManyCreateOperation`                                      | Inserts a row plus its m2m sets                                                    | `ModelManyToManyListController.create_operation` default                                                                                  |
| `ManyToManyUpdateOperation`                                                              | Overwrites/merges a row's m2m sets                                                 | `ModelManyToManyDetailController.update_operation` default (and `ModelRelationController`, which inherits it)                             |
| `NestedOperation` / `NestedCreateOperation`                                              | Inserts a row plus owned child rows in the same request                            | `ModelNestedListController.create_operation` default                                                                                      |
| `NestedUpdateOperation`                                                                  | Rewrites a row's owned child rows                                                  | `ModelNestedDetailController.update_operation` default                                                                                    |
| `ScopedCreateOperation`                                                                  | An insert with the parent id forced from the path, not the body                    | `ScopedListController.create_operation` default                                                                                           |
| `UserCreateOperation` (`api_auth.services.user`)                                         | A user row, with password hashing/validation on top of `ManyToManyCreateOperation` | `RegisterController`/`ApiUserListController.create_operation`                                                                             |

## Base models

`api_core/models/base.py`. Each inherits the one above it; triggers accumulate down the list. See [Database](../concepts/database.md) for how these triggers actually behave and [Choosing a base model](../guides/base-models.md) for picking one.

| Model                 | Fields added               | Triggers installed                                                                                                      |
| --------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `ApiModel`            | `id` (uuid7, primary key)  | `trg_protect_truncate` (refuses `TRUNCATE`), `trg_readonly_primarykey` (`pgtrigger.ReadOnly` on `id`)                   |
| `ApiTimestampedModel` | `created_at`, `updated_at` | + `trg_touch_updatedat` (sets `updated_at = NOW()` before any update)                                                   |
| `ApiAppendOnlyModel`  | _(drops `updated_at`)_     | `ApiModel`'s two, + `trg_append_only` (`Protect` on `Delete \| Update`) — **not** `ApiTimestampedModel`'s touch trigger |
| `ApiProtectedModel`   | —                          | `ApiTimestampedModel`'s three, + `trg_protect_delete` (`Protect` on `Delete`)                                           |
| `ApiSoftDeleteModel`  | `is_active`                | `ApiTimestampedModel`'s three, + `trg_softdelete_isactive` (`SoftDelete` rewriting `DELETE` into `is_active = False`)   |

## Schema helpers

`api_core/schemas/`. Factory functions live in `api_core/schemas/factories/`.

| Name                                                                          | Purpose                                                                                                                  | Module                         |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------ |
| `DTO`                                                                         | Strict base: `extra="forbid"`, `frozen=True`, `from_attributes=True`, `str_strip_whitespace=True`, `allow_inf_nan=False` | `schemas/base.py`              |
| `PermissiveDTO`                                                               | `DTO` with `extra="ignore"` instead of `"forbid"` (also the mixin `ApiConfig` itself uses)                               | `schemas/base.py`              |
| `BaseGet[PK=UUID]`                                                            | `{id: PK}` — base for every path/get schema                                                                              | `schemas/get.py`               |
| `IntInstancePath` / `UuidInstancePath`                                        | `BaseGet[PositiveInt]` / `BaseGet[UUID]` — detail-route path schemas                                                     | `schemas/path.py`              |
| `RelatedPath[PK, RelatedPK]`, `UuidToIntRelatedPath`, `UuidToUuidRelatedPath` | `{id, related}` — path schemas for link controllers                                                                      | `schemas/path.py`              |
| `PageQuery`                                                                   | `{page, page_size}` query fields                                                                                         | `schemas/pagination.py`        |
| `Paginated[Get]`                                                              | Response envelope: `next`, `previous`, `elements`, `pages`, `current`, `results`                                         | `schemas/pagination.py`        |
| `FilterQuery`, `PaginatedFilterQuery`, `UnpaginatedFilterQuery`               | Filter-query contracts; the paginated variant mixes in `PageQuery`                                                       | `schemas/filters.py`           |
| `UpdateManyToManyQuery`, `PatchManyToManyQuery`, `PutManyToManyQuery`         | The `overwrite` query flag `ModelManyToManyDetailController.put`/`.patch` parse                                          | `schemas/query.py`             |
| `build_put_schema(dto)`                                                       | Derives a `*Put` DTO from a `*Post`/`*Write` DTO by renaming the class                                                   | `schemas/factories/models.py`  |
| `build_patch_schema(dto)`                                                     | Derives a `*Patch` DTO from a `*Put` DTO by making every field optional                                                  | `schemas/factories/models.py`  |
| `build_scoped_path(model, parent_field, base=UuidInstancePath)`               | Derives a path schema carrying both a sub-resource's own key and its parent's                                            | `schemas/factories/path.py`    |
| `build_filter_query(base, cls, exclusive=None, inclusive=None, **defaults)`   | Derives a `FilterQuery` DTO from a `django_filter.FilterSet`'s declared filters                                          | `schemas/factories/filters.py` |

## Endpoints

Every url the template mounts, in the order `api_core/urls.py` and `api_auth/api.py` assemble them (the auth router itself sorts by path via `sort_urls`). All `auth/*` routes are declared in `api_auth/api.py` with `prefix="auth"`; the three root-level ones are mounted directly in `api_core/urls.py`.

| Path                                             | Methods                         | Url name                       | Controller                          |
| ------------------------------------------------ | ------------------------------- | ------------------------------ | ----------------------------------- |
| ``                                               | `GET`                           | `api-root`                     | `RootController`                    |
| `health/`                                        | `GET`                           | `health-check`                 | `HealthCheckController`             |
| `openapi/`                                       | `GET`                           | `openapi-schema`               | `dmr.openapi.views.OpenAPIJsonView` |
| `auth/csrf/`                                     | `GET`                           | `auth-csrf`                    | `CsrfController`                    |
| `auth/email-confirm/`                            | `POST`                          | `auth-email-confirm`           | `EmailConfirmController`            |
| `auth/email-resend/`                             | `POST`                          | `auth-email-resend`            | `EmailResendController`             |
| `auth/group/`                                    | `GET`, `POST`                   | `auth-group-list`              | `GroupListController`               |
| `auth/group/<int:id>/`                           | `GET`, `PUT`, `PATCH`, `DELETE` | `auth-group-detail`            | `GroupDetailController`             |
| `auth/group/all/`                                | `GET`                           | `auth-group-all`               | `GroupListAllController`            |
| `auth/mobile/login/`                             | `POST`                          | `auth-mobile-login`            | `MobileLoginController`             |
| `auth/mobile/logout/`                            | `POST`                          | `auth-mobile-logout`           | `MobileLogoutController`            |
| `auth/mobile/refresh/`                           | `POST`                          | `auth-mobile-refresh`          | `MobileRefreshController`           |
| `auth/mobile/two-factor/`                        | `POST`                          | `auth-mobile-two-factor`       | `MobileTwoFactorController`         |
| `auth/mobile/verify/`                            | `POST`                          | `auth-mobile-verify`           | `MobileVerifyController`            |
| `auth/permission/`                               | `GET`                           | `auth-permission-list`         | `PermissionListController`          |
| `auth/permission/<int:id>/`                      | `GET`                           | `auth-permission-detail`       | `PermissionDetailController`        |
| `auth/permission/all/`                           | `GET`                           | `auth-permission-all`          | `PermissionListAllController`       |
| `auth/profile/`                                  | `GET`                           | `auth-profile`                 | `ProfileController`                 |
| `auth/register/`                                 | `POST`                          | `auth-register`                | `RegisterController`                |
| `auth/two-factor/`                               | `GET`                           | `auth-two-factor`              | `TwoFactorController`               |
| `auth/two-factor-confirm/`                       | `POST`                          | `auth-two-factor-confirm`      | `TwoFactorConfirmController`        |
| `auth/two-factor-disable/`                       | `POST`                          | `auth-two-factor-disable`      | `TwoFactorDisableController`        |
| `auth/two-factor-recovery/`                      | `POST`                          | `auth-two-factor-recovery`     | `TwoFactorRecoveryController`       |
| `auth/two-factor-setup/`                         | `POST`                          | `auth-two-factor-setup`        | `TwoFactorSetupController`          |
| `auth/user/`                                     | `GET`, `POST`                   | `auth-user-list`               | `ApiUserListController`             |
| `auth/user/<uuid:id>/`                           | `GET`, `PUT`, `PATCH`, `DELETE` | `auth-user-detail`             | `ApiUserDetailController`           |
| `auth/user/all/`                                 | `GET`                           | `auth-user-all`                | `ApiUserListAllController`          |
| `auth/user/<uuid:id>/groups/`                    | `GET`, `PUT`, `PATCH`           | `auth-user-detail-groups`      | `ApiUserGroupsController`           |
| `auth/user/<uuid:id>/groups/<int:related>/`      | `GET`, `PUT`, `DELETE`          | `auth-user-groups-link`        | `ApiUserGroupsLinkController`       |
| `auth/user/<uuid:id>/permissions/`               | `GET`, `PUT`, `PATCH`           | `auth-user-detail-permissions` | `ApiUserPermissionsController`      |
| `auth/user/<uuid:id>/permissions/<int:related>/` | `GET`, `PUT`, `DELETE`          | `auth-user-permissions-link`   | `ApiUserPermissionsLinkController`  |
| `auth/web/login/`                                | `POST`                          | `auth-web-login`               | `WebLoginController`                |
| `auth/web/logout/`                               | `POST`                          | `auth-web-logout`              | `WebLogoutController`               |
| `auth/web/refresh/`                              | `POST`                          | `auth-web-refresh`             | `WebRefreshController`              |
| `auth/web/two-factor/`                           | `POST`                          | `auth-web-two-factor`          | `WebTwoFactorController`            |
| `auth/web/verify/`                               | `POST`                          | `auth-web-verify`              | `WebVerifyController`               |

Every url name is derived, not hand-typed — see [Routing](../concepts/routing.md) for the inference rules (`get_model_endpoint`, `route_inferred_controller`, `route_scoped_controller`) that produce every path and suffix in this table.
