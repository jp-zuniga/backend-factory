from collections.abc import Iterable
from typing import ClassVar

from django.db.models import QuerySet
from django_filters import FilterSet
from dmr import Body
from dmr.serializer import BaseSerializer

from api_core.controllers.components import StrictQuery
from api_core.schemas.base import DTO
from api_core.schemas.filters import PaginatedFilterQuery, UnpaginatedFilterQuery
from api_core.services.filtersets import apply_filterset
from api_core.services.mappers import paginated_mapper, queryset_mapper
from api_core.services.operations import (
    CreateOperation,
    FlatCreateOperation,
    ManyToManyCreateOperation,
    NestedCreateOperation,
)
from api_core.services.relations import collect_m2m_names
from api_utils.types import DatabaseModel

from .base import ModelController

########################################################################################


class ModelListController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: PaginatedFilterQuery,
    Get: DTO,
    Post: DTO,
    PaginatedGet: DTO,
](ModelController[Serializer, Model, Get]):
    create_operation: ClassVar[type[CreateOperation]] = FlatCreateOperation

    filterset: type[ModelFilter]

    async def get(self, parsed_query: StrictQuery[FilterQuery]) -> PaginatedGet:
        filtered: QuerySet = await apply_filterset(
            filterset=self.filterset,
            data=parsed_query.get_filters(),
            qs=self.qs,
        )

        return await paginated_mapper(  # ty:ignore[invalid-return-type]
            mapper=self.mapper,
            schema=self.schema,
            qs=filtered,
            query=parsed_query,
        )

    async def post(self, parsed_body: Body[Post]) -> Get:
        return await self.build_operation(self.create_operation).run(body=parsed_body)


########################################################################################


class ModelReadOnlyListController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: PaginatedFilterQuery,
    Get: DTO,
    PaginatedGet: DTO,
](ModelController[Serializer, Model, Get]):
    """
    Expose a paginated collection that clients may read but never write.
    """

    filterset: type[ModelFilter]

    async def get(self, parsed_query: StrictQuery[FilterQuery]) -> PaginatedGet:
        filtered: QuerySet = await apply_filterset(
            filterset=self.filterset,
            data=parsed_query.get_filters(),
            qs=self.qs,
        )

        return await paginated_mapper(  # ty:ignore[invalid-return-type]
            mapper=self.mapper,
            schema=self.schema,
            qs=filtered,
            query=parsed_query,
        )


########################################################################################


class ModelListAllController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: UnpaginatedFilterQuery,
    Get: DTO,
    ListGet: Iterable[DTO],
](ModelController[Serializer, Model, Get]):
    filterset: type[ModelFilter]

    def __init_subclass__(cls, **kwargs) -> None:  # ruff: ignore[missing-type-kwargs]
        super().__init_subclass__(**kwargs)

        if cls.is_abstract or not hasattr(cls, "schema"):
            return

        nested: frozenset[str] = collect_m2m_names(cls.schema)

        if nested:
            raise TypeError(
                f"{cls.__name__} no puede exponer las siguientes "
                "colecciones anidadas sin paginar: "
                f"{', '.join(sorted(nested))}.",
            )

    async def get(self, parsed_query: StrictQuery[FilterQuery]) -> ListGet:
        filtered: QuerySet = await apply_filterset(
            filterset=self.filterset,
            data=parsed_query.get_filters(),
            qs=self.qs,
        )

        return await queryset_mapper(  # ty:ignore[invalid-return-type]
            mapper=self.mapper,
            schema=self.schema,
            qs=filtered,
        )


########################################################################################


class ModelNestedListController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: PaginatedFilterQuery,
    Get: DTO,
    Post: DTO,
    PaginatedGet: DTO,
](
    ModelListController[
        Serializer,
        Model,
        ModelFilter,
        FilterQuery,
        Get,
        Post,
        PaginatedGet,
    ],
):
    create_operation: ClassVar[type[CreateOperation]] = NestedCreateOperation


########################################################################################


class ModelManyToManyListController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: PaginatedFilterQuery,
    Get: DTO,
    Post: DTO,
    PaginatedGet: DTO,
](
    ModelListController[
        Serializer,
        Model,
        ModelFilter,
        FilterQuery,
        Get,
        Post,
        PaginatedGet,
    ],
):
    create_operation: ClassVar[type[CreateOperation]] = ManyToManyCreateOperation
