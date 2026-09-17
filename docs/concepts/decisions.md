---
icon: lucide/gavel
---

# Decisions

The rest of this section explains how things work. This page explains _why_
they work that way — the calls that are easy to second-guess later, the
reasoning behind each one, and what reversing it would actually cost.

## uuid7 primary keys instead of serial integers

`ApiModel.id` is a `UUIDField` defaulted, on both the ORM and the database
side, to `uuid7()` (see [Models](models.md)). A uuid7 is time-ordered, so it
keeps the two things a serial integer buys you — index locality on insert,
and a usable "created before/after" ordering (`ordering = ("-id",)` on
`ApiTimestampedModel`, with a comment noting exactly this) — while also
buying you the two things a serial integer can't: an id safe to hand to a
client before the row is committed (Django's `default=uuid7` runs in Python,
so an unsaved instance already has its real id), and no cross-table id
collisions to worry about if data ever moves between databases or gets
merged. The cost: a uuid7 is 16 bytes against 4 or 8 for an integer, and it
does not compress into a human-typeable id for support tickets. Reversing
this later means a data migration touching every foreign key in the schema —
this is the decision in this template that is, by a wide margin, the most
expensive to undo once real rows exist.

## Strict DTOs, and the wire types that pay for that strictness

`DTO.model_config` sets `extra="forbid"` and `frozen=True` as the default for
every schema in the template (see [Schemas](schemas.md)), rather than
Pydantic's own more permissive defaults. The payoff is that a client typo in
a field name, or a leftover field from a previous API version, fails loudly
at the schema boundary instead of being silently ignored — the failure mode
you want for a payload that is about to be trusted with a database write. The
cost shows up immediately: strict validation does not coerce a date string
into a `date`, so a small, deliberate set of coercion helpers
(`coerce_date`, `coerce_datetime`, `coerce_uuid` in
`api_core.schemas.validators`) exists specifically to give back the leniency
a client expects, without giving up the "no unknown fields" guarantee
everywhere else. Reversing the strictness would remove the need for those
helpers, but it would also mean an API that accepts payloads it never
validated the shape of — not a trade this template is willing to make.

## Rules enforced by triggers rather than application code

A soft delete, a read-only column, a truncate ban: every one of these could
be a check in a Django `save()` override or a service function instead of a
[`pgtrigger`](database.md) trigger. The template chooses the database
because a trigger cannot be bypassed by a bulk `.update()`, a management
command, a migration's `RunPython`, or a future developer who does not know
the rule exists and reaches for the ORM directly — the guarantee holds
_structurally_, not because every code path remembered to check it. The cost
is that the rule becomes invisible to a plain `grep` through `services/` —
you have to know to look at a model's `Meta.triggers` — and that a violated
trigger surfaces as a generic `IntegrityError`/`500` unless an operation's
`exc_handler` (see [Operations](operations.md)) is specifically written to
translate it into a clean API error. Reversing this for a given rule is
cheap in isolation (delete the trigger, add the check in Python) but loses
the "holds no matter what" property for that one rule.

## Append-only history instead of updated-in-place audit columns

`track_table` (see [Models](models.md)) generates a separate, append-only
`<Model>Event` row per change rather than columns like `updated_by`/
`updated_reason` on the tracked table itself. An append-only history table
answers "what did this row look like at every point in time, and in what
request, by whom" — a question mutable audit columns cannot answer past the
single most recent change. It also means the tracked table's own schema
never grows to accommodate audit metadata, and the history survives even a
row's own deletion (soft or hard). The cost is real: it's an extra table and
extra triggers per tracked model, an extra write on every insert and update,
and a second place `exclude=` has to be remembered for any field that must
never leave the tracked table (a `secret`, a `token_hash`). There's no
practical way to "reverse" this later without losing every change that was
never captured up to that point — the earlier a tracked table starts
tracking, the more useful its history is.

## Two authentication flavours (cookies for browsers, headers for apps)

The API accepts credentials either as `httponly` cookies (set by the API
itself, read back automatically by a browser, paired with a CSRF header) or
as a bearer token in an `Authorization` header (read and stored by whatever
client sent it) — see [API → Authentication](../api/authentication.md) for
the mechanics of each. Neither flavour alone covers both consumers well: a
mobile or server client has no cookie jar and no CSRF concept to defend
against, while a browser client that stored a bearer token in `localStorage`
or a JS-readable cookie would be handing an XSS bug direct access to it.
Supporting both means every session-issuing endpoint has to reason about
which flavour it's serving (see the cookie-vs-header branches in
`api_auth.controllers.login`/`refresh`/`logout`), which is the ongoing cost
of this decision — but collapsing to one flavour would mean asking one class
of client to accept a materially worse security posture than it needs to.

## Spanish user-facing messages with English identifiers

Every message actually returned to a client — a validation error, a
`detail` field, an email subject — is written in Spanish
(`"El código proporcionado no es válido."`,
`"El recurso solicitado no se encontró."`); every identifier a developer
reads — class names, field names, enum members, error `type` values — is
English (`BadRequestError`, `ConflictErrorTypes.LOCKED`, `RequestScopes.QUERY`).
The two audiences for those two vocabularies don't overlap: the client
reading a `detail` string doesn't care what the Python class was called, and
the developer grepping the codebase for `ConflictErrorTypes` doesn't want to
match on Spanish prose that might get rephrased. Keeping identifiers in
English also keeps this template legible to the wider Django/Python
ecosystem it's built on. The cost is the obvious one: every new user-facing
string needs a translator's ear, not just a developer's, and there is
currently no `i18n` framework in play — the Spanish strings are the only
strings, not one locale among several. Reversing the split (English
messages, or a real `i18n` layer with Spanish as one option) is a
find-and-replace away for the messages themselves, but adding a second
locale properly means retrofitting translation keys everywhere a literal
string is raised today.
