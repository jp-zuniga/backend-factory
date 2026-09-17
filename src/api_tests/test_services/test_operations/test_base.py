from http import HTTPStatus

import pytest

from django.contrib.auth.models import Group
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import QuerySet

from api_auth.controllers.user import ApiUserListController
from api_auth.models import ApiUser
from api_auth.schemas.group import GroupGet, GroupInlineGet
from api_auth.schemas.user import ApiUserGet
from api_core.schemas.base import DTO
from api_core.schemas.path import IntInstancePath, UuidInstancePath
from api_core.services.mappers import instance_mapper
from api_core.services.operations import (
    FlatCreateOperation,
    FlatRetrieveOperation,
    FlatUpdateOperation,
    ManyToManyCreateOperation,
)
from api_core.services.operations.base import split_payload
from api_core.services.operations.flat import FlatDestroyOperation
from api_exceptions.enums import ConflictErrorTypes, RequestScopes
from api_exceptions.errors import ConflictError, NotFoundError
from api_tests.sync import run

pytestmark = pytest.mark.django_db

########################################################################################


class _GroupNameWrite(DTO):
    name: str


class _GroupPartialWrite(DTO):
    name: str | None = None


########################################################################################


@pytest.mark.parametrize(
    ("data", "names", "expected"),
    [
        ({}, (), ({}, {})),
        ({"a": 1}, (), ({"a": 1}, {})),
        ({"a": 1, "b": 2}, ("b",), ({"a": 1}, {"b": 2})),
        ({"a": 1, "b": 2}, ("a", "b"), ({}, {"a": 1, "b": 2})),
        ({"a": 1}, ("ausente",), ({"a": 1}, {})),
        ({"a": None}, ("a",), ({}, {"a": None})),
    ],
)
def test_split_payload(data: dict, names: tuple, expected: tuple) -> None:
    assert split_payload(data, names) == expected


def test_split_payload_does_not_mutate_input() -> None:
    data: dict = {"a": 1, "b": 2}

    split_payload(data, ("b",))

    assert data == {"a": 1, "b": 2}


########################################################################################


def test_default_resolve_fields_is_empty(
    list_controller: ApiUserListController,
) -> None:
    assert FlatCreateOperation.resolve_fields(list_controller) == frozenset()


def test_many_to_many_resolve_fields_uses_resolver(
    list_controller: ApiUserListController,
) -> None:
    assert ManyToManyCreateOperation.resolve_fields(list_controller) == frozenset({
        "groups",
        "permissions",
    })


