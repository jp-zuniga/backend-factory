from collections.abc import Sequence
from http import HTTPStatus
from typing import ClassVar, override

from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)
from dmr import Body, Cookies, ResponseSpec, modify
from dmr.decorators import endpoint_decorator
from dmr.endpoint import ModifyAnyCallable
from dmr.security.jwt.views import VerifyTokenAsyncController

from api_auth.schemas.session import SessionCookies
from api_auth.schemas.verify import MobileVerifyPost, WebVerifyResponse
from api_auth.services.csrf import ensure_csrf
from api_auth.services.session import inspect_session, verify_jwt
from api_core.controllers.serializers import CustomPydanticFastSerializer

from .base import (
    NO_STORE_HEADERS,
    JwtSettingsMixin,
    MobileAuthController,
    WebAuthController,
)

########################################################################################


class MobileVerifyController(
    MobileAuthController[CustomPydanticFastSerializer],
    JwtSettingsMixin,
    VerifyTokenAsyncController[
        CustomPydanticFastSerializer,
        MobileVerifyPost,  # ty: ignore[invalid-type-arguments]
    ],
):
    """
    Answer `204` when the given token is still live.

    `dmr` only verifies access tokens; the client says which kind it is
    holding, so a refresh or a challenge token can be checked as well.
    A revoked session is refused even while its tokens are unexpired.
    """

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
    async def post(self, parsed_body: Body[MobileVerifyPost]) -> None:
        await self.verify(parsed_body)

    @override
    @sensitive_variables()
    async def convert_verify_payload(self, payload: MobileVerifyPost) -> str:
        return payload.token

    @override
    @sensitive_variables()
    async def verify(self, parsed_body: MobileVerifyPost) -> None:
        await verify_jwt(
            encoded=await self.convert_verify_payload(parsed_body),
            expected_type=parsed_body.type,
        )


########################################################################################


class WebVerifyController(WebAuthController[CustomPydanticFastSerializer]):
    """
    Report which half of the cookie session is still live.
    """

    @modify(headers=NO_STORE_HEADERS, status_code=HTTPStatus.OK)
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    async def post(self, parsed_cookies: Cookies[SessionCookies]) -> WebVerifyResponse:
        ensure_csrf(self.request)

        access, refresh = await inspect_session(
            access=parsed_cookies.access,
            refresh=parsed_cookies.refresh,
        )

        return WebVerifyResponse(access=access, refresh=refresh)
