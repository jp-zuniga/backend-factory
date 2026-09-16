---
icon: lucide/chart-network
---

# Sub-resources

!!! note "Outline"

    Exposing rows that only make sense underneath a parent row.

- When a sub-resource is the right shape, and when a filter is enough.
- Declaring `parent_field`, and everything that is derived from it.
- Building the path schema with `build_scoped_path`.
- What the scoped controllers guarantee: isolation between parents on read and write.
- Routing them, and the urls that come out.
- Nesting deeper, and why the template stops at one level.
