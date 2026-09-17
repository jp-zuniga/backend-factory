from http import HTTPStatus

import pytest

from django.contrib.auth.models import Group, Permission
from django.db.models import QuerySet

from api_auth.models import ApiUser
from api_auth.schemas.group import GroupGet
from api_core.schemas.base import DTO
from api_core.schemas.path import IntInstancePath
from api_core.services.mappers import instance_mapper
from api_core.services.operations import (
    ManyToManyCreateOperation,
    ManyToManyUpdateOperation,
)
from api_core.services.operations.m2m import (
    exec_m2m_post,
    exec_m2m_update,
    m2m_handler,
    validate_existing_ids,
)
from api_exceptions.enums import BadRequestErrorTypes, ConflictErrorTypes
from api_exceptions.errors import BadRequestError, ConflictError, NotFoundError
from api_tests.sync import run

########################################################################################

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


class _GroupWrite(DTO):
    name: str
    permissions: list[int] | None = None


class _GroupPatch(DTO):
    name: str | None = None
    permissions: list[int] | None = None


########################################################################################


def test_validate_existing_ids_accepts_known_rows(
    sample_permissions: list[Permission],
) -> None:
    validate_existing_ids(
        {"permissions": [perm.pk for perm in sample_permissions]},
        Group,
    )


def test_validate_existing_ids_skips_empty_collections() -> None:
    validate_existing_ids({"permissions": []}, Group)
    validate_existing_ids({}, Group)


def test_validate_existing_ids_reports_missing_positions(
    sample_permissions: list[Permission],
) -> None:
    provided: list[int] = [sample_permissions[0].pk, 987654, 987655]

    with pytest.raises(BadRequestError) as raised:
        validate_existing_ids({"permissions": provided}, Group)

    assert raised.value.default_http_status == HTTPStatus.BAD_REQUEST
    assert raised.value.detail == BadRequestErrorTypes.FAILED_VALIDATION.value
    assert raised.value.field_errors == {
        "body.permissions.1": (
            "No existe un registro relacionado con el valor '987654'."
        ),
        "body.permissions.2": (
            "No existe un registro relacionado con el valor '987655'."
        ),
    }


def test_validate_existing_ids_follows_forward_descriptors(
    seeded_groups: dict[str, Group],
) -> None:
    with pytest.raises(BadRequestError) as raised:
        validate_existing_ids({"groups": [987654]}, ApiUser)

    assert "body.groups.0" in raised.value.field_errors


def test_validate_existing_ids_follows_reverse_descriptors(
    client_user: ApiUser,
) -> None:
    validate_existing_ids({"users": [client_user.pk]}, Group)

    with pytest.raises(BadRequestError):
        validate_existing_ids(
            {"users": ["00000000-0000-7000-8000-000000000000"]},
            Group,
        )


########################################################################################


def test_m2m_handler_adds_without_replacing(
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0])  # ty: ignore[unresolved-attribute]

    m2m_handler(
        m2m_inputs={"permissions": [sample_permissions[1].pk]},
        obj=sample_group,
    )

    assert sample_group.permissions.count() == 2  # ty: ignore[unresolved-attribute]


def test_m2m_handler_replaces_when_overwriting(
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0], sample_permissions[1])  # ty: ignore[unresolved-attribute]

    m2m_handler(
        m2m_inputs={"permissions": [sample_permissions[2].pk]},
        obj=sample_group,
        overwrite=True,
    )

    assert [perm.pk for perm in sample_group.permissions.all()] == [  # ty: ignore[unresolved-attribute]
        sample_permissions[2].pk,
    ]


def test_m2m_handler_clears_on_empty_overwrite(
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(*sample_permissions)  # ty: ignore[unresolved-attribute]

    m2m_handler(m2m_inputs={"permissions": []}, obj=sample_group, overwrite=True)

    assert sample_group.permissions.count() == 0  # ty: ignore[unresolved-attribute]


def test_m2m_handler_is_a_noop_on_empty_add(
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0])  # ty: ignore[unresolved-attribute]

    m2m_handler(m2m_inputs={"permissions": []}, obj=sample_group)

    assert sample_group.permissions.count() == 1  # ty: ignore[unresolved-attribute]


def test_m2m_handler_scopes_integrity_errors(
    client_user: ApiUser,
    seeded_groups: dict[str, Group],
) -> None:
    with pytest.raises(ConflictError) as raised:
        m2m_handler(m2m_inputs={"groups": [987654]}, obj=client_user)

    assert raised.value.default_http_status == HTTPStatus.CONFLICT
    assert raised.value.detail == ConflictErrorTypes.BAD_FOREIGN.value
    assert all(key.startswith("body.groups.") for key in raised.value.field_errors), (
        raised.value.field_errors
    )


def test_m2m_handler_handles_several_relations(
    client_user: ApiUser,
    sample_permissions: list[Permission],
) -> None:
    m2m_handler(
        m2m_inputs={
            "groups": [],
            "permissions": [perm.pk for perm in sample_permissions],
        },
        obj=client_user,
    )

    assert client_user.permissions.count() == len(sample_permissions)  # ty: ignore[unresolved-attribute]


########################################################################################


