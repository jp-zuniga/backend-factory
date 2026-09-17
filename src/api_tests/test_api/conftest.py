from http import HTTPStatus

import pytest

from django.contrib.auth.models import Group, Permission
from dmr.test import DMRClient

from api_auth.enums import ApiUserTypes
from api_auth.models import ApiUser
from api_tests.conftest import PASSWORD
from api_tests.factories import build_users
from api_tests.helpers import PatchedHttpResponse, route

########################################################################################


@pytest.fixture
def linked_user(client_user: ApiUser, sample_permissions: list[Permission]) -> ApiUser:
    client_user.permissions.add(*sample_permissions)  # ty: ignore[unresolved-attribute]

    return client_user


@pytest.fixture
def many_users(seeded_groups: dict[str, Group]) -> list[ApiUser]:
    return build_users(5, prefix="listado")


@pytest.fixture
def other_group(seeded_groups: dict[str, Group]) -> Group:
    return Group.objects.create(name="other-group")


########################################################################################


@pytest.fixture
def admin_web_client(dmr_client: DMRClient, admin_user: ApiUser) -> DMRClient:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-web-login"),
        data={"username": admin_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.OK, response.content

    return dmr_client


@pytest.fixture
def web_client(dmr_client: DMRClient, client_user: ApiUser) -> DMRClient:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-web-login"),
        data={"username": client_user.username, "password": PASSWORD},
    )

    assert response.status_code == HTTPStatus.OK, response.content

    return dmr_client


########################################################################################


@pytest.fixture
def client_group(seeded_groups: dict[str, Group]) -> Group:
    return seeded_groups[ApiUserTypes.CLIENT.value]


@pytest.fixture
def staff_group(seeded_groups: dict[str, Group]) -> Group:
    return seeded_groups[ApiUserTypes.STAFF.value]
