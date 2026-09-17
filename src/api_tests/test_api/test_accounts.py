from http import HTTPStatus
from uuid import uuid7

import pytest

from django.contrib.auth.models import Group, Permission
from dmr.test import DMRClient

from api_auth.enums import ApiUserTypes
from api_auth.models import ApiUser
from api_core.services.mappers import MAX_UNPAGINATED
from api_exceptions.errors import ForbiddenError, UnauthorizedError
from api_tests.conftest import PASSWORD
from api_tests.helpers import (
    PatchedHttpResponse,
    assert_detail,
    assert_field_error,
    listed_ids,
    paginated_ids,
    route,
)

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


def registration_body(**overrides: str) -> dict:
    return {
        "username": "registrado",
        "email": "registrado@pruebas.example.com",
        "first_name": "Nuevo",
        "last_name": "Usuario",
        "password1": PASSWORD,
        "password2": PASSWORD,
        "group": ApiUserTypes.CLIENT.value,
    } | overrides


########################################################################################


def test_register_is_public(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(),
    )

    assert response.status_code == HTTPStatus.CREATED

    payload: dict = response.json()

    assert payload["username"] == "registrado"
    assert payload["email"] == "registrado@pruebas.example.com"
    assert payload["is_active"] is True
    assert [group["name"] for group in payload["groups"]] == [
        ApiUserTypes.CLIENT.value,
    ]

    assert payload["permissions"] == []


