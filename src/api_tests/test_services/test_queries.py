from datetime import timedelta
from http import HTTPStatus

import pytest

from django.contrib.auth.models import Group
from django.db.models import QuerySet
from django.db.transaction import atomic
from django.db.utils import OperationalError
from psycopg.errors import LockNotAvailable, QueryCanceled

from api_auth.enums import ApiUserTypes
from api_auth.filtersets.group import GroupFilterSet
from api_auth.filtersets.user import ApiUserFilterSet
from api_auth.models import ApiUser
from api_core.services.filtersets import apply_filterset
from api_core.services.locks import LOCK_TIMEOUT, RETRIES, guarded_lock, lock_instance
from api_exceptions.enums import BadRequestErrorTypes, ConflictErrorTypes
from api_exceptions.errors import BadRequestError, ConflictError, NotFoundError
from api_tests.conftest import PASSWORD
from api_tests.factories import build_users
from api_tests.sync import run

pytestmark = pytest.mark.django_db

########################################################################################


def test_apply_filterset_without_filters(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(2, prefix="filtrado")

    filtered = run(
        apply_filterset,
        data={},
        filterset=ApiUserFilterSet,
        qs=user_qs,
    )

    assert filtered.count() == 2


def test_apply_filterset_narrows_by_field(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(3, prefix="filtrado")

    filtered = run(
        apply_filterset,
        data={"username": "filtrado-1"},
        filterset=ApiUserFilterSet,
        qs=user_qs,
    )

    assert [user.username for user in filtered] == ["filtrado-1"]


def test_apply_filterset_uses_unaccented_search(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    ApiUser.objects.create_user(
        username="jose-perez",
        first_name="José",
        last_name="Pérez",
        password=PASSWORD,
    )

    filtered = run(
        apply_filterset,
        data={"search": "jose perez"},
        filterset=ApiUserFilterSet,
        qs=user_qs,
    )

    assert filtered.count() == 0

    by_name = run(
        apply_filterset,
        data={"search": "perez"},
        filterset=ApiUserFilterSet,
        qs=user_qs,
    )

    assert by_name.count() == 1


def test_apply_filterset_filters_by_group(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    user: ApiUser = ApiUser.objects.create_user(
        username="con-grupo",
        password=PASSWORD,
    )

    user.groups.add(seeded_groups[ApiUserTypes.STAFF.value])  # ty: ignore[unresolved-attribute]

    filtered = run(
        apply_filterset,
        data={"group": ApiUserTypes.STAFF.value},
        filterset=ApiUserFilterSet,
        qs=user_qs,
    )

    assert [found.username for found in filtered] == ["con-grupo"]


def test_apply_filterset_applies_ordering(
    user_qs: QuerySet,
    seeded_groups: dict[str, Group],
) -> None:
    build_users(3, prefix="orden")

    filtered = run(
        apply_filterset,
        data={"order": "-username"},
        filterset=ApiUserFilterSet,
        qs=user_qs.filter(username__startswith="orden"),
    )

    assert [user.username for user in filtered] == [
        "orden-2",
        "orden-1",
        "orden-0",
    ]


def test_apply_filterset_rejects_invalid_uuid(user_qs: QuerySet) -> None:
    with pytest.raises(BadRequestError) as raised:
        run(
            apply_filterset,
            data={"id": "no-es-un-uuid"},
            filterset=ApiUserFilterSet,
            qs=user_qs,
        )

    assert raised.value.default_http_status == HTTPStatus.BAD_REQUEST
    assert raised.value.detail == BadRequestErrorTypes.FAILED_VALIDATION.value
    assert "query.id" in raised.value.field_errors


def test_apply_filterset_rejects_unknown_ordering(user_qs: QuerySet) -> None:
    with pytest.raises(BadRequestError) as raised:
        run(
            apply_filterset,
            data={"order": "campo_inexistente"},
            filterset=ApiUserFilterSet,
            qs=user_qs,
        )

    assert "query.order" in raised.value.field_errors


def test_apply_filterset_normalizes_error_messages(user_qs: QuerySet) -> None:
    with pytest.raises(BadRequestError) as raised:
        run(
            apply_filterset,
            data={"group_id": "no-es-numero"},
            filterset=ApiUserFilterSet,
            qs=user_qs,
        )

    message: str = raised.value.field_errors["query.group_id"]

    assert message.endswith(".")
    assert message[0].isupper()
    assert ";" not in message.removesuffix(".")


def test_apply_filterset_ignores_unknown_keys(plain_group_qs: QuerySet) -> None:
    Group.objects.create(name="grupo-filtrado")

    filtered = run(
        apply_filterset,
        data={"clave_desconocida": "x"},
        filterset=GroupFilterSet,
        qs=plain_group_qs,
    )

    assert filtered.count() == Group.objects.count()


########################################################################################


def test_lock_constants() -> None:
    assert timedelta(seconds=5) == LOCK_TIMEOUT
    assert RETRIES == 3


def test_guarded_lock_yields_control(db: None) -> None:
    entered: list[bool] = []

    with guarded_lock():
        entered.append(True)

    assert entered == [True]


def test_guarded_lock_maps_lock_not_available(db: None) -> None:
    with pytest.raises(ConflictError) as raised, guarded_lock():
        raise OperationalError from LockNotAvailable

    assert raised.value.default_http_status == HTTPStatus.CONFLICT
    assert raised.value.detail == ConflictErrorTypes.LOCKED.value


def test_guarded_lock_reraises_other_operational_errors(db: None) -> None:
    with pytest.raises(OperationalError), guarded_lock():
        raise OperationalError from QueryCanceled


def test_guarded_lock_reraises_unrelated_exceptions(db: None) -> None:
    with pytest.raises(ValueError), guarded_lock():  # ruff: ignore[pytest-raises-too-broad]
        raise ValueError


########################################################################################


def test_lock_instance_returns_row(sample_group: Group) -> None:
    with atomic():
        locked = lock_instance(lookup={"id": sample_group.pk}, model=Group)

        assert locked.pk == sample_group.pk


def test_lock_instance_raises_not_found(db: None) -> None:
    with atomic(), pytest.raises(NotFoundError) as raised:
        lock_instance(lookup={"id": 987654}, model=Group)

    assert raised.value.default_http_status == HTTPStatus.NOT_FOUND
    assert raised.value.field_errors == {
        "path.id": "No existe un registro con el valor '987654'.",
    }


def test_lock_instance_supports_composite_lookups(sample_group: Group) -> None:
    with atomic():
        locked = lock_instance(
            lookup={"id": sample_group.pk, "name": sample_group.name},
            model=Group,
        )

        assert locked.name == sample_group.name  # ty: ignore[unresolved-attribute]


def test_lock_instance_scopes_every_lookup_key(db: None) -> None:
    with atomic(), pytest.raises(NotFoundError) as raised:
        lock_instance(lookup={"id": 987654, "name": "ausente"}, model=Group)

    assert set(raised.value.field_errors) == {"path.id", "path.name"}
