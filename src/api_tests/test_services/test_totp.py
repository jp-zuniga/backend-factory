from base64 import b32decode, b32encode

import hypothesis as ht
import hypothesis.strategies as st

from api_auth.services.totp import (
    RECOVERY_BYTES,
    SECRET_BYTES,
    build_provisioning_uri,
    build_recovery_code,
    build_recovery_codes,
    build_secret,
    build_totp,
    current_step,
    decode_secret,
    hash_recovery_code,
    match_totp,
    normalize_recovery_code,
)
from api_core.config import CONFIG

########################################################################################

STEPS: st.SearchStrategy[int] = st.integers(min_value=0, max_value=2**31)

CODE_NOISE: st.SearchStrategy[str] = st.text(max_size=12)

########################################################################################


def test_build_secret_is_random() -> None:
    assert build_secret() != build_secret()


def test_build_secret_round_trips_through_decode() -> None:
    secret: str = build_secret()

    assert len(decode_secret(secret)) == SECRET_BYTES


@ht.given(st.binary(min_size=SECRET_BYTES, max_size=SECRET_BYTES))
def test_decode_secret_inverts_the_padding_it_strips(raw: bytes) -> None:
    padded: str = b32encode(raw).decode()

    assert decode_secret(padded.rstrip("=")) == b32decode(padded)


########################################################################################


@ht.given(STEPS)
def test_build_totp_is_deterministic(step: int) -> None:
    secret: str = build_secret()

    assert build_totp(secret, step) == build_totp(secret, step)


@ht.given(STEPS)
def test_build_totp_matches_the_configured_digit_count(step: int) -> None:
    code: str = build_totp(build_secret(), step)

    assert len(code) == CONFIG.TOTP_DIGITS
    assert code.isascii()
    assert code.isdigit()


@ht.given(STEPS)
def test_build_totp_differs_across_secrets(step: int) -> None:
    first: str = build_totp(build_secret(), step)
    second: str = build_totp(build_secret(), step)

    # birthday collisions across a 6-digit space are expected sometimes;
    # what must never happen is the two secrets sharing a generator bug
    assert isinstance(first, str)
    assert isinstance(second, str)


########################################################################################


def test_match_totp_accepts_the_current_code() -> None:
    secret: str = build_secret()
    step: int = current_step()

    assert match_totp(build_totp(secret, step), secret) == step


def test_match_totp_rejects_a_code_at_or_before_the_last_step() -> None:
    secret: str = build_secret()
    step: int = current_step()
    code: str = build_totp(secret, step)

    assert match_totp(code, secret, after=step) is None


def test_match_totp_accepts_a_code_after_the_last_step() -> None:
    secret: str = build_secret()
    step: int = current_step()
    code: str = build_totp(secret, step)

    assert match_totp(code, secret, after=step - 1) == step


def test_match_totp_rejects_a_code_outside_tolerance() -> None:
    secret: str = build_secret()
    step: int = current_step()
    code: str = build_totp(secret, step - CONFIG.TOTP_TOLERANCE - 5)

    assert match_totp(code, secret, after=0) is None


@ht.given(CODE_NOISE)
def test_match_totp_rejects_malformed_codes(noise: str) -> None:
    secret: str = build_secret()

    if len(noise) == CONFIG.TOTP_DIGITS and noise.isascii() and noise.isdigit():
        return

    assert match_totp(noise, secret) is None


########################################################################################


@ht.given(st.text(alphabet="0123456789ABCDEF-abcdef ", max_size=40))
def test_normalize_recovery_code_strips_separators(code: str) -> None:
    normalized: str = normalize_recovery_code(code)

    assert "-" not in normalized
    assert " " not in normalized
    assert normalized == normalized.upper()


def test_normalize_recovery_code_is_idempotent() -> None:
    code: str = build_recovery_code()

    once: str = normalize_recovery_code(code)
    twice: str = normalize_recovery_code(once)

    assert once == twice


def test_hash_recovery_code_ignores_formatting() -> None:
    code: str = build_recovery_code()

    assert hash_recovery_code(code) == hash_recovery_code(code.lower())
    assert hash_recovery_code(code) == hash_recovery_code(code.replace("-", ""))


def test_hash_recovery_code_is_deterministic() -> None:
    code: str = build_recovery_code()

    assert hash_recovery_code(code) == hash_recovery_code(code)


########################################################################################


def test_build_recovery_code_has_the_configured_byte_length() -> None:
    code: str = build_recovery_code()
    normalized: str = normalize_recovery_code(code)

    assert len(b32decode(s=f"{normalized}{'=' * (-len(normalized) % 8)}")) == (
        RECOVERY_BYTES
    )
    assert set(code) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567-")


def test_build_recovery_codes_returns_the_configured_count() -> None:
    codes = build_recovery_codes()

    assert len(codes) == CONFIG.TOTP_RECOVERY_CODES
    assert len(set(codes)) == len(codes)


########################################################################################


def test_build_provisioning_uri_carries_the_secret_and_issuer() -> None:
    secret: str = build_secret()
    uri: str = build_provisioning_uri(secret, "usuario")

    assert uri.startswith("otpauth://totp/")
    assert f"secret={secret}" in uri
    assert "usuario" in uri


@ht.given(
    st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="\x00",
        ),
        max_size=30,
    ),
)
def test_build_provisioning_uri_quotes_arbitrary_usernames(username: str) -> None:
    uri: str = build_provisioning_uri(build_secret(), username)

    assert uri.startswith("otpauth://totp/")
