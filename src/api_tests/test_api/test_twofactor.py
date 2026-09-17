from http import HTTPStatus

import pytest

from dmr.test import DMRClient

from api_auth.enums import TokenTypes
from api_auth.models import ApiUser, ApiUserTotpDevice
from api_auth.services.jwt import parse_jwt
from api_auth.services.totp import build_totp, current_step
from api_auth.services.twofactor import (
    DISABLED_DETAIL,
    ENABLED_DETAIL,
    INVALID_CODE_DETAIL,
    INVALID_PASSWORD_DETAIL,
    LOCKED_DETAIL,
    MISSING_DEVICE_DETAIL,
)
from api_core.config import CONFIG
from api_tests.conftest import PASSWORD
from api_tests.helpers import (
    PatchedHttpResponse,
    assert_detail,
    assert_field_error,
    csrf_headers,
    fetch_csrf,
    route,
)

########################################################################################

pytestmark = pytest.mark.django_db

########################################################################################


def totp_code(secret: str) -> str:
    return build_totp(secret, current_step())


def next_code(secret: str, after: int) -> str:
    # a code is rejected once its step has already been spent, so any
    # action taken after a prior spend must target the step right after it
    return build_totp(secret, after + 1)


def enroll(client: DMRClient) -> str:
    response: PatchedHttpResponse = client.post(route("auth-two-factor-setup"))

    assert response.status_code == HTTPStatus.CREATED

    return response.json()["secret"]


def confirm(client: DMRClient) -> tuple[str, int, list[str]]:
    secret: str = enroll(client)
    step: int = current_step()

    response: PatchedHttpResponse = client.post(
        route("auth-two-factor-confirm"),
        data={"code": build_totp(secret, step)},
    )

    assert response.status_code == HTTPStatus.CREATED

    return secret, step, response.json()["codes"]


########################################################################################


def test_two_factor_status_when_disabled(restricted_client: DMRClient) -> None:
    response: PatchedHttpResponse = restricted_client.get(route("auth-two-factor"))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "confirmed_at": None,
        "enabled": False,
        "pending": False,
        "recovery_codes": 0,
    }


