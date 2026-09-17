from http import HTTPStatus
from json import loads

import pytest

from dmr.test import DMRAsyncRequestFactory, DMRClient, assert_async_throttling
from dmr.throttling import Rate

from api_auth.controllers.base import AuthController
from api_core.controllers.root import RootController, build_root_response
from api_exceptions.errors import (
    NotFoundError,
    ThrottleExceededError,
    UnacceptableHeaderError,
)
from api_tests.helpers import PatchedHttpResponse, assert_detail, route
from api_tests.sync import run
from api_utils.env import OPENAPI

########################################################################################


def test_root_response_is_cached() -> None:
    assert build_root_response() is build_root_response()


def test_root_is_public(dmr_client: DMRClient) -> None:
    assert RootController.auth is None
    assert dmr_client.get(route("api-root")).status_code == HTTPStatus.OK


def test_root_rejects_unsupported_methods(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.post(route("api-root"), data={})

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["Allow"] == "GET"
    assert response.json()["field_errors"] == {
        "method": "Métodos permitidos: GET.",
    }

    assert_detail(response, "Este controlador no procesa peticiones POST.")


def test_root_returns_project_metadata(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("api-root"))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "description": OPENAPI.description,
        "title": OPENAPI.title,
        "version": OPENAPI.version,
    }


########################################################################################


def test_health_is_public(dmr_client: DMRClient, db: None, local_cache: None) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("health-check"))

    assert response.status_code in {
        HTTPStatus.OK,
        HTTPStatus.SERVICE_UNAVAILABLE,
    }


def test_health_reports_every_component(
    dmr_client: DMRClient,
    db: None,
    local_cache: None,
) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("health-check"))

    payload: dict = response.json()

    assert set(payload["components"]) == {"cache", "database", "storage"}
    assert payload["components"]["cache"] == "ok"
    assert payload["components"]["database"] == "ok"


def test_health_status_matches_components(
    dmr_client: DMRClient,
    db: None,
    local_cache: None,
) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("health-check"))

    payload: dict = response.json()

    healthy: bool = all(state == "ok" for state in payload["components"].values())

    assert payload["status"] == ("success" if healthy else "error")
    assert response.status_code == (
        HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
    )


########################################################################################


def test_openapi_declares_error_responses(openapi_document: dict) -> None:
    responses: dict = openapi_document["paths"]["/auth/user/"]["get"]["responses"]

    assert str(HTTPStatus.UNAUTHORIZED.value) in responses
    assert str(HTTPStatus.FORBIDDEN.value) in responses
    assert str(HTTPStatus.TOO_MANY_REQUESTS.value) in responses


def test_openapi_declares_security_schemes(openapi_document: dict) -> None:
    schemes: dict = openapi_document["components"]["securitySchemes"]

    assert "jwtHeader" in schemes
    assert "jwtCookie" in schemes
    assert "csrf" in schemes


def test_openapi_document_covers_every_route(openapi_document: dict) -> None:
    paths: frozenset[str] = frozenset(openapi_document["paths"])

    assert "/auth/mobile/login/" in paths
    assert "/auth/user/" in paths
    assert "/auth/user/all/" in paths
    assert "/auth/user/{id}/" in paths
    assert "/auth/user/{id}/groups/" in paths
    assert "/auth/user/{id}/groups/{related}/" in paths
    assert "/auth/group/{id}/" in paths
    assert "/auth/permission/" in paths


def test_openapi_document_is_served(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("openapi-schema"))

    assert response.status_code == HTTPStatus.OK
    assert response.headers["Content-Type"] == "application/json"

    payload: dict = response.json()

    assert payload["openapi"].startswith("3.")
    assert payload["info"]["title"] == OPENAPI.title
    assert payload["info"]["version"] == OPENAPI.version


def test_openapi_operation_ids_are_unique(openapi_document: dict) -> None:
    operations: list[str] = [
        item["operationId"]
        for path in openapi_document["paths"].values()
        for key, item in path.items()
        if key in {"get", "post", "put", "patch", "delete"}
    ]

    assert len(operations) == len(set(operations))
    assert "auth-user-list" in operations
    assert "auth-user-retrieve" in operations


########################################################################################


def test_unknown_nested_path_returns_api_error(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get("/auth/inexistente/")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert_detail(response, NotFoundError.default_detail)


def test_unknown_path_returns_api_error(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get("/ruta/que/no/existe/")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.headers["Content-Type"] == "application/json"
    assert_detail(response, NotFoundError.default_detail)


########################################################################################


def test_malformed_json_body(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        content_type="application/json",
        data="{no-es-json",
    )

    assert response.status_code in {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    }


def test_unacceptable_accept_header(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(
        route("api-root"),
        headers={"Accept": "application/xml"},
    )

    assert response.status_code == HTTPStatus.NOT_ACCEPTABLE
    assert_detail(response, UnacceptableHeaderError.default_detail)


def test_unsupported_content_type(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-mobile-login"),
        content_type="text/plain",
        data="usuario=x",
    )

    assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_wildcard_accept_header_is_allowed(dmr_client: DMRClient) -> None:
    response: PatchedHttpResponse = dmr_client.get(
        route("api-root"),
        headers={"Accept": "*/*"},
    )

    assert response.status_code == HTTPStatus.OK


########################################################################################


def test_root_is_throttled(
    dmr_async_rf: DMRAsyncRequestFactory,
    live_throttling: None,
) -> None:
    throttled, throttle = run(
        assert_async_throttling,
        RootController,
        lambda: dmr_async_rf.get(route("api-root")),
        max_requests=2,
        rate=Rate.hour,
        success_status=HTTPStatus.OK,
    )

    assert throttle.max_requests == 2
    assert throttled.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert loads(throttled.content)["detail"] == ThrottleExceededError.default_detail


@pytest.mark.parametrize(
    "name",
    ["auth-csrf", "auth-mobile-login", "auth-mobile-logout"],
)
def test_auth_endpoints_use_strict_throttling(name: str, dmr_client: DMRClient) -> None:
    assert len(AuthController.throttling) == 1
    assert AuthController.throttling[0].max_requests == 10
    assert route(name).startswith("/auth/")


def test_throttled_response_carries_rate_headers(
    dmr_async_rf: DMRAsyncRequestFactory,
    live_throttling: None,
) -> None:
    throttled, _ = run(
        assert_async_throttling,
        RootController,
        lambda: dmr_async_rf.get(route("api-root")),
        max_requests=2,
        rate=Rate.hour,
        success_status=HTTPStatus.OK,
    )

    assert "Retry-After" in throttled.headers
    assert throttled.headers["X-RateLimit-Limit"] == "2"
    assert throttled.headers["X-RateLimit-Remaining"] == "0"
