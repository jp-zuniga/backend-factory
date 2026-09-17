from collections.abc import Sequence
from http import HTTPStatus

import pytest

from django.contrib.auth.models import Group, Permission
from django.db.models import QuerySet
from pydantic import PositiveInt

from api_auth.models import ApiUser
from api_auth.schemas.group import GroupGet, GroupInlineGet
from api_auth.schemas.permission import PermissionGet
from api_auth.schemas.user import ApiUserGet, ApiUserInlineGet
from api_core.schemas.base import DTO
from api_core.schemas.get import BaseGet
from api_core.schemas.pagination import PageQuery, Paginated
from api_core.services.mappers import (
    MAX_UNPAGINATED,
    PrefetchedProxy,
    instance_mapper,
    paginated_mapper,
    queryset_mapper,
)
from api_exceptions.enums import BadRequestErrorTypes
from api_exceptions.errors import BadRequestError
from api_tests.factories import build_users
from api_tests.sync import run
from api_utils.types import DatabaseModel

pytestmark = pytest.mark.django_db

########################################################################################


class _GroupMissingRelation(BaseGet[PositiveInt]):
    inexistente: list[PermissionGet]


########################################################################################


def test_prefetched_proxy_prefers_overrides(sample_group: Group) -> None:
    proxy = PrefetchedProxy(sample_group, {"name": "reemplazado"})

    assert proxy.name == "reemplazado"


def test_prefetched_proxy_falls_back_to_instance(sample_group: Group) -> None:
    proxy = PrefetchedProxy(sample_group, {"otro": ()})

    assert proxy.pk == sample_group.pk
    assert proxy.name == sample_group.name


def test_prefetched_proxy_propagates_missing_attribute(sample_group: Group) -> None:
    proxy = PrefetchedProxy(sample_group, {})

    with pytest.raises(AttributeError):
        proxy.atributo_inexistente  # ruff: ignore[useless-expression]


def test_prefetched_proxy_allows_falsy_overrides(sample_group: Group) -> None:
    proxy = PrefetchedProxy(sample_group, {"name": ""})

    assert proxy.name == ""  # ruff: ignore[compare-to-empty-string]


########################################################################################


def test_instance_mapper_without_collections(client_user: ApiUser) -> None:
    mapped: ApiUserInlineGet = instance_mapper(client_user, ApiUserInlineGet)

    assert isinstance(mapped, ApiUserInlineGet)
    assert mapped.id == client_user.pk
    assert mapped.username == client_user.username
    assert mapped.email == client_user.email
    assert mapped.is_active is True


def test_instance_mapper_resolves_related_managers(admin_user: ApiUser) -> None:
    mapped: ApiUserGet = instance_mapper(admin_user, ApiUserGet)

    assert {group.name for group in mapped.groups} == {
        group.name
        for group in admin_user.groups.all()  # ty: ignore[unresolved-attribute]
    }
    assert mapped.permissions == ()