def test_two_factor_status_requires_authentication(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("auth-two-factor"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


########################################################################################


def test_two_factor_setup_creates_a_pending_device(
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-setup"),
    )

    assert response.status_code == HTTPStatus.CREATED

    payload: dict = response.json()

    assert payload["secret"]
    assert payload["uri"].startswith("otpauth://totp/")
    assert client_user.username in payload["uri"]

    status: PatchedHttpResponse = restricted_client.get(route("auth-two-factor"))

    assert status.json()["pending"] is True
    assert status.json()["enabled"] is False


def test_two_factor_setup_requires_authentication(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.post(route("auth-two-factor-setup"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_two_factor_setup_rejects_when_already_enabled(
    restricted_client: DMRClient,
) -> None:
    confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-setup"),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert_detail(response, ENABLED_DETAIL)


########################################################################################


def test_two_factor_confirm_activates_the_device(restricted_client: DMRClient) -> None:
    _, _, codes = confirm(restricted_client)

    assert len(codes) == CONFIG.TOTP_RECOVERY_CODES
    assert len(set(codes)) == CONFIG.TOTP_RECOVERY_CODES

    status: PatchedHttpResponse = restricted_client.get(route("auth-two-factor"))

    assert status.json()["enabled"] is True
    assert status.json()["pending"] is False
    assert status.json()["recovery_codes"] == CONFIG.TOTP_RECOVERY_CODES


def test_two_factor_confirm_rejects_an_invalid_code(
    restricted_client: DMRClient,
) -> None:
    enroll(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-confirm"),
        data={"code": "000000"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.code") == INVALID_CODE_DETAIL


def test_two_factor_confirm_rejects_a_missing_device(
    restricted_client: DMRClient,
) -> None:
    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-confirm"),
        data={"code": "000000"},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert_detail(response, MISSING_DEVICE_DETAIL)


def test_two_factor_confirm_rejects_an_already_confirmed_device(
    restricted_client: DMRClient,
) -> None:
    confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-confirm"),
        data={"code": "000000"},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert_detail(response, ENABLED_DETAIL)


########################################################################################


def test_two_factor_recovery_rotates_the_codes(restricted_client: DMRClient) -> None:
    secret, step, before = confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-recovery"),
        data={"code": next_code(secret, step)},
    )

    assert response.status_code == HTTPStatus.CREATED

    after: list[str] = response.json()["codes"]

    assert len(after) == CONFIG.TOTP_RECOVERY_CODES
    assert set(after).isdisjoint(before)


def test_two_factor_recovery_requires_a_confirmed_device(
    restricted_client: DMRClient,
) -> None:
    secret: str = enroll(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-recovery"),
        data={"code": totp_code(secret)},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert_detail(response, DISABLED_DETAIL)


def test_two_factor_recovery_rejects_an_invalid_code(
    restricted_client: DMRClient,
) -> None:
    confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-recovery"),
        data={"code": "000000"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.code") == INVALID_CODE_DETAIL


########################################################################################


def test_two_factor_disable_removes_the_device(
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    secret, step, _ = confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-disable"),
        data={"code": next_code(secret, step), "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not ApiUserTotpDevice.objects.filter(api_user_id=client_user.pk).exists()

    status: PatchedHttpResponse = restricted_client.get(route("auth-two-factor"))

    assert status.json() == {
        "confirmed_at": None,
        "enabled": False,
        "pending": False,
        "recovery_codes": 0,
    }


def test_two_factor_disable_rejects_an_invalid_password(
    restricted_client: DMRClient,
) -> None:
    secret, _, _ = confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-disable"),
        data={"code": totp_code(secret), "password": "no-es-la-clave"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.password") == INVALID_PASSWORD_DETAIL


def test_two_factor_disable_rejects_an_invalid_code(
    restricted_client: DMRClient,
) -> None:
    confirm(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-disable"),
        data={"code": "000000", "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.code") == INVALID_CODE_DETAIL


def test_two_factor_disable_requires_a_confirmed_device(
    restricted_client: DMRClient,
) -> None:
    secret: str = enroll(restricted_client)

    response: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-disable"),
        data={"code": totp_code(secret), "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert_detail(response, DISABLED_DETAIL)


########################################################################################


def test_second_factor_locks_after_too_many_failures(
    restricted_client: DMRClient,
) -> None:
    enroll(restricted_client)

    for _ in range(CONFIG.TOTP_MAX_FAILURES):
        response: PatchedHttpResponse = restricted_client.post(
            route("auth-two-factor-confirm"),
            data={"code": "000000"},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    locked: PatchedHttpResponse = restricted_client.post(
        route("auth-two-factor-confirm"),
        data={"code": "000000"},
    )

    assert locked.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert_detail(locked, LOCKED_DETAIL)


########################################################################################


def test_mobile_login_issues_a_challenge_when_enabled(
    dmr_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    confirm(restricted_client)

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.ACCEPTED

    payload: dict = response.json()

    assert payload["expires_in"] > 0
    assert parse_jwt(payload["challenge"], TokenTypes.CHALLENGE).sub == str(
        client_user.pk,
    )


def test_mobile_two_factor_exchanges_the_challenge_for_tokens(
    dmr_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    secret, step, _ = confirm(restricted_client)

    challenge: str = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    ).json()["challenge"]

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-two-factor"),
        data={"challenge": challenge, "code": next_code(secret, step)},
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["user"]["username"] == client_user.username
    assert parse_jwt(payload["access"], TokenTypes.ACCESS).sub == str(client_user.pk)


def test_mobile_two_factor_rejects_an_invalid_code(
    dmr_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    confirm(restricted_client)

    challenge: str = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    ).json()["challenge"]

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-two-factor"),
        data={"challenge": challenge, "code": "000000"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_mobile_two_factor_rejects_a_spent_challenge(
    dmr_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    secret, step, _ = confirm(restricted_client)

    challenge: str = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    ).json()["challenge"]

    dmr_client.post(
        route("auth-mobile-two-factor"),
        data={"challenge": challenge, "code": next_code(secret, step)},
    )

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-two-factor"),
        data={"challenge": challenge, "code": next_code(secret, step)},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_second_factor_accepts_a_recovery_code(
    dmr_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    _, _, codes = confirm(restricted_client)

    challenge: str = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    ).json()["challenge"]

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-two-factor"),
        data={"challenge": challenge, "code": codes[0]},
    )

    assert response.status_code == HTTPStatus.OK


def test_recovery_code_is_single_use(
    dmr_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    _, _, codes = confirm(restricted_client)

    def spend() -> PatchedHttpResponse:
        challenge: str = dmr_client.post(
            route("auth-mobile-login"),
            data={"username": client_user.username, "password": PASSWORD},
        ).json()["challenge"]

        return dmr_client.post(
            route("auth-mobile-two-factor"),
            data={"challenge": challenge, "code": codes[0]},
        )

    assert spend().status_code == HTTPStatus.OK
    assert spend().status_code == HTTPStatus.UNAUTHORIZED


########################################################################################


def test_web_login_issues_a_challenge_cookie_when_enabled(
    csrf_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    confirm(restricted_client)

    token: str = fetch_csrf(csrf_client)

    response: PatchedHttpResponse = csrf_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
        headers=csrf_headers(token),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.cookies[TokenTypes.CHALLENGE].value
    assert TokenTypes.ACCESS not in response.cookies


def test_web_two_factor_sets_token_cookies(
    csrf_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    secret, step, _ = confirm(restricted_client)

    token: str = fetch_csrf(csrf_client)

    login: PatchedHttpResponse = csrf_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
        headers=csrf_headers(token),
    )

    # `rotate_csrf_token` moves the token on, so the challenge step
    # must present the token the login response just handed back
    rotated: str = login.headers[CONFIG.csrf_header]

    response: PatchedHttpResponse = csrf_client.post(
        route("auth-web-two-factor"),
        data={"code": next_code(secret, step)},
        headers=csrf_headers(rotated),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.cookies[TokenTypes.ACCESS]["httponly"]
    assert response.cookies[TokenTypes.CHALLENGE].value == ""  # ruff: ignore[compare-to-empty-string]
    assert response.json()["user"]["username"] == client_user.username


def test_web_two_factor_requires_csrf(
    csrf_client: DMRClient,
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    secret, step, _ = confirm(restricted_client)

    token: str = fetch_csrf(csrf_client)

    csrf_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
        headers=csrf_headers(token),
    )

    response: PatchedHttpResponse = csrf_client.post(
        route("auth-web-two-factor"),
        data={"code": next_code(secret, step)},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
