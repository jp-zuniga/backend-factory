from http import HTTPStatus

import pytest

from dmr.security.jwt.blocklist.models import BlocklistedJWToken
from dmr.test import DMRClient, DMRRequestFactory

from api_auth.enums import TokenTypes
from api_auth.models import ApiUser
from api_auth.services.blocklist import REVOKED_DETAIL
from api_auth.services.csrf import ensure_csrf
from api_auth.services.jwt import EncodedJwtPair, build_jwt_pair, parse_jwt
from api_core.config import CONFIG
from api_exceptions.errors import ForbiddenError, UnauthorizedError
from api_tests.conftest import PASSWORD
from api_tests.helpers import (
    PatchedHttpResponse,
    assert_detail,
    assert_field_error,
    fetch_csrf,
    route,
    unauthenticate,
)

########################################################################################


def test_mobile_login_returns_tokens_and_user(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["user"]["username"] == client_user.username
    assert payload["user"]["email"] == client_user.email
    assert payload["user"]["is_active"] is True

    assert parse_jwt(payload["access"], TokenTypes.ACCESS).sub == str(client_user.pk)
    assert parse_jwt(payload["refresh"], TokenTypes.REFRESH).sub == str(client_user.pk)


def test_mobile_login_pairs_share_session(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    payload: dict = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    ).json()

    access = parse_jwt(payload["access"], TokenTypes.ACCESS)
    refresh = parse_jwt(payload["refresh"], TokenTypes.REFRESH)

    assert access.extras["sid"] == refresh.extras["sid"]
    assert access.jti != refresh.jti


def test_mobile_login_sets_no_cookies(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": PASSWORD},
    )

    assert TokenTypes.ACCESS not in response.cookies


def test_mobile_login_rejects_bad_password(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": client_user.username, "password": "no-es-la-clave"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert_detail(response, "Las credenciales proporcionadas no son válidas.")


def test_mobile_login_rejects_inactive_user(
    dmr_client: DMRClient,
    inactive_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": inactive_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_mobile_login_rejects_unknown_user(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={"username": "no-existe", "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"password": PASSWORD}, "body.username"),
        ({"username": "alguien"}, "body.password"),
        ({"username": "", "password": PASSWORD}, "body.username"),
        ({"username": "alguien", "password": ""}, "body.password"),
    ],
)
def test_mobile_login_validates_body(
    dmr_client: DMRClient,
    db: None,
    body: dict,
    field: str,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data=body,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, field)


def test_mobile_login_rejects_extra_fields(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        data={
            "username": client_user.username,
            "password": PASSWORD,
            "extra": True,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "body.extra")
        == "Este campo no es válido para esta acción."
    )


########################################################################################


