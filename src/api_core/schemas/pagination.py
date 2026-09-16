from typing import Annotated

from pydantic import Field, NonNegativeInt, PositiveInt

from .base import DTO

########################################################################################


class PageQuery(DTO):
    page_size: Annotated[PositiveInt, Field(default=20, le=100)]
    page: Annotated[PositiveInt, Field(default=1)]


########################################################################################


class Paginated[Get: DTO](DTO):
    next: bool
    previous: bool
    elements: NonNegativeInt
    pages: PositiveInt
    current: PositiveInt
    results: list[Get]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:  # ruff: ignore[missing-type-kwargs, bad-dunder-method-name]
        super().__pydantic_init_subclass__(**kwargs)

        if hasattr(cls, "__name__"):
            cls.__name__ = cls.__name__.replace("[", "").replace("]", "")
