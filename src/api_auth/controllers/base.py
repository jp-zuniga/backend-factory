from dataclasses import replace
from datetime import timedelta
from typing import ClassVar, Literal

from django.middleware.csrf import rotate_token
from dmr import CookieSpec, HeaderSpec, NewCookie, ResponseSpec
from dmr.headers import NewHeader
from dmr.security.base import NO_STORE_HEADERS as DMR_NO_STORE_HEADERS
from dmr.serializer import BaseSerializer

from api_auth.enums import TokenTypes
from api_auth.services.csrf import csrf_headers, ensure_csrf
from api_auth.services.jwt import EncodedJwtPair, build_jwt_pair
from api_core.config import CONFIG
from api_core.controllers.base import BaseController
from api_core.controllers.mixins import PublicControllerMixin, StrictThrottlingMixin
from api_utils.types import UsableHttpRequest

########################################################################################

# `dmr` picks which headers keep credentials out of every cache, and what
# they are set to; only the wording a client reads in the schema is ours
NO_STORE_HEADERS: dict[str, NewHeader] = {
    name: replace(header, description=None)
    for name, header in DMR_NO_STORE_HEADERS.items()
}

# `@validate` describes these headers and we set them by hand; both halves
# are built from the same source, like `dmr` does it, so they cannot drift
NO_STORE_SPEC: dict[str, HeaderSpec] = {
    name: header.to_spec() for name, header in NO_STORE_HEADERS.items()
}

NO_STORE_VALUES: dict[str, str] = {
    name: header.value for name, header in NO_STORE_HEADERS.items()
}

CSRF_HEADER_SPEC: dict[str, HeaderSpec] = {
    CONFIG.csrf_header: HeaderSpec(),
}

########################################################################################


def discarded_spec(spec: CookieSpec) -> CookieSpec:
    return replace(
        spec,
        max_age=0,
    )


########################################################################################


class AuthController[Serializer: BaseSerializer](
    PublicControllerMixin,
    StrictThrottlingMixin,
    BaseController[Serializer],
):
    pass


########################################################################################


class PrivateAuthController[Serializer: BaseSerializer](
    StrictThrottlingMixin,
    BaseController[Serializer],
):
    pass


########################################################################################


class MobileAuthController[Serializer: BaseSerializer](AuthController[Serializer]):
    namespace: ClassVar[str] = "mobile"
    variant: ClassVar[str] = "Mobile"


########################################################################################


class WebAuthController[Serializer: BaseSerializer](AuthController[Serializer]):
    namespace: ClassVar[str] = "web"
    variant: ClassVar[str] = "Web"


########################################################################################


class JwtSettingsMixin:
    """
    Every jwt setting this API applies to a `dmr` controller that signs.

    `dmr` reads these attributes off the controller class, so they are the
    single place where the lifetimes and the signing key are chosen.
    """

    jwt_algorithm: ClassVar[str] = CONFIG.JWT_ALGORITHM
    jwt_expiration: ClassVar[timedelta] = CONFIG.JWT_ACCESS_LIFETIME
    jwt_refresh_expiration: ClassVar[timedelta] = CONFIG.JWT_REFRESH_LIFETIME
    jwt_secret: ClassVar[str | None] = CONFIG.JWT_SECRET_KEY.get_secret_value()
    jwt_user_id_field: ClassVar[str] = "pk"


########################################################################################


