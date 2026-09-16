---
icon: lucide/folder-lock
---

# Choosing a base model

!!! note "Outline"

    A decision guide from "what does this table do" to a base class and a
    controller family.

- A table of the four bases against the operations each one allows.
- Pairing a base with controllers so refusals arrive as `405`, not as a trigger error.
- Soft delete: what clients see afterwards, and the filtering it forces on queries.
- Append-only: the history it buys, and the migrations it makes harder.
- Changing a base after rows exist.
