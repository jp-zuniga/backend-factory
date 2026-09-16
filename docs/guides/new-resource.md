---
icon: lucide/star
---

# Adding a resource

!!! note "Outline"

    The end-to-end walkthrough: one new table exposed as a full set of endpoints.

- Creating the app and registering it.
- The model: picking a base, naming constraints and indexes, tracking history.
- The migration, and reading it before applying it.
- Schemas: read, write, and the generated put, patch and filter variants.
- The filterset, and which fields are worth exposing.
- Controllers: which family to inherit, and the permissions to declare.
- Routing the controllers and checking the generated OpenAPI.
- A checklist of what should pass before opening a pull request.