def test_instance_mapper_maps_nested_children(
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(*sample_permissions)  # ty: ignore[unresolved-attribute]

    mapped: GroupGet = instance_mapper(sample_group, GroupGet)

    assert {perm.id for perm in mapped.permissions} == {
        perm.pk for perm in sample_permissions
    }
    assert all(perm.model for perm in mapped.permissions)


def test_instance_mapper_defaults_absent_relations_to_empty(
    sample_group: Group,
) -> None:
    mapped: _GroupMissingRelation = instance_mapper(sample_group, _GroupMissingRelation)

    assert mapped.inexistente == []


def test_instance_mapper_keeps_empty_collections(sample_group: Group) -> None:
    mapped: GroupGet = instance_mapper(sample_group, GroupGet)

    assert mapped.permissions == ()
    assert mapped.name == sample_group.name


########################################################################################


def test_queryset_mapper_returns_all_rows(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(3, prefix="mapeado")

    mapped: Sequence[ApiUserGet] = run(
        queryset_mapper,
        mapper=instance_mapper,
        schema=ApiUserGet,
        qs=user_qs.order_by("username"),
    )  # ty: ignore[invalid-assignment]

    assert len(mapped) == 3
    assert [user.username for user in mapped] == [
        "mapeado-0",
        "mapeado-1",
        "mapeado-2",
    ]


def test_queryset_mapper_on_empty_queryset(user_qs: QuerySet) -> None:
    assert (
        run(
            queryset_mapper,
            mapper=instance_mapper,
            schema=ApiUserGet,
            qs=user_qs,
        )
        == []
    )


def test_queryset_mapper_rejects_oversized_results(
    monkeypatch: pytest.MonkeyPatch,
    plain_group_qs: QuerySet,
) -> None:
    Group.objects.bulk_create([Group(name=f"grupo-{index}") for index in range(4)])

    monkeypatch.setattr("api_core.services.mappers.MAX_UNPAGINATED", 2)

    with pytest.raises(BadRequestError) as raised:
        run(
            queryset_mapper,
            mapper=instance_mapper,
            schema=GroupInlineGet,
            qs=plain_group_qs,
        )

    assert raised.value.default_http_status == HTTPStatus.BAD_REQUEST
    assert raised.value.detail == BadRequestErrorTypes.FAILED_VALIDATION.value
    assert "query.detail" in raised.value.field_errors


def test_queryset_mapper_allows_exactly_the_limit(
    monkeypatch: pytest.MonkeyPatch,
    plain_group_qs: QuerySet,
) -> None:
    Group.objects.bulk_create([Group(name=f"limite-{index}") for index in range(2)])

    limit: int = Group.objects.count()

    monkeypatch.setattr("api_core.services.mappers.MAX_UNPAGINATED", limit)

    mapped = run(
        queryset_mapper,
        mapper=instance_mapper,
        schema=GroupInlineGet,
        qs=plain_group_qs,
    )

    assert len(mapped) == limit


def test_max_unpaginated_is_a_sane_default() -> None:
    assert MAX_UNPAGINATED == 10_000


########################################################################################


def test_paginated_mapper_first_page(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(5, prefix="paginado")

    page: Paginated[ApiUserGet] = run(
        paginated_mapper,
        mapper=instance_mapper,
        schema=ApiUserGet,
        qs=user_qs.order_by("username"),
        query=PageQuery(page=1, page_size=2),
    )  # ty: ignore[invalid-assignment]

    assert page.current == 1
    assert page.elements == 5
    assert page.pages == 3
    assert page.next is True
    assert page.previous is False
    assert [user.username for user in page.results] == ["paginado-0", "paginado-1"]


def test_paginated_mapper_last_page(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(5, prefix="paginado")

    page: Paginated[ApiUserGet] = run(
        paginated_mapper,
        mapper=instance_mapper,
        schema=ApiUserGet,
        qs=user_qs.order_by("username"),
        query=PageQuery(page=3, page_size=2),
    )  # ty: ignore[invalid-assignment]

    assert page.current == 3
    assert page.next is False
    assert page.previous is True
    assert len(page.results) == 1


def test_paginated_mapper_on_empty_queryset(user_qs: QuerySet) -> None:
    page: Paginated[ApiUserGet] = run(
        paginated_mapper,
        mapper=instance_mapper,
        schema=ApiUserGet,
        qs=user_qs,
        query=PageQuery(),
    )  # ty: ignore[invalid-assignment]

    assert page.elements == 0
    assert page.pages == 1
    assert page.results == []
    assert page.next is False
    assert page.previous is False


def test_paginated_mapper_rejects_missing_page(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(1, prefix="paginado")

    with pytest.raises(BadRequestError) as raised:
        run(
            paginated_mapper,
            mapper=instance_mapper,
            schema=ApiUserGet,
            qs=user_qs,
            query=PageQuery(page=9, page_size=2),
        )

    assert raised.value.field_errors == {
        "query.page": "La página especificada no existe.",
    }


def test_paginated_mapper_uses_provided_mapper(
    user_qs: QuerySet,
    client_user: ApiUser,
) -> None:
    calls: list[type] = []

    def spy[T: DTO](obj: DatabaseModel, schema: type[T]) -> T:
        calls.append(schema)

        return instance_mapper(obj, schema)

    page: Paginated[ApiUserGet] = run(
        paginated_mapper,
        mapper=spy,
        schema=ApiUserGet,
        qs=user_qs,
        query=PageQuery(),
    )  # ty: ignore[invalid-assignment]

    assert calls == [ApiUserGet]
    assert len(page.results) == 1
