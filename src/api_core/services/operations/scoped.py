from typing import TYPE_CHECKING, override

from .flat import ForeignKeyCreateOperation

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from api_core.schemas.base import DTO
    from api_core.services.mappers import ModelMapper
    from api_utils.types import DatabaseModel

########################################################################################


class ScopedCreateOperation[Get: DTO, Post: DTO](ForeignKeyCreateOperation[Get, Post]):
    """
    Create a row underneath a parent resource.

    The parent is taken from the path, never from the body, so a
    client cannot file a child under somebody else's parent.
    """

    __slots__ = ("defaults",)

    def __init__(
        self,
        *fields: str,
        defaults: dict,
        mapper: ModelMapper[Get],
        schema: type[Get],
        qs: QuerySet,
    ) -> None:
        super().__init__(*fields, mapper=mapper, schema=schema, qs=qs)

        self.defaults: dict = defaults

    @override
    async def execute(self, data: dict) -> DatabaseModel:
        return await super().execute(data | self.defaults)
