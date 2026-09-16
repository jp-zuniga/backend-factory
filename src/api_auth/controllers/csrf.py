from http import HTTPStatus

from django.http import HttpResponse
from dmr import ResponseSpec, validate
from dmr.endpoint import ValidateAnyCallable

from api_auth.services.csrf import csrf_headers
from api_core.controllers.serializers import CustomPydanticFastSerializer

from .base import CSRF_HEADER_SPEC, NO_STORE_SPEC, NO_STORE_VALUES, AuthController

########################################################################################


class CsrfController(AuthController[CustomPydanticFastSerializer]):
    """
    Hand a browser client its CSRF token.

    The cookie that carries it is `httponly`, so the header is the only
    way a client can ever read it.
    """

    @classmethod
    def validate_spec(cls) -> ValidateAnyCallable:
        return validate(
            ResponseSpec(
                return_type=None,
                headers={**NO_STORE_SPEC, **CSRF_HEADER_SPEC},
                status_code=HTTPStatus.NO_CONTENT,
            ),
        )

    @validate.lazy(validate_spec)
    async def get(self) -> HttpResponse:
        return self.to_response(
            None,
            headers={**NO_STORE_VALUES, **csrf_headers(self.request)},
            status_code=HTTPStatus.NO_CONTENT,
        )
