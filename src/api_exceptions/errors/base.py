from http import HTTPStatus
from typing import TYPE_CHECKING, override

from api_utils.strings import dotted_join

if TYPE_CHECKING:
    from typing import Self


########################################################################################


class ApiError(Exception):
    default_detail: str = "Ha ocurrido un error inesperado."

    default_http_status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR

    @override
    def __init__(
        self,
        *args: object,
        detail: str | None = None,
        field_errors: dict[str, str] | None = None,
        http_status: HTTPStatus | None = None,
    ) -> None:
        self.detail: str = detail or self.default_detail
        self.field_errors: dict[str, str] = field_errors or {}
        self.http_status: HTTPStatus = http_status or self.default_http_status

        super().__init__(self.detail)

    def scoped(self, *crumbs: int | str) -> Self:
        if not self.field_errors or not crumbs:
            return self

        prefix = dotted_join(*crumbs)

        self.field_errors = {
            dotted_join(prefix, field): msg for field, msg in self.field_errors.items()
        }

        return self
