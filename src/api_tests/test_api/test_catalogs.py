from http import HTTPStatus

import pytest

from django.contrib.auth.models import Group, Permission
from dmr.test import DMRClient

from api_auth.controllers.permission import (
    PermissionDetailController,
    PermissionListController,
)
from api_auth.enums import ApiUserTypes, PermissionTypes
from api_auth.models import ApiUser
from api_tests.helpers import (
    PatchedHttpResponse,
    assert_field_error,
    listed_ids,
    paginated_ids,
    route,
)

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


def test_group_list_paginates(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-group-list"),
        query_params={"page_size": "2", "order": "name"},
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["elements"] == Group.objects.count()
    assert len(payload["results"]) == 2
    assert payload["results"][0]["name"] == ApiUserTypes.ADMIN.value


def test_group_list_embeds_permissions(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-group-list"),
        query_params={"name": ApiUserTypes.ADMIN.value},
    )

    group: dict = response.json()["results"][0]

    assert len(group["permissions"]) == Permission.objects.count()
    assert set(group["permissions"][0]) == {"id", "action", "model"}


def test_group_list_filters_by_name(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-group-list"),
        query_params={"name": "cliente"},
    )

    assert [item["name"] for item in response.json()["results"]] == [
        ApiUserTypes.CLIENT.value,
    ]


def test_group_list_searches_without_accents(admin_client: DMRClient, db: None) -> None:
    Group.objects.create(name="Administración")

    response: PatchedHttpResponse = admin_client.get(
        route("auth-group-list"),
        query_params={"search": "administracion"},
    )

    assert [item["name"] for item in response.json()["results"]] == [
        "Administración",
    ]


def test_group_list_all_omits_pagination(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = admin_client.get(route("auth-group-all"))

    assert response.status_code == HTTPStatus.OK

    payload = response.json()

    assert isinstance(payload, list)
    assert len(payload) == Group.objects.count()
    assert set(payload[0]) == {"id", "name"}


########################################################################################


def test_group_create(
    admin_client: DMRClient,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-group-list"),
        data={
            "name": "grupo-nuevo",
            "permissions": [perm.pk for perm in sample_permissions],
        },
    )

    assert response.status_code == HTTPStatus.CREATED

    payload: dict = response.json()

    assert payload["name"] == "grupo-nuevo"
    assert len(payload["permissions"]) == 3
    assert Group.objects.filter(name="grupo-nuevo").exists()


def test_group_create_without_permissions(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-group-list"),
        data={"name": "grupo-vacio"},
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["permissions"] == []


def test_group_create_rejects_duplicates(
    admin_client: DMRClient,
    sample_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-group-list"),
        data={"name": sample_group.name},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        assert_field_error(response, "body.name")
        == "Ya existe un registro con el valor proporcionado."
    )


def test_group_create_rejects_an_empty_name(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-group-list"),
        data={"name": ""},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "body.name")
        == "Este campo debe tener un mínimo de 1 caracter(es)."
    )


def test_group_create_reports_unknown_permissions(
    admin_client: DMRClient,
    db: None,
) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-group-list"),
        data={"name": "grupo-roto", "permissions": [987654]},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.permissions.0")


########################################################################################


def test_group_retrieve(admin_client: DMRClient, sample_group: Group) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-group-detail", id=sample_group.pk),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["id"] == sample_group.pk


def test_group_retrieve_reports_a_missing_row(
    admin_client: DMRClient,
    db: None,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-group-detail", id=987654),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert (
        assert_field_error(response, "path.id")
        == "No existe un registro con el valor '987654'."
    )


########################################################################################


def test_group_update_overwrites_permissions_by_default(
    admin_client: DMRClient,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0], sample_permissions[1])  # ty: ignore[unresolved-attribute]

    response: PatchedHttpResponse = admin_client.put(
        route("auth-group-detail", id=sample_group.pk),
        data={
            "name": sample_group.name,
            "permissions": [sample_permissions[2].pk],
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert [perm["id"] for perm in response.json()["permissions"]] == [
        sample_permissions[2].pk,
    ]


def test_group_update_can_opt_out_of_overwriting(
    admin_client: DMRClient,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0])  # ty: ignore[unresolved-attribute]

    response: PatchedHttpResponse = admin_client.put(
        f"{route('auth-group-detail', id=sample_group.pk)}?overwrite=false",
        data={
            "name": sample_group.name,
            "permissions": [sample_permissions[1].pk],
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert len(response.json()["permissions"]) == 2


def test_group_patch_merges_permissions_by_default(
    admin_client: DMRClient,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(sample_permissions[0])  # ty: ignore[unresolved-attribute]

    response: PatchedHttpResponse = admin_client.patch(
        route("auth-group-detail", id=sample_group.pk),
        data={"permissions": [sample_permissions[1].pk]},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(response.json()["permissions"]) == 2


def test_group_patch_can_opt_into_overwriting(
    admin_client: DMRClient,
    sample_group: Group,
    sample_permissions: list[Permission],
) -> None:
    sample_group.permissions.add(*sample_permissions)  # ty: ignore[unresolved-attribute]

    response: PatchedHttpResponse = admin_client.patch(
        f"{route('auth-group-detail', id=sample_group.pk)}?overwrite=true",
        data={"permissions": []},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["permissions"] == []


def test_group_patch_renames(admin_client: DMRClient, sample_group: Group) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        route("auth-group-detail", id=sample_group.pk),
        data={"name": "grupo-renombrado"},
    )

    assert response.status_code == HTTPStatus.OK

    sample_group.refresh_from_db()

    assert sample_group.name == "grupo-renombrado"


def test_group_update_validates_the_overwrite_flag(
    admin_client: DMRClient,
    sample_group: Group,
) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        f"{route('auth-group-detail', id=sample_group.pk)}?overwrite=quizas",
        data={},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "query.overwrite")


########################################################################################


def test_group_delete(admin_client: DMRClient, sample_group: Group) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-group-detail", id=sample_group.pk),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not Group.objects.filter(pk=sample_group.pk).exists()


def test_group_delete_reports_a_missing_row(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-group-detail", id=987654),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_group_delete_detaches_members(
    admin_client: DMRClient,
    client_user: ApiUser,
    seeded_groups: dict[str, Group],
) -> None:
    group: Group = seeded_groups[ApiUserTypes.CLIENT.value]

    response: PatchedHttpResponse = admin_client.delete(
        route("auth-group-detail", id=group.pk),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert client_user.groups.count() == 0  # ty: ignore[unresolved-attribute]


########################################################################################


def test_permission_list_is_read_only() -> None:
    assert PermissionListController.post is None
    assert PermissionDetailController.put is None
    assert PermissionDetailController.patch is None
    assert PermissionDetailController.delete is None


def test_permission_list_paginates(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-permission-list"),
        query_params={"page_size": "5"},
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["elements"] == Permission.objects.count()
    assert len(payload["results"]) == 5


def test_permission_shape_splits_the_codename(
    admin_client: DMRClient,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-permission-detail", id=sample_permissions[0].pk),
    )

    payload: dict = response.json()

    assert set(payload) == {"id", "action", "model"}
    assert payload["action"] == sample_permissions[0].codename.split("_")[0]  # ty: ignore[unresolved-attribute]
    assert payload["model"] == sample_permissions[0].content_type.model


def test_permission_list_filters_by_action(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-permission-list"),
        query_params={"action": PermissionTypes.VIEW.value, "page_size": "100"},
    )

    assert all(
        item["action"] == PermissionTypes.VIEW.value
        for item in response.json()["results"]
    )


def test_permission_list_filters_by_model(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-permission-list"),
        query_params={"model": "apiuser", "page_size": "100"},
    )

    assert all("apiuser" in item["model"] for item in response.json()["results"])


def test_permission_list_rejects_an_unknown_action(
    admin_client: DMRClient,
    db: None,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-permission-list"),
        query_params={"action": "inventar"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "query.action")


def test_permission_list_all(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.get(route("auth-permission-all"))

    assert response.status_code == HTTPStatus.OK
    assert len(listed_ids(response)) == Permission.objects.count()


def test_permission_create_is_not_allowed(admin_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-permission-list"),
        data={"codename": "inventado"},
    )

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["Allow"] == "GET"


def test_permission_delete_is_not_allowed(
    admin_client: DMRClient,
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-permission-detail", id=sample_permissions[0].pk),
    )

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


########################################################################################


@pytest.mark.parametrize(
    "name",
    ["auth-group-list", "auth-group-all", "auth-permission-list"],
)
def test_catalog_requires_permissions(restricted_client: DMRClient, name: str) -> None:
    response: PatchedHttpResponse = restricted_client.get(route(name))

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_catalog_ordering_is_deterministic(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    first: PatchedHttpResponse = admin_client.get(route("auth-group-list"))
    second: PatchedHttpResponse = admin_client.get(route("auth-group-list"))

    assert paginated_ids(first) == paginated_ids(second)
