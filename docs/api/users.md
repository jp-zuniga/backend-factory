---
icon: lucide/users-round
---

# Users and permissions

## Profile versus the user collection

```http
GET /auth/profile/
```

Always resolves to *the caller's own* account — there is no id in the path,
and no permission is required beyond being authenticated (`permissions` on
this controller is empty for `GET`). It's the endpoint a client calls after
login to render "who am I," and returns the same shape as a user detail.

The full collection lives separately, and does need permissions:

| Endpoint | Purpose |
| --- | --- |
| `GET /auth/user/` | Paginated list, filterable/searchable |
| `GET /auth/user/all/` | Unpaginated, inline shape — for a dropdown |
| `GET/PUT/PATCH/DELETE /auth/user/{id}/` | A specific account |

`DELETE` here doesn't remove the row: `ApiUser` is a soft-delete model, so
the account is deactivated (`is_active` becomes `False`) rather than erased.
See [Concepts → Models](../concepts/models.md) for what that guarantees.

## Creating users

Two different endpoints create accounts, with different permission
requirements and a different write schema:

- **`POST /auth/register/`** — public registration (see
  [Email confirmation](email-confirmation.md)). The client picks a `group`
  from a fixed, non-privileged choice (`"Cliente"`); there is no way to
  self-assign staff groups or explicit permissions through this endpoint.
- **`POST /auth/user/`** — staff-only creation. Requires the `add` permission
  on the user model, and accepts arbitrary `groups`/`permissions` lists by
  id, alongside the same username/email/password fields.

Both funnel through the same password-matching and password-strength checks
before the row is written, and both trigger the same
[email confirmation](email-confirmation.md) message when the account has an
address.

## Groups and permissions on a user

```http
GET /auth/user/{id}/groups/
PUT /auth/user/{id}/groups/       # full replace
PATCH /auth/user/{id}/groups/     # partial

GET /auth/user/{id}/permissions/
PUT /auth/user/{id}/permissions/
PATCH /auth/user/{id}/permissions/
```

These read/replace the *whole set* at once (a list of ids in the body).
To attach or detach a single group or permission without touching the rest
of the set, use the link endpoints instead:

```http
PUT    /auth/user/{id}/groups/{group_id}/       # attach
DELETE /auth/user/{id}/groups/{group_id}/       # detach

PUT    /auth/user/{id}/permissions/{permission_id}/
DELETE /auth/user/{id}/permissions/{permission_id}/
```

The standalone group/permission resources themselves:

| Endpoint | Notes |
| --- | --- |
| `GET/POST /auth/group/`, `GET/PUT/PATCH/DELETE /auth/group/{id}/` | Read/write |
| `GET /auth/permission/`, `GET /auth/permission/{id}/` | Read-only — Django's built-in `Permission` model isn't meant to be created or edited from this API |

## How permissions are evaluated

Every write and every non-public read is checked against Django's
`app_label.action_model` permission strings (e.g. `api_auth.view_apiuser`)
before the request reaches the operation. **Superusers skip this check
entirely** — an active superuser account can call any method on any
controller regardless of its declared `permissions` mapping. Everyone else
needs the exact permission the controller asks for, per HTTP method; a
controller with no entry for the method it received fails closed with
`403`, rather than falling through unchecked.

## Deactivating a user

`DELETE /auth/user/{id}/` never removes the row: soft delete means
`is_active` flips to `False` and the account survives (its history, its
foreign keys, its audit trail all stay intact). A deactivated account can no
longer authenticate — [logging in](sessions.md#logging-in) as it answers
`401` the same way a wrong password would.
