from typing import override

from django.apps import AppConfig
from django.db.models import CharField, TextField
from django.db.models.functions import Length
from django.db.models.signals import post_migrate

from api_core.seeding import run_structural_seeders
from api_utils.db import ImmutableUnaccent

########################################################################################


def seed_structural(
    *args,  # ruff: ignore[missing-type-args, unused-function-argument]
    **kwargs,  # ruff: ignore[missing-type-kwargs, unused-function-argument]
) -> None:
    run_structural_seeders()


class ApiCore(AppConfig):
    name = "api_core"
    label = "apicore"

    @override
    def ready(self) -> None:
        import api_core.checks  # ruff: ignore[import-outside-top-level, unused-import]

        post_migrate.connect(receiver=seed_structural, sender=self)

        CharField.register_lookup(lookup=ImmutableUnaccent)
        CharField.register_lookup(lookup=Length, lookup_name="len")
        TextField.register_lookup(lookup=ImmutableUnaccent)
        TextField.register_lookup(lookup=Length, lookup_name="len")
