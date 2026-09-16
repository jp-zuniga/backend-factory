from collections.abc import Sequence
from typing import ClassVar

from dmr import Controller
from dmr.endpoint import Endpoint
from dmr.parsers import Parser
from dmr.plugins.msgspec import MsgspecJsonParser, MsgspecJsonRenderer
from dmr.renderers import Renderer
from dmr.serializer import BaseSerializer
from dmr.throttling import AsyncThrottle, Rate

from api_auth.enums import TokenTypes
from api_auth.security import JwtCookieAsyncAuth, JwtHeaderAsyncAuth, JwtRbacAsyncAuth
from api_auth.services.jwt import REQUIRED_CLAIMS
from api_core.config import CONFIG
from api_exceptions.schemas import ApiErrorResponse
from api_utils.types import UsableHttpRequest

from .endpoints import PathOperationIdEndpoint
from .mixins import HandleNotAllowedMixin
from .throttles import build_throttle

########################################################################################


class BaseController[Serializer: BaseSerializer](
    HandleNotAllowedMixin,
    Controller[Serializer],
):
    auth: ClassVar[Sequence[JwtRbacAsyncAuth]] = (
        JwtCookieAsyncAuth(
            algorithm=CONFIG.JWT_ALGORITHM,
            cookie_name=TokenTypes.ACCESS,
            require_claims=REQUIRED_CLAIMS,
            secret=CONFIG.JWT_SECRET_KEY.get_secret_value(),
            security_scheme_name="jwtCookie",
        ),
        JwtHeaderAsyncAuth(
            algorithm=CONFIG.JWT_ALGORITHM,
            require_claims=REQUIRED_CLAIMS,
            secret=CONFIG.JWT_SECRET_KEY.get_secret_value(),
            security_scheme_name="jwtHeader",
        ),
    )

    endpoint_cls: ClassVar[type[Endpoint]] = PathOperationIdEndpoint

    error_model: ClassVar[type[ApiErrorResponse]] = ApiErrorResponse

    namespace: ClassVar[str] = ""
    variant: ClassVar[str] = ""

    parsers: ClassVar[Sequence[Parser]] = (MsgspecJsonParser(),)
    renderers: ClassVar[Sequence[Renderer]] = (MsgspecJsonRenderer(),)

    request: UsableHttpRequest

    throttling: ClassVar[Sequence[AsyncThrottle]] = (
        build_throttle(10, Rate.second),
        build_throttle(100, Rate.minute),
        build_throttle(1000, Rate.hour),
    )
