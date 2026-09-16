from http import HTTPStatus
from typing import Final, override

from django.http import HttpResponse
from django.views.decorators.debug import sensitive_variables
from dmr import Body, CookieSpec, ResponseSpec, validate

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
from api_auth.services.cookies import build_challenged_response, build_cookied_response
from api_auth.services.jwt import EncodedJwtPair
from api_auth.services.session import open_session
from api_auth.services.user import authenticate_user
from api_core.config import CONFIG
from api_core.controllers.serializers import CustomPydanticFastSerializer
from api_core.services.mappers import instance_mapper

from .base import MobileAuthController, WebAuthController

########################################################################################

CHALLENGE_LIFETIME: Final[int] = int(CONFIG.JWT_CHALLENGE_LIFETIME.total_seconds())

########################################################################################


class MobileLoginController(MobileAuthController[CustomPydanticFastSerializer]):
    @sensitive_variables()
    @validate(
        ResponseSpec(return_type=MobileLoginResponse, status_code=HTTPStatus.OK),
        ResponseSpec(
            return_type=MobileChallengeResponse,
            status_code=HTTPStatus.ACCEPTED,
        ),
        validate_responses=False,
    )
    async def post(self, parsed_body: Body[MobileLoginPost]) -> HttpResponse:
        user: ApiUser = await authenticate_user(parsed_body, self.request)

        session: EncodedJwtPair | str = await open_session(user)

        if isinstance(session, EncodedJwtPair):
            return self.to_response(
                raw_data=MobileLoginResponse(
                    access=session.access,
                    refresh=session.refresh,
                    user=instance_mapper(user, ApiUserInlineGet),
                ),
                status_code=HTTPStatus.OK,
            )

        return self.to_response(
            raw_data=MobileChallengeResponse(
                challenge=session,
                expires_in=CHALLENGE_LIFETIME,
            ),
            status_code=HTTPStatus.ACCEPTED,
        )


########################################################################################


class WebLoginController(WebAuthController[CustomPydanticFastSerializer]):
    @override
    @sensitive_variables()
    @validate(
        ResponseSpec(
            cookies={
                TokenTypes.ACCESS: CookieSpec(skip_validation=True),
                TokenTypes.REFRESH: CookieSpec(skip_validation=True),
            },
            return_type=WebLoginResponse,
            status_code=HTTPStatus.OK,
        ),
        ResponseSpec(
            cookies={TokenTypes.CHALLENGE: CookieSpec(skip_validation=True)},
            return_type=WebChallengeResponse,
            status_code=HTTPStatus.ACCEPTED,
        ),
        validate_responses=False,
    )
    async def post(self, parsed_body: Body[WebLoginPost]) -> HttpResponse:
        await super().post()

        user: ApiUser = await authenticate_user(parsed_body, self.request)

        session: EncodedJwtPair | str = await open_session(user)

        if isinstance(session, EncodedJwtPair):
            return build_cookied_response(
                ctrl=self,
                data=WebLoginResponse(user=instance_mapper(user, ApiUserInlineGet)),
                tokens=session,
            )

        return build_challenged_response(
            challenge=session,
            ctrl=self,
            data=WebChallengeResponse(expires_in=CHALLENGE_LIFETIME),
        )
