from collections.abc import Sequence
from http import HTTPMethod
from typing import ClassVar

from api_auth.models import ApiUser
from api_auth.models.through import ApiUserGroups, ApiUserPermissions
from api_auth.services.permissions import (
    DEFAULT_PERMISSIONS,
    T_ADD_PERM,
    T_CHANGE_PERM,
    T_DELETE_PERM,
    T_VIEW_PERM,
)
from api_utils.db import model_permission

########################################################################################


class ApiUserRelationsMixin:
    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = DEFAULT_PERMISSIONS | {
        HTTPMethod.GET: (
            T_VIEW_PERM,
            model_permission("view", ApiUserGroups),
            model_permission("view", ApiUserPermissions),
        ),
        HTTPMethod.POST: (
            T_ADD_PERM,
            model_permission("add", ApiUserGroups),
            model_permission("add", ApiUserPermissions),
        ),
    }


########################################################################################


class ApiUserGroupsMixin:
    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = {
        HTTPMethod.GET: (T_VIEW_PERM, model_permission("view", ApiUserGroups)),
        HTTPMethod.PATCH: (T_CHANGE_PERM, model_permission("change", ApiUserGroups)),
        HTTPMethod.PUT: (T_CHANGE_PERM, model_permission("change", ApiUserGroups)),
    }


########################################################################################


class ApiUserGroupsLinkMixin:
    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = {
        HTTPMethod.GET: (T_VIEW_PERM, model_permission("view", ApiUser)),
        HTTPMethod.PUT: (
            T_ADD_PERM,
            model_permission("view", ApiUser),
            "{app}.add_{model}",
        ),
        HTTPMethod.DELETE: (
            T_DELETE_PERM,
            model_permission("view", ApiUser),
        ),
    }


########################################################################################


class ApiUserPermissionsMixin:
    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = {
        HTTPMethod.GET: (T_VIEW_PERM, model_permission("view", ApiUserPermissions)),
        HTTPMethod.PATCH: (
            T_CHANGE_PERM,
            model_permission("change", ApiUserPermissions),
        ),
        HTTPMethod.PUT: (
            T_CHANGE_PERM,
            model_permission("change", ApiUserPermissions),
        ),
    }


########################################################################################


class ApiUserPermissionsLinkMixin(ApiUserGroupsLinkMixin):
    pass
