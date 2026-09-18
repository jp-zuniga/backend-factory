from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from api_core.seeding import (
    SeederEntry,
    SeederError,
    describe_seeder,
    get_structural_seeders,
    parse_app_filter,
    run_structural_seeders,
)

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = (
        "Aplica los seeders estructurales (grupos, permisos, catálogos fijos, etc.). "
        "Normalmente corren solos tras cada `migrate`; este comando sirve para "
        "reaplicarlos manualmente."
    )

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--list",
            action="store_true",
            help="Lista los seeders estructurales registrados, sin ejecutarlos.",
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

        only = parse_app_filter(str(options["only"]))
        skip = parse_app_filter(str(options["skip"]))

        try:
            ran = run_structural_seeders(
                only=only,
                skip=skip,
                before_each=self.announce,
            )
        except SeederError as exc:
            raise CommandError(str(exc)) from exc

        if not ran:
            self.stdout.write(
                msg="Omitido: `SKIP_SEEDERS` activo, u otro proceso tiene el lock.",
            )

            return

        self.stdout.write(msg=self.style.SUCCESS("Seeders estructurales aplicados."))

    def list_seeders(self) -> None:
        entries = get_structural_seeders()

        if not entries:
            self.stdout.write(msg="No hay seeders estructurales registrados.")
            return

        for entry in entries:
            self.stdout.write(msg=describe_seeder(entry))

    def announce(self, entry: SeederEntry) -> None:
        self.stdout.write(msg=f"Ejecutando seeder `{entry.app_label}.{entry.name}`...")
