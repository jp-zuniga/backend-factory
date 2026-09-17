from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, PositiveInt, StringConstraints

from api_auth.enums import ApiUserTypes
from api_auth.filtersets.user import ApiUserFilterSet
from api_auth.models import ApiUser
from api_core.schemas.factories import (
    build_filter_query,
    build_patch_schema,
    build_put_schema,
)
from api_core.schemas.filters import PaginatedFilterQuery, UnpaginatedFilterQuery
from api_core.schemas.get import DTO, BaseGet

from .group import GroupInlineGet
from .permission import PermissionGet
from .types import Email, Password, Username

########################################################################################

type ApiClientGroups = Literal[ApiUserTypes.CLIENT]

type ApiUserPost = ApiClientPost | ApiStaffPost

########################################################################################


class ApiUserInlineGet(BaseGet):
    is_active: bool
    first_name: str
    last_name: str
    username: str
    email: str
    email_verified_at: datetime | None


########################################################################################


class ApiUserGroupsGet(BaseGet):
    groups: tuple[GroupInlineGet, ...]


########################################################################################


class ApiUserPermissionsGet(BaseGet):
    permissions: tuple[PermissionGet, ...]


########################################################################################


class ApiUserGet(ApiUserGroupsGet, ApiUserPermissionsGet, ApiUserInlineGet):
    pass


########################################################################################


class ApiUserBaseWrite(DTO):
    first_name: Annotated[str, StringConstraints(max_length=100)] = ""
    last_name: Annotated[str, StringConstraints(max_length=100)] = ""
    email: Email
    username: Annotated[Username, AfterValidator(func=ApiUser.normalize_username)]


########################################################################################


class ApiUserBasePost(ApiUserBaseWrite):
    password1: Password
    password2: Password


########################################################################################


class ApiUserWrite(ApiUserBaseWrite):
    is_active: bool = True


########################################################################################


class ApiUserGroupsWrite(DTO):
    groups: list[PositiveInt] | None = None


########################################################################################


class ApiUserPermissionsWrite(DTO):
    permissions: list[PositiveInt] | None = None


########################################################################################


class ApiClientPost(ApiUserBasePost):
    group: ApiClientGroups


########################################################################################


class ApiStaffPost(ApiUserBasePost, ApiUserGroupsWrite, ApiUserPermissionsWrite):
    pass


########################################################################################

ApiUserPut = build_put_schema(ApiUserWrite)
ApiUserPatch = build_patch_schema(ApiUserPut)

ApiUserGroupsPut = build_put_schema(ApiUserGroupsWrite)
ApiUserGroupsPatch = build_patch_schema(ApiUserGroupsPut)

ApiUserPermissionsPut = build_put_schema(ApiUserPermissionsWrite)
ApiUserPermissionsPatch = build_patch_schema(ApiUserPermissionsPut)

########################################################################################

ApiUserFilterQuery = build_filter_query(PaginatedFilterQuery, ApiUserFilterSet)
ApiUserFilterAllQuery = build_filter_query(UnpaginatedFilterQuery, ApiUserFilterSet)
