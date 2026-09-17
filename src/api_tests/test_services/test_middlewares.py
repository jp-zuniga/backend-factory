from collections.abc import Callable

import pytest

from asgiref.sync import async_to_sync
from django.http import HttpResponse
from dmr.test import DMRRequestFactory

from api_core.config import CONFIG
from api_middlewares.cookies import cookie_partitioner, partition_cookies

########################################################################################


@pytest.fixture(autouse=True)
def secure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CONFIG, "cookie_secure", True)


def build_response() -> HttpResponse:
    response = HttpResponse()
    response.set_cookie("chocolate", "valor")

    return response


########################################################################################


def test_partition_cookies_marks_every_cookie() -> None:
    response: HttpResponse = partition_cookies(build_response())

    assert response.cookies["chocolate"]["partitioned"] is True


def test_partition_cookies_is_a_noop_when_cookies_are_not_secure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(CONFIG, "cookie_secure", False)

    response: HttpResponse = partition_cookies(build_response())

    assert response.cookies["chocolate"]["partitioned"] == ""  # ruff: ignore[compare-to-empty-string]


########################################################################################


def test_cookie_partitioner_wraps_a_sync_view(dmr_rf: DMRRequestFactory) -> None:
    def get_response(request: object) -> HttpResponse:
        return build_response()

    middleware: Callable = cookie_partitioner(get_response)
    response: HttpResponse = middleware(dmr_rf.get("/"))

    assert response.cookies["chocolate"]["partitioned"] is True


def test_cookie_partitioner_wraps_an_async_view(dmr_rf: DMRRequestFactory) -> None:
    async def get_response(request: object) -> HttpResponse:  # ruff: ignore[unused-async]
        return build_response()

    middleware: Callable = cookie_partitioner(get_response)
    response: HttpResponse = async_to_sync(middleware)(dmr_rf.get("/"))

    assert response.cookies["chocolate"]["partitioned"] is True
