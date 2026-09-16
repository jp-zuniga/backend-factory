from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, cast

from django.utils.decorators import sync_and_async_middleware

from api_core.config import CONFIG

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from django.http import HttpRequest, HttpResponse

    from .types import MiddlewareCallable

########################################################################################


def partition_cookies(response: HttpResponse) -> HttpResponse:
    if not CONFIG.cookie_secure:
        return response

    if hasattr(response, "cookies"):
        for cookie in response.cookies.values():
            cookie["partitioned"] = True

    return response


########################################################################################


@sync_and_async_middleware
def cookie_partitioner(get_response: MiddlewareCallable) -> MiddlewareCallable:

    if iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest) -> HttpResponse:
            response = await cast(
                typ="Awaitable[HttpResponse]",
                val=get_response(request),
            )

            return partition_cookies(response)

    else:

        def middleware(request: HttpRequest) -> HttpResponse:
            response = cast(
                typ="HttpResponse",
                val=get_response(request),
            )

            return partition_cookies(response)

    return middleware
