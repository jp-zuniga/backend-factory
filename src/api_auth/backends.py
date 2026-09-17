from typing import TYPE_CHECKING, override

from django.contrib.auth import (
    acheck_password_with_timing_attack_mitigation,
    check_password_with_timing_attack_mitigation,
    get_user_model,
)
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import DataError
from django.views.decorators.debug import sensitive_variables

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from api_auth.models import ApiUser
    from api_utils.types import ParsedHttpRequest

########################################################################################

USER_MODEL: ApiUser = get_user_model()

########################################################################################


class ApiUserBackend(ModelBackend):
    @override
    def _get_user_permissions(self, user_obj: ApiUser) -> QuerySet:
        return user_obj.permissions.all()  # ty: ignore[unresolved-attribute]

    @override
    @sensitive_variables("password")
    async def aauthenticate(
        self,
        request: ParsedHttpRequest,
        username: str | None = None,
        password: str | None = None,
        **kwargs: str,
    ) -> ApiUser | None:
        if username is None:
            username = kwargs.get(USER_MODEL.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            user = await USER_MODEL._default_manager.filter(**{  # ruff: ignore[private-member-access]
                USER_MODEL.USERNAME_FIELD: username,
                "is_active": True,
            }).aget()
        except DataError, MultipleObjectsReturned, ObjectDoesNotExist:
            user = None

        if await acheck_password_with_timing_attack_mitigation(
            user,
            password,
        ) and self.user_can_authenticate(user):
            return user

        return None

    @override
    @sensitive_variables("password")
    def authenticate(
        self,
        request: ParsedHttpRequest,
        username: str | None = None,
        password: str | None = None,
        **kwargs: str,
    ) -> ApiUser | None:
        if username is None:
            username = kwargs.get(USER_MODEL.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            user = USER_MODEL._default_manager.filter(**{  # ruff: ignore[private-member-access]
                USER_MODEL.USERNAME_FIELD: username,
                "is_active": True,
            }).get()
        except DataError, MultipleObjectsReturned, ObjectDoesNotExist:
            user = None

        if check_password_with_timing_attack_mitigation(
            user,
            password,
        ) and self.user_can_authenticate(user):
            return user

        return None
