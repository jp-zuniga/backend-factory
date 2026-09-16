from collections.abc import Sequence
from http import HTTPStatus
from typing import ClassVar, override

from django.http import HttpResponse
from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)
from dmr import Body, Cookies, ResponseSpec, modify, validate
from dmr.decorators import endpoint_decorator
from dmr.endpoint import ValidateAnyCallable
from dmr.security.jwt.views import CookieLogoutAsyncController

from api_auth.enums import TokenTypes
from api_auth.schemas.logout import MobileLogoutPost
from api_auth.schemas.session import SessionCookies
from api_auth.services.session import close_session
from api_core.controllers.serializers import CustomPydanticFastSerializer

from .base import (
    NO_STORE_HEADERS,
    CookieTokensMixin,
    MobileAuthController,
    WebAuthController,
)

########################################################################################


class MobileLogoutController(MobileAuthController[CustomPydanticFastSerializer]):
    """
    Close the session the given tokens belong to.

    Either token identifies the whole session, so sending one of the two
    is enough to revoke both.
    """

    @modify(
        headers=NO_STORE_HEADERS,
        status_code=HTTPStatus.NO_CONTENT,
    )
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    async def post(self, parsed_body: Body[MobileLogoutPost]) -> None:  # ruff: ignore[no-self-use]
        await close_session(
            access=parsed_body.access,
            refresh=parsed_body.refresh,
        )


########################################################################################


class WebLogoutController(
    WebAuthController[CustomPydanticFastSerializer],
    CookieTokensMixin,
    CookieLogoutAsyncController[CustomPydanticFastSerializer, None],
):
    """
    Close the session the cookies belong to, and drop every one of them.

    `dmr` only drops the cookies, because its blocklist app is optional;
    here the tokens are revoked as well, so one that leaked before the
    logout cannot outlive it.
    """

    # see `MobileLoginController.responses`
    responses: ClassVar[Sequence[ResponseSpec]] = ()

    @classmethod
    @override
    def validate_spec(cls) -> ValidateAnyCallable:
        return validate(
            ResponseSpec(
                return_type=None,
                cookies=cls.discarded_cookies_spec(),
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
        # get validated; `revoke_tokens` reads them off the request
        return await self.logout()

    @override
    @sensitive_variables()
    async def revoke_tokens(self) -> None:
        await close_session(
            access=self.request.COOKIES.get(TokenTypes.ACCESS),
            refresh=self.request.COOKIES.get(TokenTypes.REFRESH),
        )
