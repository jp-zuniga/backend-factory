from typing import TYPE_CHECKING, get_args, get_origin, override

from .base import ApiError

if TYPE_CHECKING:
    from enum import StrEnum
    from http import HTTPStatus

########################################################################################


class TypedApiError[T: StrEnum](ApiError):
    @override
    def __init__(
        self,
        *args: object,
        detail: str | None = None,
        field_errors: dict | None = None,
        http_status: HTTPStatus | None = None,
        type: T | None = None,
    ) -> None:
        if type is not None:
            detail: str = detail or type.value

        super().__init__(
            detail=detail,
            field_errors=field_errors,
            http_status=http_status,
        )

    @override
    def __init_subclass__(cls, **kwargs) -> None:  # ruff: ignore[missing-type-kwargs]
        super().__init_subclass__(**kwargs)

        for base in cls.__dict__.get("__orig_bases__", ()):
            if get_origin(tp=base) is TypedApiError:
                cls.detail_type: type[T] = get_args(tp=base)[0]
