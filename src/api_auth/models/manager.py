from typing import TYPE_CHECKING, override

from asgiref.sync import sync_to_async
from django.contrib.auth.models import UserManager
from django.utils.timezone import now
from pgtrigger import ignore

if TYPE_CHECKING:
    from datetime import datetime

    from .user import ApiUser

########################################################################################


class ApiUserManager(UserManager):
    use_in_migrations = True

    @override
    async def acreate_superuser(
        self,
        username: str,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: bool | str,
    ) -> ApiUser:
        return await super().acreate_superuser(
            username,
            email,
            password,
            **extra_fields,
        )

    @override
    def create_superuser(
        self,
        username: str,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: bool | str,
    ) -> ApiUser:
        return super().create_superuser(username, email, password, **extra_fields)

    @override
    async def _acreate_user(
        self,
        username: str,
        email: str | None,
        password: str | None,
        **extra_fields: bool | str,
    ) -> ApiUser:
        return await sync_to_async(func=self._create_user)(
            username,
            email,
            password,
            **extra_fields,
        )

    @ignore("apiauth.ApiUser:trg_apiuser_protect_insert")
    @override
    def _create_user(
        self,
        username: str,
        email: str | None,
        password: str | None,
        **extra_fields: bool | datetime | str,
    ) -> ApiUser:
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_superuser"):
            # superusers are provisioned out of band,
            # they cannot confirm an address through the API
            extra_fields.setdefault("email_verified_at", now())

        return super()._create_user(username, email, password, **extra_fields)