def test_mobile_logout_blocklists_the_session(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-logout"),
        data={"access": client_tokens.access, "refresh": client_tokens.refresh},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert BlocklistedJWToken.objects.exists()  # ty: ignore[unresolved-attribute]


def test_mobile_logout_accepts_empty_body(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-logout"), data={}
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not BlocklistedJWToken.objects.exists()  # ty: ignore[unresolved-attribute]


def test_mobile_logout_ignores_invalid_tokens(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-logout"),
        data={"access": "no.es.un.jwt"},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_logged_out_token_is_rejected(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    dmr_client.post(
        route("auth-mobile-logout"),
        data={"access": client_tokens.access, "refresh": client_tokens.refresh},
    )

    dmr_client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {client_tokens.access}"

    response: PatchedHttpResponse = dmr_client.get(route("auth-profile"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


########################################################################################


def test_mobile_refresh_rotates_the_pair(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-refresh"),
        data={"refresh": client_tokens.refresh},
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["access"] != client_tokens.access
    assert payload["refresh"] != client_tokens.refresh
    assert parse_jwt(payload["access"], TokenTypes.ACCESS)


def test_mobile_refresh_consumes_the_refresh_token(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    dmr_client.post(
        route("auth-mobile-refresh"),
        data={"refresh": client_tokens.refresh},
    )

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-refresh"),
        data={"refresh": client_tokens.refresh},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert_detail(response, REVOKED_DETAIL)


def test_mobile_refresh_requires_a_refresh_token(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-refresh"),
        data={"access": client_tokens.access},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.refresh")


def test_mobile_refresh_rejects_an_access_token(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-refresh"),
        data={"refresh": client_tokens.access},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_mobile_refresh_rejects_inactive_subject(
    dmr_client: DMRClient,
    inactive_user: ApiUser,
) -> None:
    tokens = build_jwt_pair(inactive_user)

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-refresh"),
        data={"refresh": tokens.refresh},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


########################################################################################


def test_mobile_verify_accepts_a_live_token(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-verify"),
        data={"token": client_tokens.access, "type": TokenTypes.ACCESS.value},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_mobile_verify_rejects_a_revoked_token(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    dmr_client.post(
        route("auth-mobile-logout"),
        data={"access": client_tokens.access},
    )

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-verify"),
        data={"token": client_tokens.access, "type": TokenTypes.ACCESS.value},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert_detail(response, REVOKED_DETAIL)


def test_mobile_verify_rejects_type_mismatch(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-verify"),
        data={"token": client_tokens.refresh, "type": TokenTypes.ACCESS.value},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_mobile_verify_validates_the_type(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-verify"),
        data={"token": client_tokens.access, "type": "otro"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.type")


########################################################################################


def test_csrf_endpoint_hands_out_a_token(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("auth-csrf"))

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.headers[CONFIG.csrf_header]
    assert CONFIG.csrf_cookie_name in response.cookies
    assert response.content == b""


def test_csrf_cookie_is_http_only(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("auth-csrf"))

    assert response.cookies[CONFIG.csrf_cookie_name]["httponly"]


def test_ensure_csrf_rejects_a_tokenless_request(dmr_rf: DMRRequestFactory) -> None:
    request = dmr_rf.post(route("auth-web-login"), data={})

    with pytest.raises(ForbiddenError) as raised:
        ensure_csrf(request)

    assert raised.value.default_http_status == HTTPStatus.FORBIDDEN
    assert raised.value.detail == "La autenticación CSRF falló."
    assert f"cookies.{CONFIG.csrf_cookie_name}" in raised.value.field_errors


def test_ensure_csrf_accepts_a_safe_method(dmr_rf: DMRRequestFactory) -> None:
    assert ensure_csrf(dmr_rf.get(route("api-root"))) is None


########################################################################################


def test_web_login_sets_token_cookies(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "user": {
            "id": str(client_user.pk),
            "email_verified_at": response.json()["user"]["email_verified_at"],
            "is_active": True,
            "first_name": client_user.first_name,
            "last_name": client_user.last_name,
            "username": client_user.username,
            "email": client_user.email,
        },
    }

    assert response.cookies[TokenTypes.ACCESS]["httponly"]
    assert response.cookies[TokenTypes.REFRESH]["httponly"]
    assert response.headers[CONFIG.csrf_header]


def test_web_login_leaks_no_tokens_in_the_body(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    payload: dict = dmr_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
    ).json()

    assert "access" not in payload
    assert "refresh" not in payload


def test_web_login_rejects_bad_credentials(
    dmr_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": "incorrecta"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert TokenTypes.ACCESS not in response.cookies


def test_web_cookies_authenticate_requests(
    web_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = web_client.get(route("auth-profile"))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["username"] == client_user.username


########################################################################################


def test_web_verify_reports_both_tokens(web_client: DMRClient) -> None:
    response: PatchedHttpResponse = web_client.post(route("auth-web-verify"), data={})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"access": True, "refresh": True}


def test_web_verify_without_cookies(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.post(route("auth-web-verify"), data={})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"access": False, "refresh": False}


########################################################################################


def test_web_refresh_replaces_the_cookies(web_client: DMRClient) -> None:
    before: str = web_client.cookies[TokenTypes.ACCESS].value

    response: PatchedHttpResponse = web_client.post(route("auth-web-refresh"), data={})

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.cookies[TokenTypes.ACCESS].value != before


def test_web_refresh_requires_a_refresh_cookie(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.post(route("auth-web-refresh"), data={})

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert_detail(response, UnauthorizedError.default_detail)


########################################################################################


def test_web_logout_clears_the_cookies(web_client: DMRClient) -> None:
    response: PatchedHttpResponse = web_client.post(route("auth-web-logout"), data={})

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.cookies[TokenTypes.ACCESS].value == ""  # ruff: ignore[compare-to-empty-string]
    assert response.cookies[TokenTypes.REFRESH].value == ""  # ruff: ignore[compare-to-empty-string]


def test_web_logout_revokes_the_session(web_client: DMRClient) -> None:
    access: str = web_client.cookies[TokenTypes.ACCESS].value

    web_client.post(route("auth-web-logout"), data={})

    unauthenticate(web_client)

    web_client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"

    assert web_client.get(route("auth-profile")).status_code == (
        HTTPStatus.UNAUTHORIZED
    )


def test_web_logout_without_cookies(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.post(route("auth-web-logout"), data={})

    assert response.status_code == HTTPStatus.NO_CONTENT


########################################################################################


def test_csrf_protected_flow_with_enforcement(
    csrf_client: DMRClient,
    client_user: ApiUser,
) -> None:
    token: str = fetch_csrf(csrf_client)

    response: PatchedHttpResponse = csrf_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
        headers={CONFIG.csrf_header: token},
    )

    assert response.status_code == HTTPStatus.OK


def test_csrf_enforcement_blocks_a_tokenless_post(
    csrf_client: DMRClient,
    client_user: ApiUser,
) -> None:
    fetch_csrf(csrf_client)

    response: PatchedHttpResponse = csrf_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
