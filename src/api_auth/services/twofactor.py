from dataclasses import dataclass
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.db.transaction import atomic
from django.utils.timezone import now
from django.views.decorators.debug import sensitive_variables

from api_auth.models import ApiUserRecoveryCode, ApiUserTotpDevice
from api_core.config import CONFIG
from api_exceptions.enums import BadRequestErrorTypes, RequestScopes
from api_exceptions.errors import BadRequestError, ConflictError, ThrottleExceededError

from .totp import (
    build_provisioning_uri,
    build_recovery_codes,
    build_secret,
    hash_recovery_code,
    match_totp,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final
    from uuid import UUID

    from api_auth.models import ApiUser

########################################################################################

DISABLED_DETAIL: Final[str] = "El segundo factor de autenticación no está activo."
ENABLED_DETAIL: Final[str] = "El segundo factor de autenticación ya está activo."
INVALID_CODE_DETAIL: Final[str] = "El código proporcionado no es válido."
INVALID_PASSWORD_DETAIL: Final[str] = "La contraseña proporcionada no es válida."  # ruff: ignore[hardcoded-password-string]

LOCKED_DETAIL: Final[str] = (
    "La verificación se bloqueó temporalmente por demasiados intentos fallidos."
)

MISSING_DEVICE_DETAIL: Final[str] = (
    "No hay una configuración de segundo factor asociada a esta cuenta."
)

########################################################################################


@dataclass(frozen=True, slots=True)
class TotpEnrollment:
    secret: str
    uri: str


########################################################################################


def reject_code() -> BadRequestError:
    return BadRequestError(
        field_errors={"code": INVALID_CODE_DETAIL},
        type=BadRequestErrorTypes.FAILED_VALIDATION,
    ).scoped(RequestScopes.BODY)


########################################################################################


async def find_device(user: ApiUser) -> ApiUserTotpDevice | None:
    return await ApiUserTotpDevice.objects.filter(api_user_id=user.pk).afirst()


########################################################################################


async def has_two_factor(user: ApiUser) -> bool:
    return await ApiUserTotpDevice.objects.filter(
        api_user_id=user.pk,
        confirmed_at__isnull=False,
    ).aexists()


########################################################################################


async def count_recovery_codes(device: ApiUserTotpDevice | None) -> int:
    if device is None:
        return 0

    return await ApiUserRecoveryCode.objects.filter(
        device_id=device.pk,
        used_at__isnull=True,
    ).acount()


########################################################################################


async def ensure_confirmed_device(user: ApiUser) -> ApiUserTotpDevice:
    device: ApiUserTotpDevice | None = await find_device(user)

    if device is None or device.confirmed_at is None:
        raise ConflictError(detail=DISABLED_DETAIL)

    return device


########################################################################################


def ensure_unlocked(device: ApiUserTotpDevice) -> None:
    if device.locked_until is not None and device.locked_until > now():
        raise ThrottleExceededError(detail=LOCKED_DETAIL)


########################################################################################


def register_failure(device: ApiUserTotpDevice) -> None:
    failures: int = device.failures + 1  # ty: ignore[unsupported-operator]

    if failures >= CONFIG.TOTP_MAX_FAILURES:
        device.failures = 0  # ty: ignore[invalid-assignment]
        device.locked_until = now() + CONFIG.TOTP_LOCKOUT
    else:
        device.failures = failures  # ty: ignore[invalid-assignment]
        device.locked_until = None  # ty: ignore[invalid-assignment]

    device.save(update_fields=("failures", "locked_until"))


########################################################################################


@sensitive_variables()
def spend_recovery_code(device_id: UUID, code: str) -> bool:
    return bool(
        ApiUserRecoveryCode.objects.filter(
            code=hash_recovery_code(code),
            device_id=device_id,
            used_at__isnull=True,
        ).update(used_at=now())
    )


########################################################################################


@sensitive_variables()
def spend_second_factor(device_id: UUID, code: str) -> bool:
    """
    Spend a one-time code against a device, locking its row.

    A code is only ever accepted once: time based codes advance
    the device's last step and recovery codes are marked as used.

    Args:
        device_id: The device that must verify the code.
        code: A time based code or a recovery code.

    Returns:
        Whether the code was accepted.

    """

    with atomic():
        device: ApiUserTotpDevice | None = (
            ApiUserTotpDevice.objects.select_for_update().filter(pk=device_id).first()
        )

        if device is None:
            return False

        ensure_unlocked(device)

        step: int | None = match_totp(
            code,
            device.secret,  # ty: ignore[invalid-argument-type]
            device.last_step,  # ty: ignore[invalid-argument-type]
        )

        if step is not None:
            device.last_step = step  # ty: ignore[invalid-assignment]
        elif not spend_recovery_code(device_id, code):
            register_failure(device)

            return False

        device.failures = 0  # ty: ignore[invalid-assignment]
        device.locked_until = None  # ty: ignore[invalid-assignment]

        device.save(update_fields=("failures", "last_step", "locked_until"))

        return True


########################################################################################


@sensitive_variables()
async def check_second_factor(device: ApiUserTotpDevice, code: str) -> bool:
    return await sync_to_async(func=spend_second_factor)(device.pk, code)


########################################################################################


@sensitive_variables()
def replace_recovery_codes(device_id: UUID, codes: Sequence[str]) -> None:
    with atomic():
        ApiUserRecoveryCode.objects.filter(device_id=device_id).delete()

        ApiUserRecoveryCode.objects.bulk_create([
            ApiUserRecoveryCode(code=hash_recovery_code(code), device_id=device_id)
            for code in codes
        ])


########################################################################################


@sensitive_variables()
async def issue_recovery_codes(device: ApiUserTotpDevice) -> Sequence[str]:
    codes: Sequence[str] = build_recovery_codes()

    await sync_to_async(func=replace_recovery_codes)(device.pk, codes)

    return codes


########################################################################################


@sensitive_variables()
def confirm_device(device_id: UUID, codes: Sequence[str]) -> None:
    with atomic():
        ApiUserTotpDevice.objects.filter(
            confirmed_at__isnull=True,
            pk=device_id,
        ).update(confirmed_at=now())

        replace_recovery_codes(device_id, codes)


########################################################################################


@sensitive_variables()
async def start_enrollment(user: ApiUser) -> TotpEnrollment:
    device: ApiUserTotpDevice | None = await find_device(user)

    if device is not None and device.confirmed_at is not None:
        raise ConflictError(detail=ENABLED_DETAIL)

    secret: str = build_secret()

    await ApiUserTotpDevice.objects.aupdate_or_create(
        api_user_id=user.pk,
        defaults={
            "failures": 0,
            "last_step": 0,
            "locked_until": None,
            "secret": secret,
        },
    )

    return TotpEnrollment(
        secret=secret,
        uri=build_provisioning_uri(secret, user.username),  # ty: ignore[invalid-argument-type]
    )


########################################################################################


@sensitive_variables()
async def confirm_enrollment(user: ApiUser, code: str) -> Sequence[str]:
    device: ApiUserTotpDevice | None = await find_device(user)

    if device is None:
        raise ConflictError(detail=MISSING_DEVICE_DETAIL)
    if device.confirmed_at is not None:
        raise ConflictError(detail=ENABLED_DETAIL)

    if not await check_second_factor(device, code):
        raise reject_code()

    codes: Sequence[str] = build_recovery_codes()

    await sync_to_async(func=confirm_device)(device.pk, codes)

    return codes


########################################################################################


@sensitive_variables()
async def rotate_recovery_codes(user: ApiUser, code: str) -> Sequence[str]:
    device: ApiUserTotpDevice = await ensure_confirmed_device(user)

    if not await check_second_factor(device, code):
        raise reject_code()

    return await issue_recovery_codes(device)


########################################################################################


@sensitive_variables()
async def disable_two_factor(*, code: str, password: str, user: ApiUser) -> None:
    device: ApiUserTotpDevice = await ensure_confirmed_device(user)

    if not await sync_to_async(func=user.check_password)(password):
        raise BadRequestError(
            field_errors={"password": INVALID_PASSWORD_DETAIL},
            type=BadRequestErrorTypes.FAILED_VALIDATION,
        ).scoped(RequestScopes.BODY)

    if not await check_second_factor(device, code):
        raise reject_code()

    await ApiUserTotpDevice.objects.filter(pk=device.pk).adelete()
