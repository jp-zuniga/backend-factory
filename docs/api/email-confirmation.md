---
icon: lucide/badge-check
---

# Email confirmation

The flow between registering an account and being allowed to log in, when
the deployment requires a confirmed address.

## Registering

```http
POST /auth/register/ HTTP/1.1
```

```json
{
  "username": "asdf",
  "email": "asdf@example.com",
  "password1": "asdf123!",
  "password2": "asdf123!",
  "group": "Cliente"
}
```

Creates the account and answers `201` with its data immediately, since the
row exists and can already be looked up, but `email_verified_at` is
`null`. If email verification is required and the account has an email
address, logging in is refused with `403` until that address is
confirmed. Staff accounts are created separately, through
[Users and permissions](users.md#creating-users), and go through the same
confirmation state.

## The confirmation message

Registering, or requesting a resend, sends a message containing both a
link and a bare code, built from the same single-use token:

```
Para confirmar su correo electrónico, ingrese al siguiente enlace:

https://<frontend>/verify-email?token=<token>

Si su cliente de correo no admite enlaces, ingrese este código: <token>

El enlace vence en 24 horas.
```

The token is a 32-byte URL-safe random string and expires 24 hours after
issue. Issuing a new one invalidates every other still-live token for that
address; only the latest message requested is ever redeemable.

## Confirming

```http
POST /auth/email-confirm/ HTTP/1.1
```

```json
{ "token": "<the token from the email>" }
```

On success, answers `204` and sets `email_verified_at` on the account. An
unknown, expired, or already-spent token answers `400`:

```json title="400 Bad Request"
{
  "detail": "Uno o más campos no se pudieron validar.",
  "field_errors": { "body.token": "El enlace no es válido o ya expiró." }
}
```

## Requesting a new message

```http
POST /auth/email-resend/ HTTP/1.1
```

```json
{ "email": "asdf@example.com" }
```

Always answers `202`, whether or not that address belongs to an account,
whether or not it's already verified. Nothing in the response ever reveals
which is the case: a new message goes out only when there's an unverified
account behind the address, and the endpoint stays silent otherwise, so it
can't be used to test which addresses are registered.

## Changing an email address

Since a confirmation token is bound to the exact address it was issued
for, if the account's email changes after a code was sent, redeeming the
old code is rejected (`400`, same as an expired one) rather than
confirming the new address. A fresh confirmation for the new address is
needed instead.

## Turning the requirement off

A deployment can choose to let accounts log in without ever confirming an
address, useful when it doesn't send mail, or verifies identity some
other way. The registration and confirmation endpoints keep working the
same either way; only the login-time check is skipped.
