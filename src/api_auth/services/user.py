from typing import TYPE_CHECKING, override

from asgiref.sync import sync_to_async
from django.contrib.auth import aauthenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.views.decorators.debug import sensitive_variables
from dmr.security.jwt.auth import set_request_attrs

from api_auth.schemas.user import ApiClientPost
from api_core.services.operations import ManyToManyCreateOperation
from api_core.services.operations.m2m import exec_m2m_post
from api_exceptions.enums import BadRequestErrorTypes, RequestScopes
from api_exceptions.errors import BadRequestError, UnauthorizedError

from .account import ensure_email_verified, issue_email_verification

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.http import HttpRequest
    from pydantic import PositiveInt

    from api_auth.models import ApiUser
    from api_auth.schemas.login import LoginPost
    from api_auth.schemas.user import ApiUserGet, ApiUserPost
    from api_utils.types import DatabaseModel

########################################################################################


@sensitive_variables()
async def authenticate_user(data: LoginPost, request: HttpRequest) -> ApiUser:
    user: ApiUser | None = await aauthenticate(
        request,
        password=data.password,
        username=data.username,
    )

    if user is None:
        raise UnauthorizedError(
            detail="Las credenciales proporcionadas no son válidas.",
        )

    ensure_email_verified(user)

    set_request_attrs(request, user)

    return user


########################################################################################


@sensitive_variables()
def check_password_match(data: ApiUserPost) -> None:
    if data.password1 == data.password2:
        return

    msg = "Las contraseñas ingresadas no son iguales."

    raise BadRequestError(
        field_errors={"password1": msg, "password2": msg},
        type=BadRequestErrorTypes.FAILED_VALIDATION,
    ).scoped(RequestScopes.BODY)


########################################################################################


@sensitive_variables()
def check_password_strength(data: ApiUserPost, user: ApiUser | None = None) -> None:
    subject: ApiUser = user or get_user_model()(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        username=data.username,
    )

    try:
        validate_password(password=data.password1, user=subject)
    except DjangoValidationError as v:
        errs: str = (
            "; ".join(msg.replace(".", ",").removesuffix(",") for msg in v)
        ).removesuffix(";").capitalize() + "."

        raise BadRequestError(
            field_errors={"password1": errs, "password2": errs},
            type=BadRequestErrorTypes.FAILED_VALIDATION,
        ).scoped(RequestScopes.BODY) from v


########################################################################################


@sensitive_variables()
def dump_user_post_data(data: ApiUserPost) -> dict:
    groups: Sequence[PositiveInt] = (
        Group.objects.filter(name=data.group.value).values_list("id", flat=True)
        if isinstance(data, ApiClientPost)
        else (data.groups or ())
    )

    exclude: set[str] = {
        "password1",
        "password2",
        "group" if isinstance(data, ApiClientPost) else "groups",
    }

    return data.model_dump(exclude=exclude) | {
        "password": data.password1,
        "groups": groups,
    }


########################################################################################


class UserCreateOperation[
    Get: ApiUserGet,
    Post: ApiUserPost,
](ManyToManyCreateOperation[Get, Post]):
    __slots__ = ()

    @override
    @sensitive_variables()
    def dump(self, dto: Post) -> dict:
        check_password_match(dto)
        check_password_strength(dto)

        return dump_user_post_data(dto)

    @override
    @sensitive_variables()
    async def execute(self, data: dict) -> DatabaseModel:
        user: DatabaseModel = await sync_to_async(func=exec_m2m_post)(
            *self.fields,
            data=data,
            qs=self.qs,
            user=True,
        )

        await issue_email_verification(user)  # ty: ignore[invalid-argument-type]

        return user
