from collections.abc import Generator, Sequence
from json import loads
from typing import Final
from uuid import uuid4

import hypothesis as ht
import pytest

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import BaseCache, cache
from django.core.cache.backends.dummy import DummyCache
from django.core.cache.backends.locmem import LocMemCache
from django.db import connection
from django.test.utils import override_settings
from django.utils.timezone import now
from dmr.openapi.dump import json_dumps
from dmr.settings import Settings as DmrSettings
from dmr.test import DMRClient
from dmr.throttling import AsyncThrottle
from pgtrigger.registry import registered
from pytest_django import (
    DjangoDbBlocker,
    Settings as PytestDjangoSettings,
)

from api_auth.enums import ApiUserTypes, TokenTypes
from api_auth.models import ApiUser
from api_auth.services.jwt import EncodedJwtPair, build_jwt_pair
from api_core.api import schema
from api_core.controllers.base import BaseController
from api_core.controllers.mixins import StrictThrottlingMixin

########################################################################################

DUMMY_CACHE: Final[dict] = {
    "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}

LOCMEM_CACHE: Final[dict] = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "api-tests",
    },
}

PASSWORD: Final[str] = "TEST-PASSWORD-123!"

TRUNCATE_TRIGGER: Final[str] = "trg_protect_truncate"

########################################################################################

# throttles capture `caches["default"]` when they are built, at import time,
# so overriding `settings.CACHES` never reaches them: every test would share
# one live redis. these are the instances the whole API throttles through
THROTTLES: Final[Sequence[AsyncThrottle]] = (
    *BaseController.throttling,
    *StrictThrottlingMixin.throttling,
)

########################################################################################


def swap_throttle_cache(backend: BaseCache) -> None:
    for throttle in THROTTLES:
        object.__setattr__(  # ruff: ignore[unnecessary-dunder-call]
            throttle._backend,  # ruff: ignore[private-member-access]
            "_cache",
            backend,
        )


########################################################################################

ht.settings.register_profile(
    "api",
    deadline=None,
    max_examples=50,
    suppress_health_check=(
        ht.HealthCheck.function_scoped_fixture,
        ht.HealthCheck.too_slow,
    ),
)

ht.settings.register_profile(
    "ci",
    deadline=None,
    max_examples=200,
    suppress_health_check=(
        ht.HealthCheck.function_scoped_fixture,
        ht.HealthCheck.too_slow,
    ),
)

ht.settings.load_profile("api")

########################################################################################


@pytest.fixture(scope="session")
def django_db_modify_db_settings(
    django_db_modify_db_settings_parallel_suffix: None,
) -> None:
    """
    Disable psycopg's connection pool for the test database.
    """

    settings.DATABASES["default"]["OPTIONS"]["pool"] = False


@pytest.fixture(autouse=True, scope="session")
def fast_password_hashing() -> Generator[None]:
    override = override_settings(
        PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",),
    )

    override.enable()

    yield

    override.disable()


@pytest.fixture(autouse=True, scope="session")
def allow_test_teardown(
    django_db_setup: None,
    django_db_blocker: DjangoDbBlocker,
) -> Generator[None]:
    """
    Manually disable triggers that prevent TRUNCATE statements.
    """

    triggers: Sequence[tuple[str, str]] = tuple(
        (model._meta.db_table, trigger.get_pgid(model))  # ruff: ignore[private-member-access]  # ty: ignore[unresolved-attribute]
        for model, trigger in registered()
        if trigger.name == TRUNCATE_TRIGGER
    )

    with django_db_blocker.unblock(), connection.cursor() as cursor:
        for table, pgid in triggers:
            cursor.execute(f'ALTER TABLE "{table}" DISABLE TRIGGER "{pgid}";')

    yield

    with django_db_blocker.unblock(), connection.cursor() as cursor:
        for table, pgid in triggers:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE TRIGGER "{pgid}";')


@pytest.fixture(autouse=True)
def disable_throttling(settings: PytestDjangoSettings) -> Generator[None]:
    settings.CACHES = DUMMY_CACHE
    settings.DMR_SETTINGS[DmrSettings.throttling_allow_unsafe_cache] = None

    swap_throttle_cache(DummyCache(host="throttling", params={}))

    yield

    swap_throttle_cache(cache)  # ty: ignore[invalid-argument-type]


@pytest.fixture(autouse=True)
def relaxed_cookies(settings: PytestDjangoSettings) -> None:
    settings.CSRF_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SAMESITE = "Lax"
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture
def local_cache(settings: PytestDjangoSettings) -> Generator[None]:
    settings.CACHES = LOCMEM_CACHE

    cache.clear()

    yield

    cache.clear()


