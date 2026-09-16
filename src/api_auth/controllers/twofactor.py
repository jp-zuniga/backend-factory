from http import HTTPStatus

from django.http import HttpResponse
from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)
from dmr import Body, Cookies, ResponseSpec, modify, validate
from dmr.decorators import endpoint_decorator
from dmr.endpoint import ValidateAnyCallable
from dmr.security.jwt.auth import set_request_attrs

from api_auth.enums import TokenTypes
from api_auth.models import ApiUser, ApiUserTotpDevice
from api_auth.schemas.login import MobileLoginResponse, WebLoginResponse
from api_auth.schemas.twofactor import (
    MobileTwoFactorPost,
    TwoFactorCodePost,
    TwoFactorDisablePost,
    TwoFactorRecoveryResponse,
    TwoFactorSetupResponse,
    TwoFactorStatusGet,
    WebChallengeCookies,
    WebTwoFactorPost,
)
from api_auth.schemas.user import ApiUserInlineGet
from api_auth.services.jwt import EncodedJwtPair, build_jwt_pair
from api_auth.services.session import resolve_challenge
from api_auth.services.twofactor import (
    TotpEnrollment,
    confirm_enrollment,
    count_recovery_codes,
    disable_two_factor,
    find_device,
    rotate_recovery_codes,
    start_enrollment,
)
from api_core.controllers.serializers import CustomPydanticFastSerializer
from api_core.services.mappers import instance_mapper

from .base import (
    NO_STORE_HEADERS,
    CookieTokensMixin,
    MobileAuthController,
    PrivateAuthController,
    WebAuthController,
    discarded_spec,
)

########################################################################################


class MobileTwoFactorController(MobileAuthController[CustomPydanticFastSerializer]):
    """
    Trade a challenge token and a second factor code for a token pair.
    """

    @modify(headers=NO_STORE_HEADERS, status_code=HTTPStatus.OK)
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    async def post(self, parsed_body: Body[MobileTwoFactorPost]) -> MobileLoginResponse:
        user: ApiUser = await resolve_challenge(
            parsed_body.challenge,
            parsed_body.code,
        )

        set_request_attrs(self.request, user)

        tokens: EncodedJwtPair = build_jwt_pair(user)

        return MobileLoginResponse(
            access=tokens.access,
            refresh=tokens.refresh,
            user=instance_mapper(user, ApiUserInlineGet),
        )


########################################################################################


class WebTwoFactorController(
    WebAuthController[CustomPydanticFastSerializer],
    CookieTokensMixin,
):
    """
    The same exchange, with the challenge and the tokens in cookies.

    `dmr` ships no controller for this step, so the flow is spelled out
    here; every cookie it writes still comes from `CookieTokensMixin`,
    which is what the rest of the web flow uses.
    """

    @classmethod
    def validate_spec(cls) -> ValidateAnyCallable:
        return validate(
            ResponseSpec(
                return_type=WebLoginResponse,
                cookies={
                    TokenTypes.CHALLENGE: discarded_spec(cls.challenge_cookie_spec()),
                    **cls.issued_cookies_spec(),
                    **cls.csrf_cookie_spec(),
                },
                headers=cls.response_headers_spec(),
                status_code=HTTPStatus.OK,
            ),
        )

    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    @validate.lazy(validate_spec)
    async def post(
        self,
        parsed_body: Body[WebTwoFactorPost],
        parsed_cookies: Cookies[WebChallengeCookies],
    ) -> HttpResponse:
        self.check_csrf()

        user: ApiUser = await resolve_challenge(
            parsed_cookies.challenge,
            parsed_body.code,
        )

        set_request_attrs(self.request, user)

        self.rotate_csrf_token()

        return self.to_response(
            WebLoginResponse(user=instance_mapper(user, ApiUserInlineGet)),
            cookies={
                **self.issue_cookies(),
                **self.discarded_challenge_cookie(),
            },
            headers=self.response_headers(),
            status_code=HTTPStatus.OK,
        )


########################################################################################


class TwoFactorController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.OK)
    async def get(self) -> TwoFactorStatusGet:
        device: ApiUserTotpDevice | None = await find_device(self.request.user)

        return TwoFactorStatusGet(
            confirmed_at=(device.confirmed_at if device is not None else None),  # ty: ignore[invalid-argument-type]
            enabled=device is not None and device.confirmed_at is not None,
            pending=device is not None and device.confirmed_at is None,
            recovery_codes=await count_recovery_codes(device),
        )


########################################################################################


class TwoFactorSetupController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(
        headers=NO_STORE_HEADERS,
        status_code=HTTPStatus.CREATED,
    )
    @sensitive_variables()
    async def post(self) -> TwoFactorSetupResponse:
        enrollment: TotpEnrollment = await start_enrollment(self.request.user)

        return TwoFactorSetupResponse(secret=enrollment.secret, uri=enrollment.uri)


########################################################################################


class TwoFactorConfirmController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(
        headers=NO_STORE_HEADERS,
        status_code=HTTPStatus.CREATED,
    )
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    async def post(
        self,
        parsed_body: Body[TwoFactorCodePost],
    ) -> TwoFactorRecoveryResponse:
        return TwoFactorRecoveryResponse(
            codes=tuple(await confirm_enrollment(self.request.user, parsed_body.code)),
        )


########################################################################################


class TwoFactorRecoveryController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(
        headers=NO_STORE_HEADERS,
        status_code=HTTPStatus.CREATED,
    )
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    async def post(
        self,
        parsed_body: Body[TwoFactorCodePost],
    ) -> TwoFactorRecoveryResponse:
        return TwoFactorRecoveryResponse(
            codes=tuple(
                await rotate_recovery_codes(self.request.user, parsed_body.code),
            ),
        )


########################################################################################


class TwoFactorDisableController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.NO_CONTENT)
    @sensitive_variables()
    @endpoint_decorator(sensitive_post_parameters())
    async def post(self, parsed_body: Body[TwoFactorDisablePost]) -> None:
        await disable_two_factor(
            code=parsed_body.code,
            password=parsed_body.password,
            user=self.request.user,
        )
