---
icon: lucide/users-round
---

# Users and permissions

## Profile versus the user collection

```http
GET /auth/profile/ HTTP/1.1
```

Always resolves to the caller's own account: there is no id in the path,
and no permission is required beyond being authenticated. It's the
endpoint a client calls after login to render "who am I," and returns the
same shape as a user detail.

The full collection lives separately, and does need permissions.
`GET /auth/user/` returns a paginated, filterable, and searchable list.
`GET /auth/user/all/` returns the unpaginated, inline shape, meant for a
dropdown. `GET`/`PUT`/`PATCH`/`DELETE /auth/user/{id}/` address a specific
account.

`DELETE` here doesn't remove the row: the account is deactivated
(`is_active` becomes `False`) rather than erased, and can no longer
authenticate afterward.

## Creating users

Two different endpoints create accounts, with different permission
requirements and a different write schema. `POST /auth/register/` is
public registration (see [Email confirmation](email-confirmation.md)); the
client picks a `group` from a fixed, non-privileged choice (`"Cliente"`),
and there is no way to self-assign staff groups or explicit permissions
through this endpoint. `POST /auth/user/` is staff-only creation, requiring
the `add` permission on the user model, and accepts arbitrary
`groups`/`permissions` lists by id, alongside the same
username/email/password fields.

Both funnel through the same password-matching and password-strength
checks before the row is written, and both trigger the same
[email confirmation](email-confirmation.md) message when the account has
an address.

## Groups and permissions on a user

```http
GET /auth/user/{id}/groups/ HTTP/1.1
```

```http
PUT /auth/user/{id}/groups/ HTTP/1.1
```

```http
PATCH /auth/user/{id}/groups/ HTTP/1.1
```

```http
GET /auth/user/{id}/permissions/ HTTP/1.1
```

```http
PUT /auth/user/{id}/permissions/ HTTP/1.1
```

```http
PATCH /auth/user/{id}/permissions/ HTTP/1.1
```

`GET` reads the whole set, `PUT` replaces it in full, and `PATCH` applies
a partial update, all as a list of ids in the body. To attach or detach a
single group or permission without touching the rest of the set, the
link endpoints do the job instead:

```http
PUT /auth/user/{id}/groups/{group_id}/ HTTP/1.1
```

```http
DELETE /auth/user/{id}/groups/{group_id}/ HTTP/1.1
```

```http
PUT /auth/user/{id}/permissions/{permission_id}/ HTTP/1.1
```

```http
DELETE /auth/user/{id}/permissions/{permission_id}/ HTTP/1.1
```

`PUT` attaches, `DELETE` detaches. The standalone group and permission
resources round out the surface: `GET`/`POST /auth/group/` and
`GET`/`PUT`/`PATCH`/`DELETE /auth/group/{id}/` are fully read/write, while
`GET /auth/permission/` and `GET /auth/permission/{id}/` are read-only,
since permissions themselves aren't meant to be created or edited from
this API.

## How permissions are evaluated

Every write and every non-public read is checked against the permission
the endpoint requires before the request is processed. Superusers skip
this check entirely: an active superuser account can call any method on
any endpoint. Everyone else needs the exact permission the endpoint asks
for, per HTTP method; an endpoint with no permission configured for the
method it received fails closed with `403`, rather than falling through
unchecked.

## Deactivating a user

`DELETE /auth/user/{id}/` never removes the row: the account is
deactivated instead, with its history, its foreign keys, and its audit
trail all staying intact. A deactivated account can no longer
authenticate; [logging in](sessions.md#logging-in) as it answers `401`
the same way a wrong password would.
