from collections.abc import Sequence
from http import HTTPStatus
from typing import ClassVar, override

from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpResponse
from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)
from dmr import Body, Cookies, ResponseSpec, modify, validate
from dmr.decorators import endpoint_decorator
from dmr.endpoint import ModifyAnyCallable, ValidateAnyCallable
from dmr.security.jwt import JWToken
from dmr.security.jwt.views import (
    CookieRefreshTokensAsyncController,
    RefreshTokenAsyncController,
)

from api_auth.schemas.refresh import MobileRefreshPost, MobileRefreshResponse
from api_auth.schemas.session import SessionCookies
from api_auth.services.jwt import EncodedJwtPair, build_jwt_pair, resolve_jwt_subject
from api_auth.services.session import consume_refresh
from api_core.controllers.serializers import CustomPydanticFastSerializer

from .base import (
    NO_STORE_HEADERS,
    CookieTokensMixin,
    JwtSettingsMixin,
    MobileAuthController,
    WebAuthController,
)

########################################################################################


class RotateTokensMixin:
    """
    What rotating a session means here, for both refresh controllers.

    `dmr` hands us the decoded refresh token; the account it belongs to
    is resolved the same way the rest of the API resolves a subject, and
    the token is spent before a new pair is signed, so it can never buy
    a second session.
    """

    async def get_user(self, token: JWToken) -> AbstractBaseUser:  # ruff: ignore[no-self-use]
        return await resolve_jwt_subject(token.sub)

    async def check_auth(  # ruff: ignore[no-self-use]
        self,
        user: AbstractBaseUser,
        token: JWToken,
    ) -> None:
        # `resolve_jwt_subject` has already refused an inactive account
        await consume_refresh(token, user)


########################################################################################


class MobileRefreshController(
    MobileAuthController[CustomPydanticFastSerializer],
    RotateTokensMixin,
    JwtSettingsMixin,
    RefreshTokenAsyncController[
        CustomPydanticFastSerializer,
        MobileRefreshPost,  # ty: ignore[invalid-type-arguments]
        MobileRefreshResponse,
    ],
):
    """Trade a refresh token in the request body for a brand new pair."""

    response_status_code: ClassVar[HTTPStatus] = HTTPStatus.OK

    # see `MobileLoginController.responses`
    responses: ClassVar[Sequence[ResponseSpec]] = ()

    @classmethod
    @override
    def modify_spec(cls) -> ModifyAnyCallable:
        return modify(
            headers=NO_STORE_HEADERS,
            status_code=cls.response_status_code,
        )

    @override
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    @modify.lazy(modify_spec)
    async def post(
        self,
        parsed_body: Body[MobileRefreshPost],
    ) -> MobileRefreshResponse:
        return await self.refresh(parsed_body)

    @override
    @sensitive_variables()
    async def convert_refresh_payload(self, payload: MobileRefreshPost) -> str:
        return payload.refresh

    @override
    @sensitive_variables()
    async def make_api_response(self) -> MobileRefreshResponse:
        tokens: EncodedJwtPair = build_jwt_pair(self.request.user)

        return MobileRefreshResponse(access=tokens.access, refresh=tokens.refresh)


########################################################################################


class WebRefreshController(
    WebAuthController[CustomPydanticFastSerializer],
    CookieTokensMixin,
    RotateTokensMixin,
    CookieRefreshTokensAsyncController[CustomPydanticFastSerializer, None],
):
    """
    The same rotation, driven by the cookies instead of a request body.

    The browser sends the refresh cookie on its own, which is exactly why
    CSRF is enforced here.
    """

    # see `MobileLoginController.responses`
    responses: ClassVar[Sequence[ResponseSpec]] = ()

    @classmethod
    @override
    def validate_spec(cls) -> ValidateAnyCallable:
        return validate(
            ResponseSpec(
                return_type=None,
                cookies=cls.issued_cookies_spec(),
                headers=cls.response_headers_spec(),
                status_code=cls.response_status_code,
            ),
        )

    @override
    @sensitive_variables()
    @validate.lazy(validate_spec)
    async def post(
        self,
        parsed_cookies: Cookies[SessionCookies],
    ) -> HttpResponse:
        # the cookies are declared so that they are part of the schema and
        # get validated; `dmr` reads them off the request on its own
        return await self.refresh()
