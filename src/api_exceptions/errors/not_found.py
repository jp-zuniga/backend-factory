from http import HTTPStatus
from typing import TYPE_CHECKING, override

from .base import ApiError

if TYPE_CHECKING:
    from typing import Final

########################################################################################


class NotFoundError(ApiError):
    default_detail: Final[str] = "El recurso solicitado no se encontró."

    default_http_status: Final[HTTPStatus] = HTTPStatus.NOT_FOUND

    @override
    def __init__(
        self,
        *args: object,
        detail: str | None = None,
        field_errors: dict | None = None,
        http_status: HTTPStatus | None = None,
    ) -> None:
        super().__init__(
            detail=detail,
            field_errors=(
                {
                    field: f"No existe un registro con el valor '{value}'."
                    for field, value in field_errors.items()
                }
                if field_errors is not None
                else None
            ),
            http_status=http_status,
        )
