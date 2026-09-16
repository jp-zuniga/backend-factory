from typing import TYPE_CHECKING, override

from dmr.exceptions import NotAuthenticatedError
from dmr.openapi.objects import SecurityScheme
from dmr.security.jwt.auth import CookieJWTAsyncAuth, HeaderJWTAsyncAuth
from dmr.security.jwt.auth.base import BaseJWTAsyncAuth

from api_auth.services.blocklist import find_blocklisted_jtis
from api_auth.services.csrf import ensure_csrf
from api_auth.services.jwt import jwt_lookup_keys
from api_auth.services.permissions import ensure_model_permissions
from api_core.config import CONFIG
from api_middlewares.history import build_user_context

if TYPE_CHECKING:
    from typing import Self

    from django.contrib.auth.base_user import AbstractBaseUser
    from dmr import Controller
    from dmr.endpoint import Endpoint
    from dmr.openapi.objects import Reference, SecurityRequirement
    from dmr.security.jwt import JWToken

########################################################################################

CSRF_SCHEME_NAME: str = "csrf"

########################################################################################


class JwtRbacAsyncAuth(BaseJWTAsyncAuth):
    """
    The transport-agnostic half of this API's jwt authentication.

    `dmr` already decodes the token, rejects anything that is not an
    access token, and loads an active user out of `sub`. On top of that
    we refuse revoked sessions, apply the controller's model permissions,
    and hand the user over to `pghistory`.
    """

    __slots__ = ()

    @override
    async def __call__(
        self,
        endpoint: Endpoint,
        controller: Controller,
    ) -> Self | None:
        authed: Self | None = await super().__call__(endpoint, controller)

        if authed is None:
            return None

        # user has been authenticated or rejected by now,
        # `controller.request` should be "usable" (see `api_utils.types`)
        await ensure_model_permissions(controller, controller.request)  # ty: ignore[invalid-argument-type]
        await build_user_context(controller.request)  # ty: ignore[invalid-argument-type]

        return authed

    @override
    async def check_auth(
        self,
        user: AbstractBaseUser,
        token: JWToken,
    ) -> None:
        await super().check_auth(user, token)

        # a token is also dead when its session was revoked as a whole,
        # so both keys are looked up at once instead of letting
        # `JWTokenBlocklistAsyncMixin` spend a query on the `jti` alone
        if await find_blocklisted_jtis(jwt_lookup_keys(token)):
            raise NotAuthenticatedError


########################################################################################


class JwtCookieAsyncAuth(JwtRbacAsyncAuth, CookieJWTAsyncAuth):
    """
    Reads the access token from its cookie, for browser clients.
    """

    __slots__ = ()

    @property
    @override
    def security_requirement(self) -> SecurityRequirement:
        return {CSRF_SCHEME_NAME: [], **super().security_requirement}

    @property
    @override
    def security_schemes(self) -> dict[str, SecurityScheme | Reference]:
        return {
            CSRF_SCHEME_NAME: SecurityScheme(
                name=CONFIG.csrf_header,
                security_scheme_in="header",
                type="apiKey",
            ),
            self.security_scheme_name: SecurityScheme(
                name=self.cookie_name,
                security_scheme_in="cookie",
                type="apiKey",
            ),
        }

    @override
    def _ensure_csrf(self, controller: Controller) -> None:
        if self.get_token_from_request(controller.request):
            ensure_csrf(controller.request)


########################################################################################


class JwtHeaderAsyncAuth(JwtRbacAsyncAuth, HeaderJWTAsyncAuth):
    """
    Reads the access token from `Authorization: Bearer`, for native clients.
    """

    __slots__ = ()

    @property
    @override
    def security_schemes(self) -> dict[str, SecurityScheme | Reference]:
        return {
            self.security_scheme_name: SecurityScheme(
                bearer_format="JWT",
                scheme=self.auth_scheme,
                type="http",
            ),
        }
