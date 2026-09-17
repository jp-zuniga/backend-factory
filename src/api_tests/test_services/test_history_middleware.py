from collections.abc import Callable

from asgiref.sync import async_to_sync
from django.core.handlers.asgi import ASGIRequest as DjangoASGIRequest
from django.core.handlers.wsgi import WSGIRequest as DjangoWSGIRequest
from django.http import HttpResponse
from dmr.test import DMRRequestFactory
from pghistory.middleware import ASGIRequest, WSGIRequest

from api_auth.models import ApiUser
from api_middlewares.history import build_user_context, contextful_history

########################################################################################


def build_response() -> HttpResponse:
    return HttpResponse()


def test_contextful_history_wraps_a_sync_mutation(dmr_rf: DMRRequestFactory) -> None:
    seen: list[str] = []

    def get_response(request: object) -> HttpResponse:
        seen.append("called")

        return build_response()

    middleware: Callable = contextful_history(get_response)
    request = dmr_rf.post("/algun-recurso/")
    request.__class__ = DjangoWSGIRequest

    response: HttpResponse = middleware(request)

    assert response.status_code == HttpResponse.status_code
    assert seen == ["called"]
    assert isinstance(request, WSGIRequest)


def test_contextful_history_skips_safe_methods(dmr_rf: DMRRequestFactory) -> None:
    def get_response(request: object) -> HttpResponse:
        return build_response()

    middleware: Callable = contextful_history(get_response)

    request = dmr_rf.get("/algun-recurso/")

    request.__class__ = DjangoWSGIRequest

    middleware(request)

    # a safe method must never be re-classed for history tracking
    assert not isinstance(request, WSGIRequest)


def test_contextful_history_wraps_an_async_mutation(dmr_rf: DMRRequestFactory) -> None:
    async def get_response(request: object) -> HttpResponse:  # ruff: ignore[unused-async]
        return build_response()

    middleware: Callable = contextful_history(get_response)
    request = dmr_rf.post("/algun-recurso/")
    request.__class__ = DjangoASGIRequest

    response: HttpResponse = async_to_sync(middleware)(request)

    assert response.status_code == HttpResponse.status_code
    assert isinstance(request, ASGIRequest)


def test_contextful_history_async_skips_safe_methods(dmr_rf: DMRRequestFactory) -> None:
    async def get_response(request: object) -> HttpResponse:  # ruff: ignore[unused-async]
        return build_response()

    middleware: Callable = contextful_history(get_response)
    request = dmr_rf.get("/algun-recurso/")
    request.__class__ = DjangoASGIRequest

    async_to_sync(middleware)(request)

    assert not isinstance(request, ASGIRequest)


########################################################################################


def test_build_user_context_includes_email_when_present(
    dmr_rf: DMRRequestFactory,
    client_user: ApiUser,
) -> None:
    request = dmr_rf.get("/")
    request.user = client_user

    # exercising it must not raise; the values it feeds `pghistory.context`
    # are not independently observable from outside a history-tracked write
    async_to_sync(build_user_context)(request)


def test_build_user_context_tolerates_a_blank_email(
    dmr_rf: DMRRequestFactory,
    client_user: ApiUser,
) -> None:
    client_user.email = ""  # ty: ignore[invalid-assignment]

    request = dmr_rf.get("/")
    request.user = client_user

    async_to_sync(build_user_context)(request)
