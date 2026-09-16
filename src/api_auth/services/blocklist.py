from typing import TYPE_CHECKING, Final

from dmr.security.jwt.blocklist.models import BlocklistedJWToken

from api_exceptions.errors import UnauthorizedError

from .jwt import (
    find_jwt_subject,
    jwt_lookup_keys,
    jwt_revocation_expiry,
    jwt_revocation_key,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet
    from dmr.security.jwt.token import JWToken

    from api_auth.models import ApiUser

    from .jwt import ParsedJwtPair

########################################################################################

REVOKED_DETAIL: Final[str] = "El token proporcionado ya fue revocado."

########################################################################################


async def blocklist_jwt_pair(pair: ParsedJwtPair, user: ApiUser | None = None) -> None:
    await blocklist_jwts(
        pair.tokens,
        user if user is not None else await find_jwt_subject(pair.optional_subject()),
    )


########################################################################################


async def blocklist_jwts(
    tokens: Sequence[JWToken],
    user: ApiUser | None = None,
) -> None:
    if not tokens:
        return

    await BlocklistedJWToken.objects.abulk_create(  # ty:ignore[unresolved-attribute]
        [
            BlocklistedJWToken(
                expires_at=jwt_revocation_expiry(token),
                jti=jwt_revocation_key(token),
                user=user,
            )
            for token in tokens
        ],
        ignore_conflicts=True,
    )


########################################################################################


async def consume_jwt(token: JWToken, user: ApiUser | None = None) -> bool:
    _, created = await BlocklistedJWToken.objects.aget_or_create(  # ty:ignore[unresolved-attribute]
        jti=jwt_revocation_key(token),
        defaults={
            "expires_at": jwt_revocation_expiry(token),
            "user": user,
        },
    )

    return created


########################################################################################


async def ensure_active_jwts(tokens: Sequence[JWToken]) -> None:
    # a token is also dead when its session was revoked as a whole,
    # which is what logging out blocklists
    if await find_blocklisted_jtis(
        frozenset(key for token in tokens for key in jwt_lookup_keys(token)),
    ):
        raise UnauthorizedError(detail=REVOKED_DETAIL)


########################################################################################


async def find_blocklisted_jtis(jtis: frozenset[str | None]) -> frozenset[str]:
    if not jtis:
        return frozenset()

    qs: QuerySet = BlocklistedJWToken.objects.filter(jti__in=jtis).values_list(  # ty:ignore[unresolved-attribute]
        "jti",
        flat=True,
    )

    return frozenset([jti async for jti in qs])
