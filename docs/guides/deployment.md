---
icon: lucide/git-branch
---

# Deployment

!!! note "Outline"

    Taking the template to an environment that is not a laptop.

- The image, its build stages, and what runs at container start.
- Environment variables that must be set, and the checks that refuse to start without them.
- `DEPLOY=True`: what it tightens, from cookies to secret lengths.
- Migrations and seeders during a release.
- Health checks and what they actually probe.
- The pipeline in `.github`, and what it gates.
