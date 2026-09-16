---
icon: lucide/lightbulb
---

# Concepts

This section explains the ideas [`api_core`](../getting-started/layout.md) rests
on. It builds on [`django-modern-rest`][dmr-docs] (`dmr`), the library that
gives this template its request dispatch, validation and OpenAPI machinery.
`dmr` supplies the primitives — `Controller`, `Endpoint`, parsers, auth,
throttling, the OpenAPI builder. `api_core` composes those primitives into the
generics that the rest of the codebase actually writes against, so a new
resource costs a handful of declarations instead of a hand-rolled view.

## Four layers

Every endpoint in this template is built from the same four layers, each with
its own page in this section:

| Layer | Answers | Page |
| --- | --- | --- |
| Controller | Which url, which methods, who may call it | [Controllers](controllers.md) |
| Schema | What shape a request and response take | [Schemas](schemas.md) |
| Operation | What actually reads or writes rows | [Operations](operations.md) |
| Model | What the database itself refuses to allow | [Models](models.md) |

A request moves down this table — controller to schema to operation to model —
and the response carries the same shape back up. [Request lifecycle](request-lifecycle.md)
walks a single request through all four, naming the exact module responsible
at each hop.

## What the database is trusted with

The application layer validates shapes and enforces authorization; it does not
re-implement invariants PostgreSQL can guarantee on its own. Uniqueness,
not-null, foreign keys, and rules like "this row can never be deleted" are
declared as constraints and triggers, not `if` statements. [Database](database.md)
covers what lives at that layer, and [Models](models.md) covers the base
classes that wire a table up to it. When a trigger refuses a write, [Errors](errors.md)
covers how that refusal turns into a `409`, not a stack trace.

## Why an endpoint is a few lines of generics

Because the four layers are generic, adding a resource is mostly picking type
parameters: a model, a set of schemas, a filterset, and a controller family
whose default operations already know how to run them. [Controllers](controllers.md)
and [Operations](operations.md) describe what those generics resolve to and
what they refuse to accept, and the [guide to adding a resource](../guides/new-resource.md)
walks the same path end to end against a real table.

The parts that would otherwise be hand-written and easy to get out of sync —
urls and the OpenAPI document — are derived instead of declared:
[Routing](routing.md) covers how a controller class becomes a url, and
[OpenAPI](openapi.md) covers how the same class becomes a documented operation.

## Reading order

1. [Request lifecycle](request-lifecycle.md) — the whole path, once, so the
   rest of this section has a spine to hang off.
2. [Controllers](controllers.md), [Schemas](schemas.md), [Operations](operations.md),
   [Models](models.md) — one page per layer, top to bottom.
3. [Database](database.md) — what the bottom layer leans on.
4. [Routing](routing.md), [Errors](errors.md), [OpenAPI](openapi.md) — the
   cross-cutting concerns every controller gets for free.
5. [Decisions](decisions.md) — why the above looks the way it does, and what
   it would cost to change.
