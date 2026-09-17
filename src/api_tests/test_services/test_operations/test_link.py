from http import HTTPStatus
from uuid import uuid7

import pytest

from django.contrib.auth.models import Group
from django.db.models import QuerySet

from api_auth.controllers.user import (
    ApiUserGroupsLinkController,
    ApiUserPermissionsLinkController,
)
from api_auth.models import ApiUser, ApiUserGroups, ApiUserPermissions
from api_auth.schemas.through import ApiUserGroupsLinkGet
from api_core.schemas.path import UuidToIntRelatedPath
from api_core.services.mappers import instance_mapper
from api_core.services.operations import (
    FlatLinkAttachOperation,
    FlatLinkDetachOperation,
    FlatLinkInspectOperation,
)
from api_exceptions.errors import NotFoundError
from api_tests.sync import run

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


@pytest.fixture
def attach(user_groups_qs: QuerySet) -> FlatLinkAttachOperation:
    return FlatLinkAttachOperation(
        mapper=instance_mapper,
        parent="api_user",
        related="group",
        schema=ApiUserGroupsLinkGet,
        qs=user_groups_qs,
    )


@pytest.fixture
def detach(user_groups_qs: QuerySet) -> FlatLinkDetachOperation:
    return FlatLinkDetachOperation(
        mapper=instance_mapper,
        parent="api_user",
        related="group",
        schema=ApiUserGroupsLinkGet,
        qs=user_groups_qs,
    )


@pytest.fixture
def inspect(user_groups_qs: QuerySet) -> FlatLinkInspectOperation:
    return FlatLinkInspectOperation(
        mapper=instance_mapper,
        parent="api_user",
        related="group",
        schema=ApiUserGroupsLinkGet,
        qs=user_groups_qs,
    )


########################################################################################


def test_controller_resolves_link_endpoints() -> None:
    assert ApiUserGroupsLinkController.parent_model() is ApiUser
    assert ApiUserGroupsLinkController.related_model() is Group
    assert ApiUserGroupsLinkController.model is ApiUserGroups
    assert ApiUserPermissionsLinkController.parent_model() is ApiUser
    assert ApiUserPermissionsLinkController.model is ApiUserPermissions


########################################################################################


def test_build_lookup_uses_column_names(
    attach: FlatLinkAttachOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    lookup: dict = attach.build_lookup(
        UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk),
    )

    assert lookup == {
        "api_user_id": client_user.pk,
        "group_id": sample_group.pk,
    }


def test_operation_stores_relation_names(attach: FlatLinkAttachOperation) -> None:
    assert attach.parent == "api_user"
    assert attach.related == "group"


########################################################################################


def test_find_missing_returns_none_when_both_exist(
    attach: FlatLinkAttachOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    path = UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk)

    assert run(attach.find_missing, path) is None


def test_find_missing_flags_absent_parent(
    attach: FlatLinkAttachOperation,
    sample_group: Group,
) -> None:
    path = UuidToIntRelatedPath(id=uuid7(), related=sample_group.pk)

    assert run(attach.find_missing, path) == "id"


def test_find_missing_flags_absent_related(
    attach: FlatLinkAttachOperation,
    client_user: ApiUser,
) -> None:
    path = UuidToIntRelatedPath(id=client_user.pk, related=987654)

    assert run(attach.find_missing, path) == "related"


def test_find_missing_prefers_parent(attach: FlatLinkAttachOperation) -> None:
    path = UuidToIntRelatedPath(id=uuid7(), related=987654)

    assert run(attach.find_missing, path) == "id"


########################################################################################


def test_attach_creates_link(
    attach: FlatLinkAttachOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    result = run(
        attach.run,
        UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk),
    )

    assert result is None
    assert ApiUserGroups.objects.filter(
        api_user=client_user,
        group=sample_group,
    ).exists()


def test_attach_is_idempotent(
    attach: FlatLinkAttachOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    path = UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk)

    run(attach.run, path)
    run(attach.run, path)

    assert (
        ApiUserGroups.objects.filter(
            api_user=client_user,
            group=sample_group,
        ).count()
        == 1
    )


def test_attach_reports_missing_parent(
    attach: FlatLinkAttachOperation,
    sample_group: Group,
) -> None:
    missing = uuid7()

    with pytest.raises(NotFoundError) as raised:
        run(attach.run, UuidToIntRelatedPath(id=missing, related=sample_group.pk))

    assert raised.value.default_http_status == HTTPStatus.NOT_FOUND
    assert raised.value.field_errors == {
        "path.id": f"No existe un registro con el valor '{missing}'.",
    }


def test_attach_reports_missing_related(
    attach: FlatLinkAttachOperation,
    client_user: ApiUser,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        run(attach.run, UuidToIntRelatedPath(id=client_user.pk, related=987654))

    assert raised.value.field_errors == {
        "path.related": "No existe un registro con el valor '987654'.",
    }


########################################################################################


def test_detach_removes_link(
    detach: FlatLinkDetachOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    ApiUserGroups.objects.create(api_user=client_user, group=sample_group)

    assert (
        run(
            detach.run,
            UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk),
        )
        is None
    )
    assert not ApiUserGroups.objects.filter(
        api_user=client_user,
        group=sample_group,
    ).exists()


def test_detach_reports_absent_link(
    detach: FlatLinkDetachOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        run(
            detach.run,
            UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk),
        )

    assert set(raised.value.field_errors) == {"path.id", "path.related"}


def test_detach_reports_absent_parent(
    detach: FlatLinkDetachOperation,
    sample_group: Group,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        run(detach.run, UuidToIntRelatedPath(id=uuid7(), related=sample_group.pk))

    assert set(raised.value.field_errors) == {"path.id"}


########################################################################################


def test_inspect_returns_mapped_link(
    inspect: FlatLinkInspectOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    ApiUserGroups.objects.create(api_user=client_user, group=sample_group)

    found: ApiUserGroupsLinkGet = run(
        inspect.run,
        UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk),
    )

    assert found.api_user.id == client_user.pk
    assert found.api_user.username == client_user.username
    assert found.group.id == sample_group.pk
    assert found.group.name == sample_group.name


def test_inspect_reports_absent_link(
    inspect: FlatLinkInspectOperation,
    client_user: ApiUser,
    sample_group: Group,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        run(
            inspect.run,
            UuidToIntRelatedPath(id=client_user.pk, related=sample_group.pk),
        )

    assert set(raised.value.field_errors) == {"path.id", "path.related"}


def test_inspect_reports_absent_related(
    inspect: FlatLinkInspectOperation,
    client_user: ApiUser,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        run(inspect.run, UuidToIntRelatedPath(id=client_user.pk, related=987654))

    assert set(raised.value.field_errors) == {"path.related"}
