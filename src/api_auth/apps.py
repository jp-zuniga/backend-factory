from typing import override

from django.apps import AppConfig

########################################################################################


class ApiAuth(AppConfig):
    name = "api_auth"
    label = "apiauth"

    @override
    def ready(self) -> None:
        import api_auth.seeders  # ruff: ignore[import-outside-top-level, unused-import]
