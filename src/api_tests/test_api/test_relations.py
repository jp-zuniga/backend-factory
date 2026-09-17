from http import HTTPStatus
from uuid import uuid7

import pytest

from django.contrib.auth.models import Group, Permission
from dmr.test import DMRClient

from api_auth.controllers.user import (
    ApiUserGroupsController,
    ApiUserPermissionsController,
)
from api_auth.enums import ApiUserTypes
from api_auth.models import ApiUser, ApiUserGroups, ApiUserPermissions
from api_tests.helpers import PatchedHttpResponse, assert_field_error, route

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


def test_relation_controllers_drop_delete() -> None:
    assert ApiUserGroupsController.delete is None
    assert ApiUserPermissionsController.delete is None


########################################################################################


def test_user_groups_relation_retrieve(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-detail-groups", id=client_user.pk),
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert set(payload) == {"id", "groups"}
    assert [group["name"] for group in payload["groups"]] == [
        ApiUserTypes.CLIENT.value,
    ]


def test_user_groups_relation_replaces_on_put(
    admin_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail-groups", id=client_user.pk),
        data={"groups": [staff_group.pk]},
    )

    assert response.status_code == HTTPStatus.OK
    assert [group["name"] for group in response.json()["groups"]] == [
        ApiUserTypes.STAFF.value,
    ]
    assert client_user.groups.count() == 1  # ty: ignore[unresolved-attribute]


def test_user_groups_relation_merges_on_patch(
    admin_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        route("auth-user-detail-groups", id=client_user.pk),
        data={"groups": [staff_group.pk]},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(response.json()["groups"]) == 2


def test_user_groups_relation_clears_with_an_empty_list(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail-groups", id=client_user.pk),
        data={"groups": []},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["groups"] == []
    assert client_user.groups.count() == 0  # ty: ignore[unresolved-attribute]


def test_user_groups_relation_reports_unknown_groups(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail-groups", id=client_user.pk),
        data={"groups": [987654]},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "body.groups.0")
        == "No existe un registro relacionado con el valor '987654'."
    )


def test_user_groups_relation_reports_a_missing_user(
    admin_client: DMRClient, db: None
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail-groups", id=uuid7()),
        data={"groups": []},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert_field_error(response, "path.id")


def test_user_groups_relation_rejects_delete(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-user-detail-groups", id=client_user.pk),
    )

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert "GET" in response.headers["Allow"]


########################################################################################


def test_user_permissions_relation_retrieve(
    admin_client: DMRClient,
    linked_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-detail-permissions", id=linked_user.pk),
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert set(payload) == {"id", "permissions"}
    assert len(payload["permissions"]) == 3


def test_user_permissions_relation_replaces_on_put(
    admin_client: DMRClient,
    linked_user: ApiUser,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail-permissions", id=linked_user.pk),
        data={"permissions": [sample_permissions[0].pk]},
    )

    assert response.status_code == HTTPStatus.OK
    assert [perm["id"] for perm in response.json()["permissions"]] == [
        sample_permissions[0].pk,
    ]


def test_user_permissions_relation_requires_permissions(
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = restricted_client.get(
        route("auth-user-detail-permissions", id=client_user.pk),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


########################################################################################


def test_groups_link_inspect(
    admin_client: DMRClient,
    client_user: ApiUser,
    client_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-groups-link", id=client_user.pk, related=client_group.pk),
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["api_user"]["id"] == str(client_user.pk)
    assert payload["group"]["id"] == client_group.pk
    assert payload["group"]["name"] == ApiUserTypes.CLIENT.value


def test_groups_link_inspect_reports_a_missing_link(
    admin_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-groups-link", id=client_user.pk, related=staff_group.pk),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert set(response.json()["field_errors"]) == {"path.id", "path.related"}


def test_groups_link_inspect_reports_a_missing_group(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-groups-link", id=client_user.pk, related=987654),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert set(response.json()["field_errors"]) == {"path.related"}


########################################################################################


def test_groups_link_attach(
    superuser_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    response: PatchedHttpResponse = superuser_client.put(
        route("auth-user-groups-link", id=client_user.pk, related=staff_group.pk),
        data={},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert ApiUserGroups.objects.filter(
        api_user=client_user,
        group=staff_group,
    ).exists()


def test_groups_link_attach_is_idempotent(
    superuser_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    target: str = route(
        "auth-user-groups-link",
        id=client_user.pk,
        related=staff_group.pk,
    )

    superuser_client.put(target, data={})

    assert superuser_client.put(target, data={}).status_code == HTTPStatus.NO_CONTENT
    assert (
        ApiUserGroups.objects.filter(
            api_user=client_user,
            group=staff_group,
        ).count()
        == 1
    )


def test_groups_link_attach_reports_a_missing_user(
    superuser_client: DMRClient,
    staff_group: Group,
    db: None,
) -> None:
    response: PatchedHttpResponse = superuser_client.put(
        route("auth-user-groups-link", id=uuid7(), related=staff_group.pk),
        data={},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert set(response.json()["field_errors"]) == {"path.id"}


def test_groups_link_attach_reports_a_missing_group(
    superuser_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = superuser_client.put(
        route("auth-user-groups-link", id=client_user.pk, related=987654),
        data={},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert set(response.json()["field_errors"]) == {"path.related"}


########################################################################################


def test_groups_link_detach(
    admin_client: DMRClient,
    client_user: ApiUser,
    client_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-user-groups-link", id=client_user.pk, related=client_group.pk),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not ApiUserGroups.objects.filter(api_user=client_user).exists()


def test_groups_link_detach_reports_a_missing_link(
    admin_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-user-groups-link", id=client_user.pk, related=staff_group.pk),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


########################################################################################


def test_permissions_link_attach(
    superuser_client: DMRClient,
    client_user: ApiUser,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = superuser_client.put(
        route(
            "auth-user-permissions-link",
            id=client_user.pk,
            related=sample_permissions[0].pk,
        ),
        data={},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert ApiUserPermissions.objects.filter(
        api_user=client_user,
        permission=sample_permissions[0],
    ).exists()


def test_permissions_link_inspect(
    superuser_client: DMRClient,
    linked_user: ApiUser,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = superuser_client.get(
        route(
            "auth-user-permissions-link",
            id=linked_user.pk,
            related=sample_permissions[0].pk,
        ),
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["api_user"]["id"] == str(linked_user.pk)
    assert payload["permission"]["id"] == sample_permissions[0].pk
    assert set(payload["permission"]) == {"id", "action", "model"}


def test_permissions_link_detach(
    superuser_client: DMRClient,
    linked_user: ApiUser,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = superuser_client.delete(
        route(
            "auth-user-permissions-link",
            id=linked_user.pk,
            related=sample_permissions[0].pk,
        ),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert linked_user.permissions.count() == 2  # ty: ignore[unresolved-attribute]


########################################################################################


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_link_endpoints_require_authentication(
    dmr_client: DMRClient,
    client_user: ApiUser,
    client_group: Group,
    method: str,
) -> None:
    target: str = route(
        "auth-user-groups-link",
        id=client_user.pk,
        related=client_group.pk,
    )

    call = getattr(dmr_client, method)

    response: PatchedHttpResponse = (
        call(target) if method == "get" else call(target, data={})
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_link_attach_permission_template_is_formattable(
    admin_client: DMRClient,
    client_user: ApiUser,
    staff_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-groups-link", id=client_user.pk, related=staff_group.pk),
        data={},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
