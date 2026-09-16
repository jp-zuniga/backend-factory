from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, cast

from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIRequest as DjangoASGIRequest
from django.core.handlers.wsgi import WSGIRequest as DjangoWSGIRequest
from django.utils.decorators import sync_and_async_middleware
from pghistory import context
from pghistory.config import middleware_methods
from pghistory.middleware import ASGIRequest, WSGIRequest

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from django.http import HttpRequest, HttpResponse

    from api_utils.types import UsableHttpRequest

    from .types import MiddlewareCallable

########################################################################################


def patch_request_for_history(request: HttpRequest) -> None:
    if isinstance(request, DjangoWSGIRequest):
        request.__class__ = WSGIRequest
    elif isinstance(request, DjangoASGIRequest):
        request.__class__ = ASGIRequest


########################################################################################


@sync_to_async
def build_user_context(request: UsableHttpRequest) -> None:
    """
    Populate active async `pghistory.context` session with request user's details.

    It's safe to assume `request` is "usable" (see `api_utils.types`)
    here since this is **ONLY EVER CALLED** from `api_auth.security`
    **AFTER** a user has been authenticated.
    """

    context(
        user={
            "id": str(request.user.pk),
            "username": request.user.username,
            **({"email": request.user.email} if request.user.email else {}),
        },
    )


########################################################################################


@sync_and_async_middleware
def contextful_history(get_response: MiddlewareCallable) -> MiddlewareCallable:

    if iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest) -> HttpResponse:
            if request.method not in middleware_methods():
                return await cast(
                    typ="Awaitable[HttpResponse]",
                    val=get_response(request),
                )

            patch_request_for_history(request)

            async with context(url=request.path):
                return await cast(
                    typ="Awaitable[HttpResponse]",
                    val=get_response(request),
                )

    else:

        def middleware(request: HttpRequest) -> HttpResponse:
            if request.method not in middleware_methods():
                return cast(
                    typ="HttpResponse",
                    val=get_response(request),
                )

            patch_request_for_history(request)

            with context(url=request.path):
                return cast(
                    typ="HttpResponse",
                    val=get_response(request),
                )

    return middleware
