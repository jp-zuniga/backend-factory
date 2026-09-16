from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, override

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from api_exceptions.enums import RequestScopes
from api_exceptions.errors import ConflictError, NotFoundError

from .base import ModelOperation

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from api_core.schemas.base import DTO
    from api_core.schemas.path import RelatedInstancePath
    from api_core.services.mappers import ModelMapper
    from api_utils.types import DatabaseModel

########################################################################################


class LinkOperation[Get: DTO](ModelOperation[Get], ABC):
    __slots__ = ("parent", "related")

    scope: ClassVar[RequestScopes] = RequestScopes.PATH

    @override
    def __init__(  # ty: ignore[invalid-method-override]
        self,
        *fields: str,
        mapper: ModelMapper[Get],
        parent: str,
        related: str,
        schema: type[Get],
        qs: QuerySet,
    ) -> None:
        super().__init__(*fields, mapper=mapper, schema=schema, qs=qs)

        self.parent: str = parent
        self.related: str = related

    def build_lookup(self, path: RelatedInstancePath) -> dict:
        return {
            f"{self.parent}_id": path.id,
            f"{self.related}_id": path.related,
        }

    async def find_missing(self, path: RelatedInstancePath) -> str | None:
        through: type[DatabaseModel] = self.qs.model  # ty: ignore[invalid-assignment]

        for name, field, value in (
            ("id", self.parent, path.id),
            ("related", self.related, path.related),
        ):
            model: type[DatabaseModel] = through._meta.get_field(field).related_model

            if not await model._default_manager.filter(pk=value).aexists():
                return name

        return None

    async def raise_missing(self, path: RelatedInstancePath) -> None:
        missing: str | None = await self.find_missing(path)

        raise NotFoundError(
            field_errors=(
                {missing: getattr(path, missing)}
                if missing is not None
                else path.model_dump()
            ),
        ).scoped(self.scope)


########################################################################################


class LinkAttachOperation[Get: DTO](LinkOperation[Get], ABC):
    __slots__ = ()

    @override
    async def run(self, path: RelatedInstancePath) -> None:
        lookup: dict = self.build_lookup(path)

        try:
            await self.execute(lookup)
        except IntegrityError as i:
            if (missing := await self.find_missing(path)) is None:
                raise ConflictError.from_integrity_error(i).scoped(self.scope) from i

            raise NotFoundError(
                field_errors={missing: getattr(path, missing)},
            ).scoped(self.scope) from i

    @abstractmethod
    @override
    async def execute(self, lookup: dict) -> int:
        pass


########################################################################################


class LinkDetachOperation[Get: DTO](LinkOperation[Get], ABC):
    __slots__ = ()

    @override
    async def run(self, path: RelatedInstancePath) -> None:
        lookup: dict = self.build_lookup(path)

        if await self.execute(lookup):
            return

        await self.raise_missing(path)

    @abstractmethod
    @override
    async def execute(self, lookup: dict) -> int:
        pass


########################################################################################


class LinkInspectOperation[Get: DTO](LinkOperation[Get], ABC):
    __slots__ = ()

    @override
    async def run(self, path: RelatedInstancePath) -> Get:
        lookup: dict = self.build_lookup(path)

        try:
            obj: DatabaseModel = await self.execute(lookup)
        except ObjectDoesNotExist:
            await self.raise_missing(path)

        return self.map(obj)

    @abstractmethod
    @override
    async def execute(self, lookup: dict) -> DatabaseModel:
        pass


########################################################################################


class FlatLinkAttachOperation[Get: DTO](LinkAttachOperation[Get]):
    __slots__ = ()

    @override
    async def execute(self, lookup: dict) -> int:
        _, created = await self.qs.model._default_manager.aget_or_create(**lookup)  # ty: ignore[unresolved-attribute]

        return int(created)


########################################################################################


class FlatLinkDetachOperation[Get: DTO](LinkDetachOperation[Get]):
    __slots__ = ()

    @override
    async def execute(self, lookup: dict) -> int:
        deleted, _ = await self.qs.model._default_manager.filter(**lookup).adelete()  # ty: ignore[unresolved-attribute]

        return deleted


########################################################################################


class FlatLinkInspectOperation[Get: DTO](LinkInspectOperation[Get]):
    __slots__ = ()

    @override
    async def execute(self, lookup: dict) -> DatabaseModel:
        return await self.qs.aget(**lookup)
