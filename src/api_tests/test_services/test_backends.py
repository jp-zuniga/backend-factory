import pytest

from dmr.test import DMRRequestFactory

from api_auth.backends import ApiUserBackend
from api_auth.models import ApiUser
from api_tests.conftest import PASSWORD

########################################################################################

pytestmark = pytest.mark.django_db

########################################################################################


@pytest.fixture
def backend() -> ApiUserBackend:
    return ApiUserBackend()


########################################################################################


def test_authenticate_accepts_valid_credentials(
    backend: ApiUserBackend,
    dmr_rf: DMRRequestFactory,
    client_user: ApiUser,
) -> None:
    found = backend.authenticate(
        dmr_rf.get("/"),
        username=client_user.username,
        password=PASSWORD,
    )

    assert found == client_user


def test_authenticate_rejects_a_bad_password(
    backend: ApiUserBackend,
    dmr_rf: DMRRequestFactory,
    client_user: ApiUser,
) -> None:
    found = backend.authenticate(
        dmr_rf.get("/"),
        username=client_user.username,
        password="NO!!!",
    )

    assert found is None


def test_authenticate_rejects_an_unknown_username(
    backend: ApiUserBackend,
    dmr_rf: DMRRequestFactory,
    db: None,
) -> None:
    found = backend.authenticate(
        dmr_rf.get("/"),
        username="nadie",
        password=PASSWORD,
    )

    assert found is None


def test_authenticate_rejects_an_inactive_user(
    backend: ApiUserBackend,
    dmr_rf: DMRRequestFactory,
    inactive_user: ApiUser,
) -> None:
    found = backend.authenticate(
        dmr_rf.get("/"),
        username=inactive_user.username,
        password=PASSWORD,
    )

    assert found is None


def test_authenticate_requires_a_username(
    backend: ApiUserBackend,
    dmr_rf: DMRRequestFactory,
    db: None,
) -> None:
    assert backend.authenticate(dmr_rf.get("/"), password=PASSWORD) is None


def test_authenticate_requires_a_password(
    backend: ApiUserBackend,
    dmr_rf: DMRRequestFactory,
    client_user: ApiUser,
) -> None:
    found = backend.authenticate(dmr_rf.get("/"), username=client_user.username)

    assert found is None


def test_get_user_permissions_reads_off_the_relation(
    backend: ApiUserBackend,
    client_user: ApiUser,
    sample_permissions: list,
) -> None:
    client_user.permissions.add(*sample_permissions)  # ty: ignore[unresolved-attribute]

    perms = backend._get_user_permissions(client_user)  # ruff: ignore[private-member-access]

    assert perms.count() == len(sample_permissions)
