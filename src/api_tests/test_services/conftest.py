import pytest

from django.contrib.auth.models import Group
from django.db.models import QuerySet

from api_auth.controllers.user import ApiUserListController
from api_auth.models import ApiUser, ApiUserGroups, ApiUserPermissions
from api_auth.schemas.group import GroupGet
from api_auth.schemas.through import ApiUserGroupsLinkGet, ApiUserPermissionsLinkGet
from api_auth.schemas.user import ApiUserGet
from api_core.services.relations import RelationResolver

########################################################################################


@pytest.fixture
def group_qs(db: None) -> QuerySet:
    return RelationResolver.build(Group, GroupGet).build_qs()


@pytest.fixture
def plain_group_qs(db: None) -> QuerySet:
    return Group.objects.all()


@pytest.fixture
def user_groups_qs(db: None) -> QuerySet:
    return RelationResolver.build(ApiUserGroups, ApiUserGroupsLinkGet).build_qs()


@pytest.fixture
def user_permissions_qs(db: None) -> QuerySet:
    return RelationResolver.build(
        ApiUserPermissions,
        ApiUserPermissionsLinkGet,
    ).build_qs()


@pytest.fixture
def user_qs(db: None) -> QuerySet:
    return RelationResolver.build(ApiUser, ApiUserGet).build_qs()


########################################################################################


@pytest.fixture
def list_controller() -> ApiUserListController:
    return ApiUserListController()
