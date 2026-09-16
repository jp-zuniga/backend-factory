from http import HTTPStatus
from typing import ClassVar

from dmr import Body, Path, modify
from dmr.serializer import BaseSerializer

from api_core.controllers.components import StrictQuery
from api_core.schemas.base import DTO
from api_core.schemas.path import InstancePath, UuidInstancePath
from api_core.schemas.query import PatchManyToManyQuery, PutManyToManyQuery
from api_core.services.operations import (
    DestroyOperation,
    FlatRetrieveOperation,
    FlatUpdateOperation,
    ManyToManyUpdateOperation,
    NestedUpdateOperation,
    RetrieveOperation,
    UpdateOperation,
)
from api_core.services.operations.flat import FlatDestroyOperation
from api_utils.types import DatabaseModel

from .base import ModelController

########################################################################################


class ModelDetailController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    Get: DTO,
    Put: DTO,
    Patch: DTO,
    PathSchema: InstancePath = UuidInstancePath,
](ModelController[Serializer, Model, Get]):
    destroy_operation: ClassVar[type[DestroyOperation]] = FlatDestroyOperation
    retrieve_operation: ClassVar[type[RetrieveOperation]] = FlatRetrieveOperation
    update_operation: ClassVar[type[UpdateOperation]] = FlatUpdateOperation

    async def get(self, parsed_path: Path[PathSchema]) -> Get:
        return await self.build_operation(self.retrieve_operation).run(parsed_path)

    async def put(
        self,
        parsed_body: Body[Put],
        parsed_path: Path[PathSchema],
    ) -> Get:
        return await self.build_operation(
            self.update_operation,
            partial=False,
        ).run(
            body=parsed_body,
            path=parsed_path,
        )

    async def patch(
        self,
        parsed_body: Body[Patch],
        parsed_path: Path[PathSchema],
    ) -> Get:
        return await self.build_operation(
            self.update_operation,
            partial=True,
        ).run(
            body=parsed_body,
            path=parsed_path,
        )

    @modify(status_code=HTTPStatus.NO_CONTENT)
    async def delete(self, parsed_path: Path[PathSchema]) -> None:
        await self.build_operation(self.destroy_operation).run(parsed_path)


########################################################################################


class ModelReadOnlyDetailController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    Get: DTO,
    PathSchema: InstancePath = UuidInstancePath,
](ModelController[Serializer, Model, Get]):
    """
    Expose a single row that clients may read but never write.
    """

    retrieve_operation: ClassVar[type[RetrieveOperation]] = FlatRetrieveOperation

    async def get(self, parsed_path: Path[PathSchema]) -> Get:
        return await self.build_operation(self.retrieve_operation).run(parsed_path)


########################################################################################


class ModelReadUpdateDetailController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    Get: DTO,
    Put: DTO,
    Patch: DTO,
    PathSchema: InstancePath = UuidInstancePath,
](ModelController[Serializer, Model, Get]):
    """
    Expose a single row that clients may read and edit, but never delete.
    """

    retrieve_operation: ClassVar[type[RetrieveOperation]] = FlatRetrieveOperation
    update_operation: ClassVar[type[UpdateOperation]] = FlatUpdateOperation

    async def get(self, parsed_path: Path[PathSchema]) -> Get:
        return await self.build_operation(self.retrieve_operation).run(parsed_path)

    async def put(
        self,
        parsed_body: Body[Put],
        parsed_path: Path[PathSchema],
    ) -> Get:
        return await self.build_operation(
            self.update_operation,
            partial=False,
        ).run(
            body=parsed_body,
            path=parsed_path,
        )

    async def patch(
        self,
        parsed_body: Body[Patch],
        parsed_path: Path[PathSchema],
    ) -> Get:
        return await self.build_operation(
            self.update_operation,
            partial=True,
        ).run(
            body=parsed_body,
            path=parsed_path,
        )


########################################################################################


class ModelNestedDetailController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    Get: DTO,
    Put: DTO,
    Patch: DTO,
    PathSchema: InstancePath = UuidInstancePath,
](ModelDetailController[Serializer, Model, Get, Put, Patch, PathSchema]):
    update_operation: ClassVar[type[UpdateOperation]] = NestedUpdateOperation


########################################################################################


class ModelManyToManyDetailController[
    Serializer: BaseSerializer,
    Model: DatabaseModel,
    Get: DTO,
    Put: DTO,
    Patch: DTO,
    PathSchema: InstancePath = UuidInstancePath,
](ModelDetailController[Serializer, Model, Get, Put, Patch, PathSchema]):
    update_operation: ClassVar[type[UpdateOperation]] = ManyToManyUpdateOperation

    async def put(  # ty: ignore[invalid-method-override]
        self,
        parsed_body: Body[Put],
        parsed_path: Path[PathSchema],
        parsed_query: StrictQuery[PutManyToManyQuery],
    ) -> Get:
        return await self.build_operation(
            self.update_operation,
            partial=False,
            overwrite=parsed_query.overwrite,
        ).run(parsed_body, parsed_path)

    async def patch(  # ty: ignore[invalid-method-override]
        self,
        parsed_body: Body[Patch],
        parsed_path: Path[PathSchema],
        parsed_query: StrictQuery[PatchManyToManyQuery],
    ) -> Get:
        return await self.build_operation(
            self.update_operation,
            partial=True,
            overwrite=parsed_query.overwrite,
        ).run(parsed_body, parsed_path)
