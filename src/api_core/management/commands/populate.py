from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.transaction import atomic

from api_core.config import CONFIG
from api_core.seeding import (
    SeederEntry,
    SeederError,
    describe_seeder,
    filter_seeders,
    get_fixture_seeders,
    parse_app_filter,
    run_seeders,
)

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Popular la base de datos local con datos de prueba."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--list",
            action="store_true",
            help="Lista los seeders registrados, sin ejecutarlos.",
        )

        parser.add_argument(
            "--only",
            default="",
            help="Ejecuta solo los seeders de estas apps (separadas por comas).",
        )

        parser.add_argument(
            "--skip",
            default="",
            help="Omite los seeders de estas apps (separadas por comas).",
        )

    @override
    def handle(self, *args: str, **options: object) -> None:
        if options["list"]:
            self.list_seeders()
            return

        if not CONFIG.DEBUG:
            raise CommandError(
                "Este comando solo se puede ejecutar en ambientes de desarrollo.",
            )

        if CONFIG.SKIP_SEEDERS:
            return

        self.stdout.write(msg="Verificando estado de migraciones...")

        executor = MigrationExecutor(connection)

        nodes: set = executor.loader.graph.leaf_nodes()

        if executor.migration_plan(targets=nodes):
            raise CommandError("Hay migraciones sin aplicar.")

        self.stdout.write(msg=self.style.SUCCESS("Migraciones al día."))

        only = parse_app_filter(str(options["only"]))
        skip = parse_app_filter(str(options["skip"]))

        self.populate(only=only, skip=skip)

        self.stdout.write(msg=self.style.SUCCESS("Base de datos populada."))

    def list_seeders(self) -> None:
        entries = get_fixture_seeders()

        if not entries:
            self.stdout.write(msg="No hay seeders registrados.")
            return

        for entry in entries:
            self.stdout.write(msg=describe_seeder(entry))

    @atomic
    def populate(self, only: frozenset[str], skip: frozenset[str]) -> None:
        entries = filter_seeders(*get_fixture_seeders(), only=only, skip=skip)

        try:
            run_seeders(*entries, before_each=self.announce)
        except SeederError as exc:
            raise CommandError(str(exc)) from exc

    def announce(self, entry: SeederEntry) -> None:
        self.stdout.write(msg=f"Ejecutando `{entry.app_label}.{entry.name}`...")
