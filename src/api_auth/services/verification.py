from hashlib import sha256
from secrets import token_urlsafe
from typing import TYPE_CHECKING
from urllib.parse import quote

from asgiref.sync import sync_to_async
from django.db.transaction import atomic
from django.utils.timezone import now
from django.views.decorators.debug import sensitive_variables

from api_auth.enums import VerificationPurposes
from api_auth.models import VerificationCode
from api_core.config import CONFIG
from api_exceptions.enums import BadRequestErrorTypes, RequestScopes
from api_exceptions.errors import BadRequestError

from .mail import send_template

if TYPE_CHECKING:
    from datetime import datetime, timedelta
    from typing import Final

    from api_auth.models import ApiUser

########################################################################################

TOKEN_BYTES: Final[int] = 32

SECONDS_PER_HOUR: Final[int] = 3600

########################################################################################

FRONTEND_PATHS: Final[dict[VerificationPurposes, str]] = {
    VerificationPurposes.EMAIL: "verify-email",
}

LIFETIMES: Final[dict[VerificationPurposes, timedelta]] = {
    VerificationPurposes.EMAIL: CONFIG.EMAIL_VERIFICATION_LIFETIME,
}

########################################################################################


@sensitive_variables()
def build_link(purpose: VerificationPurposes, token: str) -> str:
    return (
        f"{CONFIG.frontend_url}/{FRONTEND_PATHS[purpose]}"
        f"?token={quote(string=token, safe='')}"
    )


########################################################################################


@sensitive_variables()
def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


########################################################################################


def reject_code() -> BadRequestError:
    return BadRequestError(
        field_errors={"token": "El enlace no es válido o ya expiró."},
        type=BadRequestErrorTypes.FAILED_VALIDATION,
    ).scoped(RequestScopes.BODY)


########################################################################################


def invalidate_live_codes(email: str, purpose: VerificationPurposes) -> int:
    return VerificationCode.objects.filter(
        consumed_at__isnull=True,
        email__iexact=email,
        invalidated_at__isnull=True,
        purpose=purpose,
    ).update(invalidated_at=now())


########################################################################################


@sensitive_variables()
def persist_code(
    email: str,
    lifetime: timedelta,
    purpose: VerificationPurposes,
    token: str,
    user: ApiUser,
) -> None:
    with atomic():
        invalidate_live_codes(email, purpose)

        VerificationCode.objects.create(
            api_user=user,
            email=email,
            expires_at=(now() + lifetime),
            purpose=purpose,
            token_hash=hash_token(token),
        )


########################################################################################


@sensitive_variables()
async def issue_code(
    email: str,
    purpose: VerificationPurposes,
    user: ApiUser,
) -> str:
    """
    Issue a single use code and mail it to an address.

    Any other live code issued to *email* for the same purpose
    is invalidated, so only the latest message ever works.

    Args:
        email: The address that must receive the code.
        purpose: What the code is going to be spent on.
        user: The account the code belongs to.

    Returns:
        The raw token, which is never stored.

    """

    lifetime: timedelta = LIFETIMES[purpose]

    token: str = token_urlsafe(TOKEN_BYTES)

    await sync_to_async(func=persist_code)(
        email=email,
        lifetime=lifetime,
        purpose=purpose,
        token=token,
        user=user,
    )

    await send_template(
        context={
            "hours": int(lifetime.total_seconds() // SECONDS_PER_HOUR),
            "link": build_link(purpose=purpose, token=token),
            "token": token,
        },
        purpose=purpose,
        to=email,
    )

    return token


########################################################################################


@sensitive_variables()
def claim_code(token: str, purpose: VerificationPurposes) -> VerificationCode:
    """
    Spend a live code, locking its row.

    Args:
        token: The raw token received from the client.
        purpose: The purpose the token must have been issued for.

    Returns:
        The code that was spent, with its account preloaded.

    Raises:
        reject_code: When no live code matches the token.

    """

    moment: datetime = now()

    with atomic():
        code: VerificationCode | None = (
            VerificationCode.objects
            .select_for_update(of=("self",))
            .select_related("api_user")
            .filter(
                consumed_at__isnull=True,
                expires_at__gt=moment,
                invalidated_at__isnull=True,
                purpose=purpose,
                token_hash=hash_token(token),
            )
            .first()
        )

        if code is None:
            raise reject_code()

        code.consumed_at = moment  # ty: ignore[invalid-assignment]

        code.save(update_fields=("consumed_at",))

        return code


########################################################################################


@sensitive_variables()
async def consume_code(token: str, purpose: VerificationPurposes) -> VerificationCode:
    return await sync_to_async(func=claim_code)(purpose=purpose, token=token)
