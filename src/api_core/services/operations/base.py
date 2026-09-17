from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, override

from django.core.exceptions import ObjectDoesNotExist
from django.db import DataError, IntegrityError
from django.db.transaction import TransactionManagementError

from api_exceptions.enums import RequestScopes
from api_exceptions.errors import ConflictError, NotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import ClassVar

    from django.db.models import QuerySet

    from api_core.controllers.models.base import ModelController
    from api_core.schemas.base import DTO
    from api_core.schemas.path import InstancePath
    from api_core.services.mappers import ModelMapper
    from api_utils.types import DatabaseModel

########################################################################################


def split_payload(data: dict, names: Sequence[str]) -> tuple[dict, dict]:
    extracted: dict = {name: data[name] for name in names if name in data}

    payload: dict = {
        name: value for name, value in data.items() if name not in extracted
    }

    return payload, extracted


########################################################################################


class ModelOperation[Get: DTO](ABC):
    __slots__ = ("fields", "mapper", "qs", "schema")

    scope: ClassVar[RequestScopes] = RequestScopes.BODY

    def __init__(
        self,
        *fields: str,
        mapper: ModelMapper[Get],
        schema: type[Get],
        qs: QuerySet,
    ) -> None:
        self.fields: Sequence[str] = fields
        self.mapper: ModelMapper[Get] = mapper
        self.schema: type[Get] = schema
        self.qs: QuerySet = qs

    def dump(self, dto: DTO) -> dict:  # ruff: ignore[no-self-use]
        return dto.model_dump()

    @abstractmethod
    async def execute(self, *args, **kwargs):  # ruff: ignore[missing-return-type-undocumented-public-function, missing-type-args, missing-type-kwargs]
        pass

    def map(self, obj: DatabaseModel) -> Get:
        return self.mapper(obj, self.schema)

    @staticmethod
    def resolve_fields(ctrl: ModelController) -> frozenset[str]:  # ruff: ignore[unused-static-method-argument]
        return frozenset()

    @abstractmethod
    async def run(self, *args, **kwargs):  # ruff: ignore[missing-return-type-undocumented-public-function, missing-type-args, missing-type-kwargs]
        pass

    @classmethod
    @contextmanager
    def exc_handler(cls, lookup: dict | None = None) -> Iterator[None]:
        try:
            yield
        except IntegrityError as i:
            raise ConflictError.from_integrity_error(i).scoped(cls.scope) from i
        except (DataError, ObjectDoesNotExist) as o:
            # DataError covers values a column can't even represent
            # such a value can never match a row, so 404
            raise NotFoundError(field_errors=lookup).scoped(RequestScopes.PATH) from o
        except TransactionManagementError as t:
            # a query issued while unwinding an already-broken transaction
            # (like pgtrigger.ignore()'s cleanup) can mask the integrity
            # error that broke it; recover it from the chain instead of
            # surfacing an unrelated 500
            if isinstance(t.__cause__, IntegrityError):
                raise ConflictError.from_integrity_error(t.__cause__).scoped(
                    cls.scope,
                ) from t

            raise


########################################################################################


class CreateOperation[Get: DTO, Post: DTO](ModelOperation[Get], ABC):
    __slots__ = ()

    @override
    async def run(self, body: Post) -> Get:
        data: dict = self.dump(dto=body)

        with self.exc_handler():
            obj: DatabaseModel = await self.execute(data)

        return self.map(obj)


########################################################################################


class DestroyOperation[Get: DTO](ModelOperation[Get], ABC):
    __slots__ = ()

    scope: ClassVar[RequestScopes] = RequestScopes.PATH

    @override
    async def run(self, path: InstancePath) -> None:
        lookup: dict = path.model_dump()

        with self.exc_handler(lookup):
            deleted: int = await self.execute(lookup)

        if not deleted:
            raise NotFoundError(field_errors=lookup).scoped(RequestScopes.PATH)

    @abstractmethod
    @override
    async def execute(self, lookup: dict) -> int:
        pass


########################################################################################


class RetrieveOperation[Get: DTO](ModelOperation[Get], ABC):
    __slots__ = ()

    scope: ClassVar[RequestScopes] = RequestScopes.PATH

    @override
    async def run(self, path: InstancePath) -> Get:
        lookup: dict = path.model_dump()

        with self.exc_handler(lookup):
            obj: DatabaseModel = await self.execute(lookup)

        return self.map(obj)

    @abstractmethod
    @override
    async def execute(self, lookup: dict) -> DatabaseModel:
        pass


########################################################################################


class UpdateOperation[Get: DTO, Post: DTO](ModelOperation[Get], ABC):
    __slots__ = ("partial",)

    def __init__(
        self,
        *fields: str,
        mapper: ModelMapper[Get],
        partial: bool = False,
        schema: type[Get],
        qs: QuerySet,
    ) -> None:
        super().__init__(*fields, mapper=mapper, schema=schema, qs=qs)

        self.partial: bool = partial

    @override
    def dump(self, dto: DTO) -> dict:
        return dto.model_dump(exclude_unset=self.partial)

    @override
    async def run(self, body: Post, path: InstancePath) -> Get:
        lookup: dict = path.model_dump()

        data: dict = self.dump(dto=body)

        with self.exc_handler(lookup):
            obj: DatabaseModel = await self.execute(data, lookup)

        return self.map(obj)

    @abstractmethod
    @override
    async def execute(self, data: dict, lookup: dict) -> DatabaseModel:
        pass