def test_register_hashes_the_password(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    dmr_client.post(route("auth-register"), data=registration_body())

    created: ApiUser = ApiUser.objects.get(username="registrado")

    assert created.password != PASSWORD
    assert created.check_password(PASSWORD)


def test_register_never_echoes_the_password(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    payload: dict = dmr_client.post(
        route("auth-register"),
        data=registration_body(),
    ).json()

    assert "password" not in payload
    assert "password1" not in payload


def test_register_rejects_mismatched_passwords(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(password2="Otra-Contrasena-99"),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST

    assert (
        assert_field_error(response, "body.password1")
        == "Las contraseñas ingresadas no son iguales."
    )

    assert_field_error(response, "body.password2")


def test_register_rejects_weak_passwords(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(password1="12345678", password2="12345678"),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST

    message: str = assert_field_error(response, "body.password1")

    assert message.endswith(".")
    assert message[0].isupper()


def test_register_rejects_duplicate_usernames(
    dmr_client: DMRClient,
    client_user: ApiUser,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(username=client_user.username),  # ty: ignore[invalid-argument-type]
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert assert_field_error(response, "body.username")


def test_register_rejects_invalid_email(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(email="no-es-un-correo"),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.email") == "Debe ser un correo válido."


def test_register_accepts_an_empty_email(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(email=""),
    )

    assert response.status_code == HTTPStatus.CREATED

    assert response.json()["email"] == ""  # ruff: ignore[compare-to-empty-string]


def test_register_rejects_a_non_client_group(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-register"),
        data=registration_body(group=ApiUserTypes.ADMIN.value),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.group")


def test_register_normalizes_the_username(
    dmr_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    dmr_client.post(route("auth-register"), data=registration_body(username="  eco  "))

    assert ApiUser.objects.filter(username="eco").exists()


########################################################################################


def test_profile_returns_the_current_user(
    restricted_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = restricted_client.get(route("auth-profile"))

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["id"] == str(client_user.pk)
    assert payload["username"] == client_user.username
    assert [group["name"] for group in payload["groups"]] == [
        ApiUserTypes.CLIENT.value,
    ]


def test_profile_includes_direct_permissions(
    restricted_client: DMRClient,
    linked_user: ApiUser,
) -> None:
    payload: dict = restricted_client.get(route("auth-profile")).json()

    assert len(payload["permissions"]) == 3
    assert all(perm["action"] for perm in payload["permissions"])
    assert all(perm["model"] for perm in payload["permissions"])


def test_profile_requires_authentication(dmr_client: DMRClient, db: None) -> None:
    response: PatchedHttpResponse = dmr_client.get(route("auth-profile"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert_detail(response, UnauthorizedError.default_detail)


def test_profile_needs_no_model_permissions(restricted_client: DMRClient) -> None:
    assert restricted_client.get(route("auth-profile")).status_code == HTTPStatus.OK


def test_profile_rejects_a_malformed_token(dmr_client: DMRClient, db: None) -> None:
    dmr_client.defaults["HTTP_AUTHORIZATION"] = "Bearer no.es.un.jwt"

    assert dmr_client.get(route("auth-profile")).status_code == (
        HTTPStatus.UNAUTHORIZED
    )


########################################################################################


def test_user_list_paginates(
    admin_client: DMRClient,
    many_users: list[ApiUser],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"page": "1", "page_size": "2", "order": "username"},
    )

    assert response.status_code == HTTPStatus.OK

    payload: dict = response.json()

    assert payload["current"] == 1
    assert payload.get("page_size", True)
    assert payload["next"] is True
    assert payload["previous"] is False
    assert len(payload["results"]) == 2


def test_user_list_counts_every_row(
    admin_client: DMRClient,
    many_users: list[ApiUser],
) -> None:
    payload: dict = admin_client.get(route("auth-user-list")).json()

    assert payload["elements"] == ApiUser.objects.count()
    assert payload["pages"] >= 1


def test_user_list_filters_by_username(
    admin_client: DMRClient,
    many_users: list[ApiUser],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"username": "listado-2"},
    )

    assert [item["username"] for item in response.json()["results"]] == ["listado-2"]


def test_user_list_filters_by_group(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"group": ApiUserTypes.CLIENT.value},
    )

    assert paginated_ids(response) == [str(client_user.pk)]


def test_user_list_searches_across_fields(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"search": "client"},
    )

    assert str(client_user.pk) in paginated_ids(response)


def test_user_list_rejects_unknown_filters(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"inexistente": "x"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "query.inexistente")
        == "Este campo no es válido para esta acción."
    )


def test_user_list_rejects_repeated_filters(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.get(
        f"{route('auth-user-list')}?username=a&username=b",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "query.username")
        == "Este parámetro solo puede especificarse una vez."
    )


def test_user_list_caps_the_page_size(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"page_size": "101"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "query.page_size")
        == "Este campo debe ser menor, o igual, a 100."
    )


def test_user_list_rejects_a_missing_page(
    admin_client: DMRClient,
    many_users: list[ApiUser],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-list"),
        query_params={"page": "99"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "query.page")
        == "La página especificada no existe."
    )


def test_user_list_requires_permissions(restricted_client: DMRClient) -> None:
    response: PatchedHttpResponse = restricted_client.get(route("auth-user-list"))

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert_detail(response, ForbiddenError.default_detail)


def test_user_list_requires_authentication(dmr_client: DMRClient, db: None) -> None:
    assert dmr_client.get(route("auth-user-list")).status_code == (
        HTTPStatus.UNAUTHORIZED
    )


########################################################################################


def test_user_list_all_returns_a_flat_list(
    admin_client: DMRClient,
    many_users: list[ApiUser],
) -> None:
    response: PatchedHttpResponse = admin_client.get(route("auth-user-all"))

    assert response.status_code == HTTPStatus.OK

    payload = response.json()

    assert isinstance(payload, list)
    assert len(payload) == ApiUser.objects.count()
    assert "groups" not in payload[0]


def test_user_list_all_supports_filters(
    admin_client: DMRClient,
    many_users: list[ApiUser],
) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-all"),
        query_params={"username": "listado-0"},
    )

    assert len(listed_ids(response)) == 1


def test_user_list_all_has_no_pagination_params(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-all"),
        query_params={"page": "1"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "query.page")


def test_max_unpaginated_guard_is_documented() -> None:
    assert MAX_UNPAGINATED == 10_000


########################################################################################


def test_user_create_accepts_groups_and_permissions(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
    sample_permissions: list[Permission],
) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-user-list"),
        data={
            "username": "creado-por-admin",
            "email": "creado@pruebas.example.com",
            "first_name": "Creado",
            "last_name": "Admin",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "groups": [seeded_groups[ApiUserTypes.STAFF.value].pk],
            "permissions": [perm.pk for perm in sample_permissions],
        },
    )

    assert response.status_code == HTTPStatus.CREATED

    payload: dict = response.json()

    assert [group["name"] for group in payload["groups"]] == [
        ApiUserTypes.STAFF.value,
    ]

    assert len(payload["permissions"]) == 3


def test_user_create_without_relations(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-user-list"),
        data={
            "username": "minimo",
            "password1": PASSWORD,
            "password2": PASSWORD,
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["groups"] == []


def test_user_create_reports_unknown_relations(
    admin_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = admin_client.post(
        route("auth-user-list"),
        data={
            "username": "con-grupo-falso",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "groups": [987654],
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        assert_field_error(response, "body.groups.0")
        == "No existe un registro relacionado con el valor '987654'."
    )


def test_user_create_requires_permissions(
    restricted_client: DMRClient,
    seeded_groups: dict[str, Group],
) -> None:
    response: PatchedHttpResponse = restricted_client.post(
        route("auth-user-list"),
        data={
            "username": "prohibido",
            "password1": PASSWORD,
            "password2": PASSWORD,
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


########################################################################################


def test_user_retrieve(admin_client: DMRClient, client_user: ApiUser) -> None:
    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-detail", id=client_user.pk),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["id"] == str(client_user.pk)


def test_user_retrieve_reports_a_missing_row(admin_client: DMRClient) -> None:
    missing = uuid7()

    response: PatchedHttpResponse = admin_client.get(
        route("auth-user-detail", missing),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert (
        assert_field_error(response, "path.id")
        == f"No existe un registro con el valor '{missing}'."
    )


def test_user_retrieve_validates_the_path(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.get("/auth/user/no-es-uuid/")

    assert response.status_code == HTTPStatus.NOT_FOUND


########################################################################################


def test_user_update_replaces_every_field(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail", id=client_user.pk),
        data={
            "username": "renombrado",
            "email": "renombrado@pruebas.example.com",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "is_active": True,
        },
    )

    assert response.status_code == HTTPStatus.OK

    client_user.refresh_from_db()

    assert client_user.username == "renombrado"
    assert client_user.first_name == "Nombre"


def test_user_update_requires_every_field(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.put(
        route("auth-user-detail", id=client_user.pk),
        data={"first_name": "Solo"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert assert_field_error(response, "body.username") == "Este campo es requerido."


def test_user_patch_updates_a_single_field(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        route("auth-user-detail", id=client_user.pk),
        data={"first_name": "Parcial"},
    )

    assert response.status_code == HTTPStatus.OK

    client_user.refresh_from_db()

    assert client_user.first_name == "Parcial"
    assert client_user.username == "client"


def test_user_patch_with_an_empty_body(
    admin_client: DMRClient,
    client_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        route("auth-user-detail", id=client_user.pk),
        data={},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["username"] == client_user.username


def test_user_patch_reports_duplicate_usernames(
    admin_client: DMRClient,
    client_user: ApiUser,
    staff_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        route("auth-user-detail", id=client_user.pk),
        data={"username": staff_user.username},
    )

    assert response.status_code == HTTPStatus.CONFLICT


def test_user_patch_reports_a_missing_row(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.patch(
        route("auth-user-detail", uuid7()),
        data={"first_name": "Fantasma"},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


########################################################################################


def test_user_delete_soft_deletes(
    admin_client: DMRClient, client_user: ApiUser
) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-user-detail", id=client_user.pk),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT

    client_user.refresh_from_db()

    assert client_user.is_active is False


def test_user_delete_reports_a_missing_row(admin_client: DMRClient) -> None:
    response: PatchedHttpResponse = admin_client.delete(
        route("auth-user-detail", uuid7()),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_user_delete_requires_permissions(
    restricted_client: DMRClient,
    staff_user: ApiUser,
) -> None:
    response: PatchedHttpResponse = restricted_client.delete(
        route("auth-user-detail", id=staff_user.pk),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


########################################################################################


def test_superuser_bypasses_permission_checks(
    superuser_client: DMRClient,
    client_user: ApiUser,
) -> None:
    assert superuser_client.get(route("auth-user-list")).status_code == HTTPStatus.OK
    assert (
        superuser_client.get(
            route("auth-user-detail", id=client_user.pk),
        ).status_code
        == HTTPStatus.OK
    )


@pytest.mark.parametrize(
    "name",
    ["auth-user-list", "auth-user-all", "auth-group-list", "auth-permission-list"],
)
def test_protected_endpoints_reject_anonymous_requests(
    db: None,
    dmr_client: DMRClient,
    name: str,
) -> None:
    assert dmr_client.get(route(name)).status_code == HTTPStatus.UNAUTHORIZED