@pytest.fixture
def live_throttling(local_cache: None) -> Generator[None]:
    """
    Let throttles count against a cache no other test can reach.
    """

    swap_throttle_cache(LocMemCache(name=f"throttling-{uuid4().hex}", params={}))

    yield

    swap_throttle_cache(DummyCache(host="throttling", params={}))


########################################################################################


@pytest.fixture
def content_type(db: None) -> ContentType:
    created: ContentType = ContentType.objects.create(
        app_label="TEST!",
        model="MODEL!",
    )

    ContentType.objects.clear_cache()

    return created


@pytest.fixture
def sample_group(db: None) -> Group:
    return Group.objects.create(name="group")


@pytest.fixture
def seeded_groups(db: None) -> dict[str, Group]:
    groups: dict[str, Group] = {
        value: Group.objects.get_or_create(name=value)[0]
        for value in ApiUserTypes.values
    }

    groups[ApiUserTypes.ADMIN.value].permissions.add(*Permission.objects.all())  # ty: ignore[unresolved-attribute]

    return groups


@pytest.fixture
def sample_permissions(db: None) -> list[Permission]:
    return list(Permission.objects.order_by("pk")[:3])


########################################################################################


def create_user(*, group: Group | None = None, **fields: bool | str) -> ApiUser:
    user: ApiUser = ApiUser.objects.create_user(
        password=PASSWORD,
        **fields,
    )

    ApiUser.objects.filter(pk=user.pk).update(email_verified_at=now())

    user.refresh_from_db()

    if group is not None:
        user.groups.add(group)  # ty: ignore[unresolved-attribute]

    return user


@pytest.fixture
def admin_user(seeded_groups: dict[str, Group]) -> ApiUser:
    return create_user(
        email="admin@unit.example.com",
        group=seeded_groups[ApiUserTypes.ADMIN.value],
        username="admin",
    )


@pytest.fixture
def client_user(seeded_groups: dict[str, Group]) -> ApiUser:
    return create_user(
        email="client@unit.example.com",
        group=seeded_groups[ApiUserTypes.CLIENT.value],
        username="client",
    )


@pytest.fixture
def inactive_user(db: None) -> ApiUser:
    return create_user(is_active=False, username="inactive")


@pytest.fixture
def staff_user(seeded_groups: dict[str, Group]) -> ApiUser:
    return create_user(
        email="staff@unit.example.com",
        group=seeded_groups[ApiUserTypes.STAFF.value],
        username="staff",
    )


@pytest.fixture
def unverified_user(seeded_groups: dict[str, Group]) -> ApiUser:
    user: ApiUser = ApiUser.objects.create_user(
        email="unverified@unit.example.com",
        password=PASSWORD,
        username="unverified",
    )

    user.groups.add(seeded_groups[ApiUserTypes.CLIENT.value])  # ty: ignore[unresolved-attribute]

    return user


@pytest.fixture
def superuser(db: None) -> ApiUser:
    return ApiUser.objects.create_superuser(
        username="sudo",
        email="sudo@unit.example.com",
        password=PASSWORD,
    )


########################################################################################


@pytest.fixture
def admin_tokens(admin_user: ApiUser) -> EncodedJwtPair:
    return build_jwt_pair(admin_user)


@pytest.fixture
def client_tokens(client_user: ApiUser) -> EncodedJwtPair:
    return build_jwt_pair(client_user)


@pytest.fixture
def superuser_tokens(superuser: ApiUser) -> EncodedJwtPair:
    return build_jwt_pair(superuser)


########################################################################################


@pytest.fixture
def admin_client(dmr_client: DMRClient, admin_tokens: EncodedJwtPair) -> DMRClient:
    dmr_client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {admin_tokens.access}"

    return dmr_client


@pytest.fixture
def cookie_client(
    dmr_client: DMRClient,
    superuser_tokens: EncodedJwtPair,
) -> DMRClient:
    dmr_client.cookies[TokenTypes.ACCESS] = superuser_tokens.access
    dmr_client.cookies[TokenTypes.REFRESH] = superuser_tokens.refresh

    return dmr_client


@pytest.fixture
def csrf_client() -> DMRClient:
    return DMRClient(enforce_csrf_checks=True)


@pytest.fixture
def restricted_client(
    dmr_client: DMRClient,
    client_tokens: EncodedJwtPair,
) -> DMRClient:
    dmr_client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {client_tokens.access}"

    return dmr_client


@pytest.fixture
def superuser_client(
    dmr_client: DMRClient,
    superuser_tokens: EncodedJwtPair,
) -> DMRClient:
    dmr_client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {superuser_tokens.access}"

    return dmr_client


########################################################################################


@pytest.fixture(scope="session")
def openapi_document() -> dict:
    return loads(json_dumps(schema.convert(skip_validation=True)))


@pytest.fixture(scope="session")
def tracecov_schema(openapi_document: dict) -> dict:
    return openapi_document
