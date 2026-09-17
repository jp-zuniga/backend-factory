from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

from django.http import HttpResponse
from django.urls import reverse
from dmr.test import DMRClient

from api_auth.models import ApiUser
from api_auth.services.jwt import EncodedJwtPair
from api_core.config import CONFIG
from api_exceptions.enums import RequestScopes

########################################################################################


class PatchedHttpResponse(HttpResponse):
    """
    I LOVE DJANGO!!!

    I ESPECIALLY LOVE THE MONKEYPATCHED HTTP RESPONSE
    OBJECTS RETURNED BY THE TESTING CLIENTS!!!!!!!!!!
    """  # ruff: ignore[missing-trailing-period]

    json: Callable[[], dict]


########################################################################################


def route(name: str, *args: int | str | UUID, **kwargs: int | str | UUID) -> str:
    return reverse(
        args=(list(args) if args and not kwargs else None),
        kwargs=(kwargs if kwargs and not args else None),
        viewname=name,
    )


########################################################################################


def bearer(client: DMRClient, tokens: EncodedJwtPair) -> DMRClient:
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {tokens.access}"

    return client


def unauthenticate(client: DMRClient) -> DMRClient:
    client.defaults.pop("HTTP_AUTHORIZATION", None)
    client.cookies.clear()

    return client


########################################################################################


def csrf_headers(token: str) -> dict[str, str]:
    return {CONFIG.csrf_header: token}


def fetch_csrf(client: DMRClient) -> str:
    response: PatchedHttpResponse = client.get(route("auth-csrf"))

    assert response.status_code == HTTPStatus.NO_CONTENT

    token: str | None = response.headers.get(CONFIG.csrf_header)

    assert token

    return token


########################################################################################


def assert_detail(response: PatchedHttpResponse, expected: str) -> None:
    assert response.json()["detail"] == expected


def assert_field_error(response: PatchedHttpResponse, key: str) -> str:
    payload: dict = response.json()

    assert payload["field_errors"] is not None
    assert key in payload["field_errors"], payload["field_errors"]

    return payload["field_errors"][key]


def scoped_key(scope: RequestScopes, *crumbs: int | str) -> str:
    return ".".join((scope.value, *(str(crumb) for crumb in crumbs)))


########################################################################################


def listed_ids(response: PatchedHttpResponse) -> list[str]:
    return [str(item["id"]) for item in response.json()]


def paginated_ids(response: PatchedHttpResponse) -> list[str]:
    return [str(item["id"]) for item in response.json()["results"]]


########################################################################################


def mobile_login(client: DMRClient, user: ApiUser, password: str) -> dict:
    response: PatchedHttpResponse = client.post(
        route("auth-mobile-login"),
        data={"username": user.username, "password": password},
    )

    assert response.status_code == HTTPStatus.OK

    return response.json()