class CookieTokensMixin(JwtSettingsMixin):
    """
    How every controller that writes token cookies behaves in this API.

    This mixin only replaces the parts that have to match the rest of the API:

    - the CSRF check, so that a failure reads like every other error
    - the header that hands the CSRF token back, because the cookie
      carrying it is `httponly` and a browser client cannot read it
    - the descriptions a client reads in the schema
    - tokens that share a session id, so revoking one revokes the pair

    The cookie specs are spelled out here instead of being inherited, so
    that the one controller with no `dmr` cookie base -- the second factor
    one -- writes exactly the same cookies as the rest of the flow. All of
    them still read their flags off the attributes below.
    """

    request: UsableHttpRequest

    jwt_access_cookie: ClassVar[str] = TokenTypes.ACCESS
    jwt_refresh_cookie: ClassVar[str] = TokenTypes.REFRESH

    jwt_access_cookie_path: ClassVar[str] = "/"

    # `dmr` leaves this one without a default, so that the refresh token is
    # scoped to the endpoint that rotates it. Here it has to reach the whole
    # API: logging out and checking a session both read it back.
    jwt_refresh_cookie_path: ClassVar[str] = "/"

    jwt_cookie_domain: ClassVar[str | None] = None
    jwt_cookie_httponly: ClassVar[bool] = True
    jwt_cookie_secure: ClassVar[bool] = CONFIG.cookie_secure

    jwt_cookie_samesite: ClassVar[Literal["lax", "strict", "none"]] = (
        CONFIG.cookie_samesite_policy
    )

    jwt_ensure_csrf: ClassVar[bool] = True

    @classmethod
    def access_cookie_spec(cls) -> CookieSpec:
        return CookieSpec(
            domain=cls.jwt_cookie_domain,
            httponly=cls.jwt_cookie_httponly,
            max_age=int(cls.jwt_expiration.total_seconds()),
            path=cls.jwt_access_cookie_path,
            samesite=cls.jwt_cookie_samesite,
            secure=cls.jwt_cookie_secure,
        )

    @classmethod
    def refresh_cookie_spec(cls) -> CookieSpec:
        return CookieSpec(
            domain=cls.jwt_cookie_domain,
            httponly=cls.jwt_cookie_httponly,
            max_age=int(cls.jwt_refresh_expiration.total_seconds()),
            path=cls.jwt_refresh_cookie_path,
            samesite=cls.jwt_cookie_samesite,
            secure=cls.jwt_cookie_secure,
        )

    @classmethod
    def challenge_cookie_spec(cls) -> CookieSpec:
        return CookieSpec(
            domain=cls.jwt_cookie_domain,
            httponly=cls.jwt_cookie_httponly,
            max_age=int(CONFIG.JWT_CHALLENGE_LIFETIME.total_seconds()),
            path=cls.jwt_access_cookie_path,
            samesite=cls.jwt_cookie_samesite,
            secure=cls.jwt_cookie_secure,
        )

    # both token cookies of a successful response
    @classmethod
    def issued_cookies_spec(cls) -> dict[str, CookieSpec]:
        return {
            cls.jwt_access_cookie: cls.access_cookie_spec(),
            cls.jwt_refresh_cookie: cls.refresh_cookie_spec(),
        }

    # every cookie this flow can ever set, as it is set
    @classmethod
    def settable_cookies_spec(cls) -> dict[str, CookieSpec]:
        return {
            TokenTypes.CHALLENGE: cls.challenge_cookie_spec(),
            **cls.issued_cookies_spec(),
        }

    # every cookie this flow can set, as it is sent back on logout
    @classmethod
    def discarded_cookies_spec(cls) -> dict[str, CookieSpec]:
        return {
            name: discarded_spec(spec)
            for name, spec in cls.settable_cookies_spec().items()
        }

    @classmethod
    def csrf_cookie_spec(cls) -> dict[str, CookieSpec]:
        """
        Describe the CSRF cookie that django sets after us.

        `CsrfViewMiddleware` writes it once the token is rotated, which
        happens after our own validation has run; that is why it is only
        ever documented and never validated.

        Returns:
            The cookie, keyed by the name django writes it under.

        """

        return {
            CONFIG.csrf_cookie_name: CookieSpec(skip_validation=True),
        }

    @classmethod
    def csrf_response_specs(cls) -> tuple[ResponseSpec, ...]:
        """
        Drop `dmr`'s own description of a failed CSRF check.

        It carries the plain error model, while `Settings.responses`
        already describes `403` for every endpoint this API serves.

        Returns:
            Nothing at all, on purpose.

        """

        return ()

    @classmethod
    def response_headers_spec(cls) -> dict[str, HeaderSpec]:
        return {**NO_STORE_SPEC, **CSRF_HEADER_SPEC}

    def response_headers(self) -> dict[str, str]:
        return {**NO_STORE_VALUES, **csrf_headers(self.request)}

    def check_csrf(self) -> None:
        """
        Enforce CSRF, raising this API's error instead of `dmr`'s bare one.

        A browser sends these cookies on its own, so without this check
        any other site could act on a session that is not its own.
        """

        if self.jwt_ensure_csrf:
            ensure_csrf(self.request)

    def rotate_csrf_token(self) -> None:
        """Hand a freshly authed client a CSRF token of its own."""

        rotate_token(self.request)

    def token_cookies(self, tokens: EncodedJwtPair) -> dict[str, NewCookie]:
        return {
            self.jwt_access_cookie: NewCookie.from_spec(
                self.access_cookie_spec(),
                value=tokens.access,
            ),
            self.jwt_refresh_cookie: NewCookie.from_spec(
                self.refresh_cookie_spec(),
                value=tokens.refresh,
            ),
        }

    def challenge_cookie(self, challenge: str) -> dict[str, NewCookie]:
        return {
            TokenTypes.CHALLENGE: NewCookie.from_spec(
                self.challenge_cookie_spec(),
                value=challenge,
            ),
        }

    # the challenge cookie, sent back empty once it has been spent
    def discarded_challenge_cookie(self) -> dict[str, NewCookie]:
        return {
            TokenTypes.CHALLENGE: NewCookie.from_spec(
                discarded_spec(self.challenge_cookie_spec()),
                value="",
            ),
        }

    def issue_cookies(self) -> dict[str, NewCookie]:
        """
        Open a session for the user of this request.

        `dmr` mints the two tokens on their own; ours share a session id,
        so that revoking either one revokes the whole pair.

        Returns:
            Both token cookies, keyed by their cookie name.

        """

        return self.token_cookies(build_jwt_pair(self.request.user))

    # every cookie this flow can set, empty and already expired
    def discard_cookies(self) -> dict[str, NewCookie]:
        return {
            name: NewCookie.from_spec(spec, value="")
            for name, spec in self.discarded_cookies_spec().items()
        }
