from base64 import b32decode, b32encode
from hashlib import sha1, sha256
from hmac import (
    compare_digest,
    new as build_hmac,
)
from secrets import token_bytes
from time import time
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

from api_core.config import CONFIG

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

########################################################################################

RECOVERY_BYTES: Final[int] = 10
RECOVERY_CHUNK: Final[int] = 4
SECRET_BYTES: Final[int] = 20

TRUNCATION_MASK: Final[int] = 0x7FFFFFFF

########################################################################################


def build_secret() -> str:
    return b32encode(token_bytes(SECRET_BYTES)).decode().rstrip("=")


########################################################################################


def decode_secret(secret: str) -> bytes:
    return b32decode(s=f"{secret}{'=' * (-len(secret) % 8)}", casefold=True)


########################################################################################


def build_provisioning_uri(secret: str, username: str) -> str:
    label: str = quote(string=f"{CONFIG.TOTP_ISSUER}:{username}", safe="")

    params: str = urlencode({
        "algorithm": "SHA1",
        "digits": CONFIG.TOTP_DIGITS,
        "issuer": CONFIG.TOTP_ISSUER,
        "period": CONFIG.TOTP_PERIOD,
        "secret": secret,
    })

    return f"otpauth://totp/{label}?{params}"


########################################################################################


def current_step() -> int:
    return int(time()) // CONFIG.TOTP_PERIOD


########################################################################################


def build_totp(secret: str, step: int) -> str:
    digest: bytes = build_hmac(
        decode_secret(secret),
        step.to_bytes(length=8, byteorder="big"),
        sha1,
    ).digest()

    offset: int = digest[-1] & 0x0F

    truncated: int = int.from_bytes(
        bytes=digest[offset : offset + 4],
        byteorder="big",
    )

    code: int = (truncated & TRUNCATION_MASK) % 10**CONFIG.TOTP_DIGITS

    return str(code).rjust(CONFIG.TOTP_DIGITS, "0")


########################################################################################


def match_totp(code: str, secret: str, after: int = 0) -> int | None:
    """
    Find the time step that a one-time code belongs to.

    Steps at or before *after* are rejected so that a code
    can never be replayed within its tolerance window.

    Args:
        code: The one-time code to verify.
        secret: The device's shared secret.
        after: The last step already spent by the device.

    Returns:
        The matched step, or `None` when the code is not valid.

    """

    if len(code) != CONFIG.TOTP_DIGITS or not (code.isascii() and code.isdigit()):
        return None

    step: int = current_step()

    for candidate in range(
        max(step - CONFIG.TOTP_TOLERANCE, after + 1),
        step + CONFIG.TOTP_TOLERANCE + 1,
    ):
        if compare_digest(build_totp(secret, candidate), code):
            return candidate

    return None


########################################################################################


def normalize_recovery_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").upper()


########################################################################################


def hash_recovery_code(code: str) -> str:
    return build_hmac(
        CONFIG.SECRET_KEY.get_secret_value().encode(),
        normalize_recovery_code(code).encode(),
        sha256,
    ).hexdigest()


########################################################################################


def build_recovery_code() -> str:
    raw: str = b32encode(token_bytes(RECOVERY_BYTES)).decode().rstrip("=")

    return "-".join(
        raw[start : start + RECOVERY_CHUNK]
        for start in range(0, len(raw), RECOVERY_CHUNK)
    )


########################################################################################


def build_recovery_codes() -> Sequence[str]:
    return tuple(build_recovery_code() for _ in range(CONFIG.TOTP_RECOVERY_CODES))
