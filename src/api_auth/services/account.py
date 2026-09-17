from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.db.transaction import atomic
from django.utils.timezone import now
from django.views.decorators.debug import sensitive_variables

from api_auth.enums import VerificationPurposes
from api_auth.models import ApiUser
from api_core.config import CONFIG
from api_exceptions.errors import ForbiddenError

from .verification import claim_code, issue_code, reject_code

if TYPE_CHECKING:
    from typing import Final

    from api_auth.models import VerificationCode

########################################################################################

UNVERIFIED_DETAIL: Final[str] = (
    "Debe confirmar su correo electrónico antes de iniciar sesión."
)

########################################################################################


def ensure_email_verified(user: ApiUser) -> None:
    if (
        CONFIG.REQUIRE_EMAIL_VERIFICATION
        and user.email
        and user.email_verified_at is None
    ):
        raise ForbiddenError(detail=UNVERIFIED_DETAIL)


########################################################################################


@sensitive_variables()
def settle_email(token: str) -> ApiUser:
    """
    Spend an email verification code and mark its account as verified.

    Args:
        token: The raw token received from the client.

    Returns:
        The account that owns the code.

    Raises:
        reject_code: When the token is not live, or when its address
                     is no longer the account's address.

    """

    with atomic():
        code: VerificationCode = claim_code(token, VerificationPurposes.EMAIL)

        user: ApiUser = code.api_user  # ty: ignore[invalid-assignment]

        # the address may have changed after the code was issued
        if user.email.casefold() != code.email.casefold():  # ty: ignore[unresolved-attribute]
            raise reject_code()

        ApiUser.objects.filter(
            email_verified_at__isnull=True,
            pk=user.pk,
        ).update(email_verified_at=now())

        return user


########################################################################################


@sensitive_variables()
async def confirm_email(token: str) -> ApiUser:
    return await sync_to_async(func=settle_email)(token)


########################################################################################


async def issue_email_verification(user: ApiUser) -> None:
    if not user.email or user.email_verified_at is not None:
        return

    await issue_code(
        email=user.email,
        purpose=VerificationPurposes.EMAIL,
        user=user,
    )


########################################################################################


async def resend_verification(email: str) -> None:
    """
    Send a new verification code to an address, if it still needs one.

    Nothing is ever reported back to the client, so that the endpoint
    cannot be used to find out which addresses are registered.

    Args:
        email: The address that requested a new code.

    """

    user: ApiUser | None = await ApiUser.objects.filter(
        email__iexact=email,
        email_verified_at__isnull=True,
        is_active=True,
    ).afirst()

    if user is None:
        return

    await issue_email_verification(user)
