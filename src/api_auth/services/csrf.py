from typing import TYPE_CHECKING, Final, override

from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils.translation import gettext

from api_core.config import CONFIG
from api_exceptions.enums import RequestScopes
from api_exceptions.errors import ForbiddenError

if TYPE_CHECKING:
    from django.http import HttpRequest

########################################################################################

CSRF_FAILED_DETAIL: Final[str] = "La autenticación CSRF falló."

# django spells out exactly which check failed, which is a debugging aid and
# not something a client should be told about our defenses; `dmr@0.15.0` made
# the same call for its own csrf check (#1332), so we follow it here
OPAQUE_CSRF_REASON: Final[str] = "No se pudo verificar el token CSRF."

########################################################################################


class ReasonedCsrfMiddleware(CsrfViewMiddleware):
    @override
    def _reject(self, request: HttpRequest, reason: str) -> str:
        return reason if CONFIG.DEBUG else OPAQUE_CSRF_REASON


########################################################################################


async def dummy(  # ruff: ignore[unused-async]
    *args,  # ruff: ignore[missing-type-args, unused-function-argument]
    **kwargs,  # ruff: ignore[missing-type-kwargs, unused-function-argument]
) -> None:
    return None


########################################################################################

CSRF_CHECKER: Final = ReasonedCsrfMiddleware(get_response=dummy)

########################################################################################


# the cookie carrying the CSRF token is `httponly`, so this header is the
# only way a browser client can ever learn what its token is
def csrf_headers(request: HttpRequest) -> dict[str, str]:
    return {CONFIG.csrf_header: get_token(request)}


########################################################################################


def ensure_csrf(request: HttpRequest) -> None:
    CSRF_CHECKER.process_request(request)

    if reason := CSRF_CHECKER.process_view(
        callback_args=(),
        callback_kwargs={},
        callback=None,
        request=request,
    ):
        raise ForbiddenError(
            detail=CSRF_FAILED_DETAIL,
            field_errors={CONFIG.csrf_cookie_name: gettext(message=reason)},
        ).scoped(RequestScopes.COOKIES)
