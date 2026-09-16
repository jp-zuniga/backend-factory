from http import HTTPStatus
from typing import TYPE_CHECKING

from dmr.negotiation import request_renderer
from dmr.response import build_response

from api_auth.enums import TokenTypes
from api_core.config import CONFIG
from api_core.controllers.serializers import CustomPydanticFastSerializer

from .csrf import attach_csrf

if TYPE_CHECKING:
    from datetime import timedelta

    from django.http import HttpRequest, HttpResponse
    from dmr import Controller

    from api_core.schemas.base import DTO

    from .jwt import EncodedJwtPair

########################################################################################


def build_cookied_response(
    *,
    ctrl: Controller,
    data: DTO | None = None,
    status: HTTPStatus = HTTPStatus.OK,
    tokens: EncodedJwtPair,
) -> HttpResponse:
    response: HttpResponse = build_response(
        raw_data=data,
        renderer=request_renderer(ctrl.request),
        serializer=ctrl.serializer,
        status_code=status,
    )

    set_jwt_cookie(
        key=TokenTypes.ACCESS,
        lifetime=CONFIG.JWT_ACCESS_LIFETIME,
        response=response,
        value=tokens.access,
    )

    set_jwt_cookie(
        key=TokenTypes.REFRESH,
        lifetime=CONFIG.JWT_REFRESH_LIFETIME,
        response=response,
        value=tokens.refresh,
    )

    return attach_csrf(response, ctrl.request)


########################################################################################


def build_challenged_response(
    *,
    challenge: str,
    ctrl: Controller,
    data: DTO | None = None,
) -> HttpResponse:
    response: HttpResponse = build_response(
        raw_data=data,
        renderer=request_renderer(ctrl.request),
        serializer=ctrl.serializer,
        status_code=HTTPStatus.ACCEPTED,
    )

    set_jwt_cookie(
        key=TokenTypes.CHALLENGE,
        lifetime=CONFIG.JWT_CHALLENGE_LIFETIME,
        response=response,
        value=challenge,
    )

    return attach_csrf(response, ctrl.request)


########################################################################################


def build_cookieless_response(request: HttpRequest) -> HttpResponse:
    response: HttpResponse = build_response(
        raw_data=None,
        renderer=request_renderer(request),
        serializer=CustomPydanticFastSerializer,
        status_code=HTTPStatus.NO_CONTENT,
    )

    unset_jwt_cookie(TokenTypes.ACCESS, response)
    unset_jwt_cookie(TokenTypes.CHALLENGE, response)
    unset_jwt_cookie(TokenTypes.REFRESH, response)

    return attach_csrf(response, request)


########################################################################################


def set_jwt_cookie(
    key: str,
    lifetime: timedelta,
    response: HttpResponse,
    value: str,
) -> None:
    response.set_cookie(
        httponly=True,
        key=key,
        max_age=lifetime,
        samesite=CONFIG.cookie_samesite,
        secure=CONFIG.cookie_secure,
        value=value,
    )


########################################################################################


def unset_jwt_cookie(key: str, response: HttpResponse) -> None:
    response.set_cookie(
        expires="Thu, 01 Jan 1970 00:00:00 GMT",
        httponly=True,
        key=key,
        max_age=0,
        samesite=CONFIG.cookie_samesite,
        secure=CONFIG.cookie_secure,
        value="",
    )
