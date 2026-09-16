from typing import TYPE_CHECKING

from api_auth.enums import TokenTypes
from api_exceptions.errors import UnauthorizedError

from .blocklist import (
    REVOKED_DETAIL,
    blocklist_jwt_pair,
    consume_jwt,
    ensure_active_jwts,
    find_blocklisted_jtis,
)
from .jwt import (
    ParsedJwtPair,
    build_challenge_jwt,
    build_jwt_pair,
    parse_jwt,
    parse_jwt_pair,
    resolve_jwt_subject,
)
from .twofactor import (
    INVALID_CODE_DETAIL,
    check_second_factor,
    find_device,
    has_two_factor,
)

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from dmr.security.jwt import JWToken

    from api_auth.models import ApiUser, ApiUserTotpDevice

    from .jwt import EncodedJwtPair

########################################################################################


async def close_session(access: str | None, refresh: str | None) -> None:
    await blocklist_jwt_pair(parse_jwt_pair(access, refresh))


########################################################################################


async def consume_refresh(refresh: JWToken, user: AbstractBaseUser) -> None:
    """
    Spend a refresh token, so that it can never buy a second session.

    Both tokens of a pair carry the same session id, and that is what
    the blocklist stores, so the access token handed out next to this
    one dies here as well.

    Args:
        refresh: The refresh token that is being rotated.
        user: The account the token was issued for.

    Raises:
        UnauthorizedError: When the token was already spent or revoked.

    """

    if not await consume_jwt(refresh, user):
        raise UnauthorizedError(detail=REVOKED_DETAIL)


########################################################################################


async def inspect_session(
    access: str | None,
    refresh: str | None,
) -> tuple[bool, bool]:
    pair: ParsedJwtPair = parse_jwt_pair(access, refresh)

    blocked: frozenset[str] = await find_blocklisted_jtis(pair.jtis)

    return (
        pair.access is not None and pair.access.jti not in blocked,
        pair.refresh is not None and pair.refresh.jti not in blocked,
    )


########################################################################################


async def open_session(user: ApiUser) -> EncodedJwtPair | str:
    """
    Start a session for an authenticated user.

    Args:
        user: The user that already proved its credentials.

    Returns:
        The session's token pair, or a challenge token when
        the user still has to provide its second factor.

    """

    if await has_two_factor(user):
        return build_challenge_jwt(user)

    return build_jwt_pair(user)


########################################################################################


async def resolve_challenge(challenge: str | None, code: str) -> ApiUser:
    """
    Trade a challenge token and a second factor code for an account.

    Args:
        challenge: The challenge token handed out by the login endpoint.
        code: A time based code or a recovery code.

    Returns:
        The account the challenge was issued for.

    Raises:
        UnauthorizedError: When the challenge was already spent,
            or when the second factor code is not valid.

    """

    token: JWToken = parse_jwt(challenge, TokenTypes.CHALLENGE)

    # a spent challenge must never consume a second factor code
    await ensure_active_jwts((token,))

    user: ApiUser = await resolve_jwt_subject(token.sub)

    device: ApiUserTotpDevice | None = await find_device(user)

    if device is None or device.confirmed_at is None:
        raise UnauthorizedError

    if not await check_second_factor(device, code):
        raise UnauthorizedError(detail=INVALID_CODE_DETAIL)

    if not await consume_jwt(token, user):
        raise UnauthorizedError(detail=REVOKED_DETAIL)

    return user


########################################################################################


async def verify_jwt(encoded: str | None, expected_type: str) -> None:
    await ensure_active_jwts((parse_jwt(encoded, expected_type),))
