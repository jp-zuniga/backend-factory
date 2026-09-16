from http import HTTPStatus
from typing import override

from django.http import HttpResponse
from django.views.decorators.debug import sensitive_variables
from dmr import Body, CookieSpec, Cookies, ResponseSpec, modify, validate
from dmr.security.jwt.auth import set_request_attrs

from api_auth.enums import TokenTypes
from api_auth.models import ApiUserTotpDevice
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
from api_auth.services.cookies import build_cookied_response, unset_jwt_cookie
from api_auth.services.jwt import JwtSession
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

from .base import MobileAuthController, PrivateAuthController, WebAuthController

########################################################################################


class MobileTwoFactorController(MobileAuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.OK)
    @sensitive_variables()
    async def post(self, parsed_body: Body[MobileTwoFactorPost]) -> MobileLoginResponse:
        session: JwtSession = await resolve_challenge(
            parsed_body.challenge,
            parsed_body.code,
        )

        set_request_attrs(self.request, session.user)

        return MobileLoginResponse(
            access=session.tokens.access,
            refresh=session.tokens.refresh,
            user=instance_mapper(session.user, ApiUserInlineGet),
        )


########################################################################################


class WebTwoFactorController(WebAuthController[CustomPydanticFastSerializer]):
    @override
    @sensitive_variables()
    @validate(
        ResponseSpec(
            cookies={
                TokenTypes.ACCESS: CookieSpec(skip_validation=True),
                TokenTypes.CHALLENGE: CookieSpec(skip_validation=True),
                TokenTypes.REFRESH: CookieSpec(skip_validation=True),
            },
            return_type=WebLoginResponse,
            status_code=HTTPStatus.OK,
        ),
        validate_responses=False,
    )
    async def post(
        self,
        parsed_body: Body[WebTwoFactorPost],
        parsed_cookies: Cookies[WebChallengeCookies],
    ) -> HttpResponse:
        await super().post()

        session: JwtSession = await resolve_challenge(
            parsed_cookies.challenge,
            parsed_body.code,
        )

        set_request_attrs(self.request, session.user)

        response: HttpResponse = build_cookied_response(
            ctrl=self,
            data=WebLoginResponse(
                user=instance_mapper(session.user, ApiUserInlineGet),
            ),
            tokens=session.tokens,
        )

        unset_jwt_cookie(TokenTypes.CHALLENGE, response)

        return response


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
    @modify(status_code=HTTPStatus.CREATED)
    @sensitive_variables()
    async def post(self) -> TwoFactorSetupResponse:
        enrollment: TotpEnrollment = await start_enrollment(self.request.user)

        return TwoFactorSetupResponse(secret=enrollment.secret, uri=enrollment.uri)


########################################################################################


class TwoFactorConfirmController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.CREATED)
    @sensitive_variables()
    async def post(
        self,
        parsed_body: Body[TwoFactorCodePost],
    ) -> TwoFactorRecoveryResponse:
        return TwoFactorRecoveryResponse(
            codes=tuple(await confirm_enrollment(self.request.user, parsed_body.code)),
        )


########################################################################################


class TwoFactorRecoveryController(PrivateAuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.CREATED)
    @sensitive_variables()
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
    async def post(self, parsed_body: Body[TwoFactorDisablePost]) -> None:
        await disable_two_factor(
            code=parsed_body.code,
            password=parsed_body.password,
            user=self.request.user,
        )
