from collections.abc import Sequence
from http import HTTPStatus
from typing import ClassVar, Final, override

from django.http import HttpResponse
from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)
from dmr import Body, ResponseSpec, validate
from dmr.decorators import endpoint_decorator
from dmr.endpoint import ValidateAnyCallable
from dmr.security.jwt.views import (
    CookieObtainTokensAsyncController,
    ObtainTokensAsyncController,
    ObtainTokensPayload,
)

from api_auth.enums import TokenTypes
from api_auth.models import ApiUser
from api_auth.schemas.login import (
    MobileLoginPost,
    MobileLoginResponse,
    WebLoginPost,
    WebLoginResponse,
)
from api_auth.schemas.twofactor import MobileChallengeResponse, WebChallengeResponse
from api_auth.schemas.user import ApiUserInlineGet
from api_auth.services.jwt import EncodedJwtPair
from api_auth.services.session import open_session
from api_auth.services.user import authenticate_user
from api_core.config import CONFIG
from api_core.controllers.serializers import CustomPydanticFastSerializer
from api_core.services.mappers import instance_mapper

from .base import (
    NO_STORE_SPEC,
    NO_STORE_VALUES,
    CookieTokensMixin,
    JwtSettingsMixin,
    MobileAuthController,
    WebAuthController,
)

########################################################################################

CHALLENGE_LIFETIME: Final[int] = int(CONFIG.JWT_CHALLENGE_LIFETIME.total_seconds())

########################################################################################


class MobileLoginController(
    MobileAuthController[CustomPydanticFastSerializer],
    JwtSettingsMixin,
    ObtainTokensAsyncController[
        CustomPydanticFastSerializer,
        MobileLoginPost,  # ty: ignore[invalid-type-arguments]
        HttpResponse,
    ],
):
    """
    Trade credentials for a token pair, or for a second factor challenge.

    `dmr` returns one body on one status code; this flow answers `202`
    with a challenge instead whenever the account has a second factor,
    which is why the endpoint is described by hand.
    """

    responses: ClassVar[Sequence[ResponseSpec]] = ()

    @classmethod
    def validate_spec(cls) -> ValidateAnyCallable:
        return validate(
            ResponseSpec(
                return_type=MobileLoginResponse,
                headers=NO_STORE_SPEC,
                status_code=HTTPStatus.OK,
            ),
            ResponseSpec(
                return_type=MobileChallengeResponse,
                headers=NO_STORE_SPEC,
                status_code=HTTPStatus.ACCEPTED,
            ),
        )

    @override
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    @validate.lazy(validate_spec)
    async def post(self, parsed_body: Body[MobileLoginPost]) -> HttpResponse:
        return await self.login(parsed_body)

    @override
    @sensitive_variables()
    async def login(self, parsed_body: MobileLoginPost) -> HttpResponse:
        await authenticate_user(
            request=self.request,
            **await self.convert_auth_payload(parsed_body),
        )

        return await self.make_api_response()

    @override
    @sensitive_variables()
    async def convert_auth_payload(
        self,
        payload: MobileLoginPost,
    ) -> ObtainTokensPayload:
        return {"password": payload.password, "username": payload.username}

    @override
    async def make_api_response(self) -> HttpResponse:
        user: ApiUser = self.request.user

        session: EncodedJwtPair | str = await open_session(user)

        if isinstance(session, EncodedJwtPair):
            return self.to_response(
                MobileLoginResponse(
                    access=session.access,
                    refresh=session.refresh,
                    user=instance_mapper(user, ApiUserInlineGet),
                ),
                headers=NO_STORE_VALUES,
                status_code=HTTPStatus.OK,
            )

        return self.to_response(
            MobileChallengeResponse(
                challenge=session,
                expires_in=CHALLENGE_LIFETIME,
            ),
            headers=NO_STORE_VALUES,
            status_code=HTTPStatus.ACCEPTED,
        )


########################################################################################


class WebLoginController(
    WebAuthController[CustomPydanticFastSerializer],
    CookieTokensMixin,
    CookieObtainTokensAsyncController[
        CustomPydanticFastSerializer,
        WebLoginPost,  # ty: ignore[invalid-type-arguments]
        WebLoginResponse,
    ],
):
    """
    The same flow as `MobileLoginController`, with the tokens in cookies.

    The tokens never reach the response body: they are `httponly` cookies,
    so no script on the page can read them.
    """

    response_status_code: ClassVar[HTTPStatus] = HTTPStatus.OK

    # see `MobileLoginController.responses`
    responses: ClassVar[Sequence[ResponseSpec]] = ()

    @classmethod
    @override
    def validate_spec(cls) -> ValidateAnyCallable:
        return validate(
            ResponseSpec(
                return_type=WebLoginResponse,
                cookies={**cls.issued_cookies_spec(), **cls.csrf_cookie_spec()},
                headers=cls.response_headers_spec(),
                status_code=cls.response_status_code,
            ),
            ResponseSpec(
                return_type=WebChallengeResponse,
                cookies={
                    TokenTypes.CHALLENGE: cls.challenge_cookie_spec(),
                    **cls.csrf_cookie_spec(),
                },
                headers=cls.response_headers_spec(),
                status_code=HTTPStatus.ACCEPTED,
            ),
        )

    @override
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    @validate.lazy(validate_spec)
    async def post(self, parsed_body: Body[WebLoginPost]) -> HttpResponse:
        return await self.login(parsed_body)

    @override
    @sensitive_variables()
    async def login(self, parsed_body: WebLoginPost) -> HttpResponse:
        # the browser holds a cookie session, so the credentials alone are
        # not proof that the client meant to send this request
        self.check_csrf()

        user: ApiUser = await authenticate_user(
            request=self.request,
            **await self.convert_auth_payload(parsed_body),
        )

        session: EncodedJwtPair | str = await open_session(user)

        self.rotate_csrf_token()

        if isinstance(session, EncodedJwtPair):
            return self.to_response(
                WebLoginResponse(user=instance_mapper(user, ApiUserInlineGet)),
                cookies=self.token_cookies(session),
                headers=self.response_headers(),
                status_code=self.response_status_code,
            )

        return self.to_response(
            WebChallengeResponse(expires_in=CHALLENGE_LIFETIME),
            cookies=self.challenge_cookie(session),
            headers=self.response_headers(),
            status_code=HTTPStatus.ACCEPTED,
        )

    @override
    @sensitive_variables()
    async def convert_auth_payload(self, payload: WebLoginPost) -> ObtainTokensPayload:
        return {"password": payload.password, "username": payload.username}