def test_operation_stores_construction_arguments(plain_group_qs: QuerySet) -> None:
    operation = FlatCreateOperation(
        "uno",
        "dos",
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    assert operation.fields == ("uno", "dos")
    assert operation.schema is GroupInlineGet
    assert operation.qs is plain_group_qs
    assert operation.mapper is instance_mapper


def test_operation_scopes(plain_group_qs: QuerySet) -> None:
    assert FlatCreateOperation.scope is RequestScopes.BODY
    assert FlatRetrieveOperation.scope is RequestScopes.PATH
    assert FlatDestroyOperation.scope is RequestScopes.PATH
    assert FlatUpdateOperation.scope is RequestScopes.BODY


def test_operation_map_delegates_to_mapper(
    sample_group: Group,
    plain_group_qs: QuerySet,
) -> None:
    operation = FlatRetrieveOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    assert operation.map(sample_group) == GroupInlineGet(
        id=sample_group.pk,
        name=sample_group.name,  # ty: ignore[invalid-argument-type]
    )


def test_operation_dump_uses_full_payload(plain_group_qs: QuerySet) -> None:
    operation = FlatCreateOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    assert operation.dump(_GroupPartialWrite()) == {"name": None}


def test_update_operation_dump_respects_partial(plain_group_qs: QuerySet) -> None:
    partial = FlatUpdateOperation(
        mapper=instance_mapper,
        partial=True,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    complete = FlatUpdateOperation(
        mapper=instance_mapper,
        partial=False,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    assert partial.partial is True
    assert partial.dump(_GroupPartialWrite()) == {}
    assert complete.dump(_GroupPartialWrite()) == {"name": None}


########################################################################################


def test_exc_handler_maps_integrity_error_to_conflict() -> None:
    with pytest.raises(ConflictError) as raised, FlatCreateOperation.exc_handler():
        raise IntegrityError

    assert raised.value.default_http_status == HTTPStatus.CONFLICT


def test_exc_handler_maps_missing_object_to_not_found() -> None:
    lookup: dict = {"id": 7}

    with (
        pytest.raises(NotFoundError) as raised,
        FlatRetrieveOperation.exc_handler(
            lookup,
        ),
    ):
        raise ObjectDoesNotExist

    assert raised.value.field_errors == {
        "path.id": "No existe un registro con el valor '7'.",
    }


def test_exc_handler_without_lookup() -> None:
    with pytest.raises(NotFoundError) as raised, FlatRetrieveOperation.exc_handler():
        raise ObjectDoesNotExist

    assert raised.value.field_errors == {}


def test_exc_handler_lets_other_errors_through() -> None:
    with pytest.raises(RuntimeError), FlatCreateOperation.exc_handler():
        raise RuntimeError


########################################################################################


def test_flat_create_returns_mapped_instance(plain_group_qs: QuerySet) -> None:
    operation = FlatCreateOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    created: GroupInlineGet = run(operation.run, _GroupNameWrite(name="creado"))

    assert created.name == "creado"
    assert Group.objects.filter(pk=created.id).exists()


def test_flat_create_maps_unique_violation(plain_group_qs: QuerySet) -> None:
    Group.objects.create(name="duplicado")

    operation = FlatCreateOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    with pytest.raises(ConflictError) as raised:
        run(operation.run, _GroupNameWrite(name="duplicado"))

    assert raised.value.detail == ConflictErrorTypes.UNIQUE.value
    assert raised.value.field_errors == {
        "body.name": "Ya existe un registro con el valor proporcionado.",
    }


########################################################################################


def test_flat_retrieve_returns_instance(
    sample_group: Group,
    plain_group_qs: QuerySet,
) -> None:
    operation = FlatRetrieveOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    found: GroupInlineGet = run(operation.run, IntInstancePath(id=sample_group.pk))

    assert found.id == sample_group.pk


def test_flat_retrieve_raises_not_found(plain_group_qs: QuerySet) -> None:
    operation = FlatRetrieveOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    with pytest.raises(NotFoundError) as raised:
        run(operation.run, IntInstancePath(id=424242))

    assert raised.value.field_errors == {
        "path.id": "No existe un registro con el valor '424242'.",
    }


def test_flat_retrieve_uses_annotated_queryset(
    client_user: ApiUser, user_qs: QuerySet
) -> None:
    operation = FlatRetrieveOperation(
        mapper=instance_mapper,
        schema=ApiUserGet,
        qs=user_qs,
    )

    found: ApiUserGet = run(operation.run, UuidInstancePath(id=client_user.pk))

    assert found.id == client_user.pk
    assert len(found.groups) == 1


########################################################################################


def test_flat_update_applies_changes(
    sample_group: Group,
    plain_group_qs: QuerySet,
) -> None:
    operation = FlatUpdateOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    updated: GroupInlineGet = run(
        operation.run,
        _GroupNameWrite(name="renombrado"),
        IntInstancePath(id=sample_group.pk),
    )

    sample_group.refresh_from_db()

    assert updated.name == "renombrado"
    assert sample_group.name == "renombrado"


def test_flat_update_with_empty_partial_payload(
    sample_group: Group,
    plain_group_qs: QuerySet,
) -> None:
    operation = FlatUpdateOperation(
        mapper=instance_mapper,
        partial=True,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    updated: GroupInlineGet = run(
        operation.run,
        _GroupPartialWrite(),
        IntInstancePath(id=sample_group.pk),
    )

    assert updated.name == sample_group.name


def test_flat_update_raises_not_found_when_row_is_absent(
    plain_group_qs: QuerySet,
) -> None:
    operation = FlatUpdateOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    with pytest.raises(NotFoundError) as raised:
        run(
            operation.run,
            _GroupNameWrite(name="fantasma"),
            IntInstancePath(id=424242),
        )

    assert raised.value.field_errors == {
        "path.id": "No existe un registro con el valor '424242'.",
    }


def test_flat_update_raises_not_found_on_empty_payload(
    plain_group_qs: QuerySet,
) -> None:
    operation = FlatUpdateOperation(
        mapper=instance_mapper,
        partial=True,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    with pytest.raises(NotFoundError):
        run(operation.run, _GroupPartialWrite(), IntInstancePath(id=424242))


def test_flat_update_maps_unique_violation(
    sample_group: Group,
    plain_group_qs: QuerySet,
) -> None:
    Group.objects.create(name="ocupado")

    operation = FlatUpdateOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    with pytest.raises(ConflictError) as raised:
        run(
            operation.run,
            _GroupNameWrite(name="ocupado"),
            IntInstancePath(id=sample_group.pk),
        )

    assert raised.value.detail == ConflictErrorTypes.UNIQUE.value


########################################################################################


def test_flat_destroy_removes_row(
    sample_group: Group, plain_group_qs: QuerySet
) -> None:
    operation = FlatDestroyOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    assert run(operation.run, IntInstancePath(id=sample_group.pk)) is None
    assert not Group.objects.filter(pk=sample_group.pk).exists()


def test_flat_destroy_raises_not_found(plain_group_qs: QuerySet) -> None:
    operation = FlatDestroyOperation(
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    with pytest.raises(NotFoundError) as raised:
        run(operation.run, IntInstancePath(id=424242))

    assert raised.value.field_errors == {
        "path.id": "No existe un registro con el valor '424242'.",
    }


def test_flat_destroy_strips_prefetches(
    sample_group: Group,
    group_qs: QuerySet,
) -> None:
    operation = FlatDestroyOperation(
        mapper=instance_mapper,
        schema=GroupGet,
        qs=group_qs,
    )

    assert group_qs._prefetch_related_lookups  # ruff: ignore[private-member-access]  # ty: ignore[redundant-condition]

    run(operation.run, IntInstancePath(id=sample_group.pk))

    assert not Group.objects.filter(pk=sample_group.pk).exists()