def test_exec_m2m_post_creates_row_with_relations(
    plain_group_qs: QuerySet,
    sample_permissions: list[Permission],
) -> None:
    created = exec_m2m_post(
        "permissions",
        data={
            "name": "creado-con-permisos",
            "permissions": [perm.pk for perm in sample_permissions],
        },
        qs=plain_group_qs,
    )

    assert created.name == "creado-con-permisos"  # ty: ignore[unresolved-attribute]
    assert created.permissions.count() == len(sample_permissions)  # ty: ignore[unresolved-attribute]


def test_exec_m2m_post_normalizes_none_relations(plain_group_qs: QuerySet) -> None:
    created = exec_m2m_post(
        "permissions",
        data={"name": "sin-permisos", "permissions": None},
        qs=plain_group_qs,
    )

    assert created.permissions.count() == 0  # ty: ignore[unresolved-attribute]


def test_exec_m2m_post_validates_before_inserting(plain_group_qs: QuerySet) -> None:
    with pytest.raises(BadRequestError):
        exec_m2m_post(
            "permissions",
            data={"name": "nunca-creado", "permissions": [987654]},
            qs=plain_group_qs,
        )

    assert not Group.objects.filter(name="nunca-creado").exists()


def test_exec_m2m_post_routes_users_through_manager(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    created = exec_m2m_post(
        "groups",
        "permissions",
        data={
            "username": "creado-por-manager",
            "password": "Contrasena-De-Servicios-5",
            "email": "manager@pruebas.example.com",
            "first_name": "",
            "last_name": "",
            "groups": [],
            "permissions": [],
        },
        qs=user_qs,
        user=True,
    )

    assert created.username == "creado-por-manager"  # ty: ignore[unresolved-attribute]
    assert created.is_active is True  # ty: ignore[unresolved-attribute]
    assert created.check_password("Contrasena-De-Servicios-5")  # ty: ignore[unresolved-attribute]


########################################################################################


def test_exec_m2m_update_merges_relations(
    group_qs: QuerySet,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0])  # ty: ignore[unresolved-attribute]

    updated = exec_m2m_update(
        "permissions",
        data={"permissions": [sample_permissions[1].pk]},
        lookup={"id": sample_group.pk},
        overwrite=False,
        qs=group_qs,
    )

    assert updated.permissions.count() == 2  # ty: ignore[unresolved-attribute]


def test_exec_m2m_update_overwrites_relations(
    group_qs: QuerySet,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0], sample_permissions[1])  # ty: ignore[unresolved-attribute]

    updated = exec_m2m_update(
        "permissions",
        data={"permissions": [sample_permissions[2].pk]},
        lookup={"id": sample_group.pk},
        overwrite=True,
        qs=group_qs,
    )

    assert [perm.pk for perm in updated.permissions.all()] == [  # ty: ignore[unresolved-attribute]
        sample_permissions[2].pk,
    ]


def test_exec_m2m_update_writes_scalar_payload(
    group_qs: QuerySet,
    sample_group: Group,
) -> None:
    updated = exec_m2m_update(
        "permissions",
        data={"name": "renombrado-por-servicio"},
        lookup={"id": sample_group.pk},
        overwrite=False,
        qs=group_qs,
    )

    assert updated.name == "renombrado-por-servicio"  # ty: ignore[unresolved-attribute]


def test_exec_m2m_update_requires_existing_row(group_qs: QuerySet) -> None:
    with pytest.raises(NotFoundError):
        exec_m2m_update(
            "permissions",
            data={"name": "fantasma"},
            lookup={"id": 424242},
            overwrite=False,
            qs=group_qs,
        )


########################################################################################


def test_many_to_many_create_operation(
    group_qs: QuerySet,
    sample_permissions: dict[str, Group],
) -> None:
    operation = ManyToManyCreateOperation(
        "permissions",
        mapper=instance_mapper,
        schema=GroupGet,
        qs=group_qs,
    )

    created: GroupGet = run(
        operation.run,
        _GroupWrite(
            name="creado-por-operacion",
            permissions=[perm.pk for perm in sample_permissions],  # ty: ignore[unresolved-attribute]
        ),
    )

    assert created.name == "creado-por-operacion"
    assert len(created.permissions) == len(sample_permissions)


def test_many_to_many_update_operation_partial(
    group_qs: QuerySet,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    operation = ManyToManyUpdateOperation(
        "permissions",
        mapper=instance_mapper,
        overwrite=False,
        partial=True,
        schema=GroupGet,
        qs=group_qs,
    )

    assert operation.overwrite is False
    assert operation.partial is True

    updated: GroupGet = run(
        operation.run,
        _GroupPatch(permissions=[sample_permissions[0].pk]),
        IntInstancePath(id=sample_group.pk),
    )

    assert updated.name == sample_group.name
    assert len(updated.permissions) == 1


def test_many_to_many_update_operation_overwrites(
    group_qs: QuerySet,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(*sample_permissions)  # ty: ignore[unresolved-attribute]

    operation = ManyToManyUpdateOperation(
        "permissions",
        mapper=instance_mapper,
        overwrite=True,
        schema=GroupGet,
        qs=group_qs,
    )

    updated: GroupGet = run(
        operation.run,
        _GroupWrite(name=sample_group.name, permissions=[]),  # ty: ignore[invalid-argument-type]
        IntInstancePath(id=sample_group.pk),
    )

    assert updated.permissions == ()
