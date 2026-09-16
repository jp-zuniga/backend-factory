from typing import ClassVar, override

from django_filters import FilterSet
from dmr import Body
from dmr.serializer import BaseSerializer

from api_core.controllers.mixins import ParentScopedMixin
from api_core.schemas.base import DTO
from api_core.schemas.filters import PaginatedFilterQuery
from api_core.schemas.path import InstancePath, UuidInstancePath
from api_core.services.operations import (
    CreateOperation,
    ScopedCreateOperation,
    UpdateOperation,
)
from api_core.services.operations.flat import ForeignKeyUpdateOperation
from api_utils.types import DatabaseModel

from .detail import ModelReadUpdateDetailController
from .list import ModelListController, ModelReadOnlyListController

########################################################################################


class ScopedDetailController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    Get: DTO,
    Put: DTO,
    Patch: DTO,
    PathSchema: InstancePath = UuidInstancePath,
](
    ParentScopedMixin,
    ModelReadUpdateDetailController[Serializer, Model, Get, Put, Patch, PathSchema],
):
    """
    Expose one row of a sub-resource, e.g. `/parent/{parent_id}/children/{id}/`.

    Rows filed under another parent are invisible here:
    they answer `404`, the same as rows that do not exist at all.
    """

    update_operation: ClassVar[type[UpdateOperation]] = ForeignKeyUpdateOperation


########################################################################################


class ScopedListController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: PaginatedFilterQuery,
    Get: DTO,
    Post: DTO,
    PaginatedGet: DTO,
](
    ParentScopedMixin,
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
    """
    Expose a sub-resource collection, e.g. `/parent/{parent_id}/children/`.

    Both halves read the parent off the path: the listing only
    returns its children, and a create files the new row under it.
    """

    create_operation: ClassVar[type[CreateOperation]] = ScopedCreateOperation

    @override
    async def post(self, parsed_body: Body[Post]) -> Get:
        return await self.build_operation(
            self.create_operation,
            defaults={self.__class__.parent_param(): self.parent_id},
        ).run(body=parsed_body)


########################################################################################


class ScopedReadOnlyListController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    ModelFilter: FilterSet,
    FilterQuery: PaginatedFilterQuery,
    Get: DTO,
    PaginatedGet: DTO,
](
    ParentScopedMixin,
    ModelReadOnlyListController[
        Serializer,
        Model,
        ModelFilter,
        FilterQuery,
        Get,
        PaginatedGet,
    ],
):
    """
    Expose a sub-resource collection that clients may read but never write.
    """
