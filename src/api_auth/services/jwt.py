from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NamedTuple
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError as DjangoValidationError,
)
from dmr.exceptions import NotAuthenticatedError
from dmr.security.jwt.token import JWToken

from api_auth.enums import TokenTypes
from api_core.config import CONFIG
from api_exceptions.errors import UnauthorizedError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta
    from typing import Final

    from api_auth.models import ApiUser

########################################################################################

REQUIRED_CLAIMS: Final[Sequence[str]] = ("exp", "jti", "sub")

SESSION_KEY_PREFIX: Final[str] = "sid:"

########################################################################################


class EncodedJwtPair(NamedTuple):
    access: str
    refresh: str


########################################################################################


@dataclass(frozen=True, slots=True)
class JwtSession:
    tokens: EncodedJwtPair
    user: ApiUser


########################################################################################


@dataclass(frozen=True, slots=True)
class ParsedJwtPair:
    access: JWToken | None = None
    refresh: JWToken | None = None

    @property
    def jtis(self) -> frozenset[str | None]:
        return frozenset(key for token in self.tokens for key in jwt_lookup_keys(token))

    @property
    def subjects(self) -> frozenset[str]:
        return frozenset(token.sub for token in self.tokens)

    @property
    def tokens(self) -> Sequence[JWToken]:
        return tuple(
            token for token in (self.access, self.refresh) if token is not None
        )

    def optional_subject(self) -> str | None:
        subjects: frozenset[str] = self.subjects

        return next(iter(subjects)) if len(subjects) == 1 else None

    def subject(self) -> str:
        subjects: frozenset[str] = self.subjects

        if len(subjects) > 1:
            raise UnauthorizedError(
                detail="Los tokens proporcionados le pertenecen a usuarios distintos.",
            )

        if not subjects:
            raise UnauthorizedError

        return next(iter(subjects))


########################################################################################


def decode_jwt(encoded: str, expected_type: str) -> JWToken:
    token: JWToken = JWToken.decode(
        algorithm=CONFIG.JWT_ALGORITHM,
        encoded_token=encoded,
        require_claims=REQUIRED_CLAIMS,
        secret=CONFIG.JWT_SECRET_KEY.get_secret_value(),
    )

    if token.extras.get("type") != expected_type:
        raise NotAuthenticatedError

    return token


########################################################################################


async def find_jwt_subject(sub: str | None) -> ApiUser | None:
    if sub is None:
        return None

    try:
        return await get_user_model().objects.filter(pk=sub).afirst()
    except DjangoValidationError, ValueError:
        return None


########################################################################################


def jwt_lookup_keys(token: JWToken) -> frozenset[str | None]:
    session: str | None = jwt_session_key(token)

    return (
        frozenset({token.jti}) if session is None else frozenset({token.jti, session})
    )


########################################################################################


def jwt_revocation_expiry(token: JWToken) -> datetime:
    if jwt_session_key(token) is None:
        return token.exp

    return token.iat + CONFIG.JWT_REFRESH_LIFETIME


########################################################################################


def jwt_revocation_key(token: JWToken) -> str | None:
    return jwt_session_key(token) or token.jti


########################################################################################


def jwt_session_key(token: JWToken) -> str | None:
    session: str | None = token.extras.get("sid")

    return f"{SESSION_KEY_PREFIX}{session}" if session is not None else None


########################################################################################


def build_challenge_jwt(user: ApiUser) -> str:
    return build_jwt(
        lifetime=CONFIG.JWT_CHALLENGE_LIFETIME,
        token_type=TokenTypes.CHALLENGE,
        user=user,
    )


########################################################################################


def build_jwt(
    *,
    lifetime: timedelta,
    session: str | None = None,
    token_type: str,
    user: ApiUser,
) -> str:
    extras: dict[str, str] = {"type": token_type}

    if session is not None:
        extras["sid"] = session

    return JWToken(
        sub=str(user.pk),
        exp=datetime.now(tz=UTC) + lifetime,
        jti=uuid4().hex,
        extras=extras,
    ).encode(
        algorithm=CONFIG.JWT_ALGORITHM,
        secret=CONFIG.JWT_SECRET_KEY.get_secret_value(),
    )


########################################################################################


def build_jwt_pair(user: ApiUser) -> EncodedJwtPair:
    session: str = uuid4().hex

    return EncodedJwtPair(
        access=build_jwt(
            lifetime=CONFIG.JWT_ACCESS_LIFETIME,
            session=session,
            token_type=TokenTypes.ACCESS,
            user=user,
        ),
        refresh=build_jwt(
            lifetime=CONFIG.JWT_REFRESH_LIFETIME,
            session=session,
            token_type=TokenTypes.REFRESH,
            user=user,
        ),
    )


########################################################################################


def parse_jwt(encoded: str | None, expected_type: str) -> JWToken:
    if encoded is None:
        raise UnauthorizedError

    try:
        return decode_jwt(encoded, expected_type)
    except (NotAuthenticatedError, ValueError) as e:
        raise UnauthorizedError from e


########################################################################################


def parse_jwt_pair(access: str | None, refresh: str | None) -> ParsedJwtPair:
    return ParsedJwtPair(
        access=try_parse_jwt(access, TokenTypes.ACCESS),
        refresh=try_parse_jwt(refresh, TokenTypes.REFRESH),
    )


########################################################################################


async def resolve_jwt_subject(sub: str) -> ApiUser:
    try:
        user: ApiUser = await get_user_model().objects.aget(pk=sub)
    except (DjangoValidationError, ObjectDoesNotExist, ValueError) as e:
        raise UnauthorizedError from e

    if not user.is_active:
        raise UnauthorizedError

    return user


########################################################################################


def try_parse_jwt(encoded: str | None, expected_type: str) -> JWToken | None:
    try:
        return parse_jwt(encoded, expected_type)
    except UnauthorizedError:
        return None
