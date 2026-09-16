from typing import TYPE_CHECKING

from django.contrib.auth.models import Group, Permission
from django.db.models import CASCADE, DB_CASCADE, ForeignKey, UniqueConstraint

from api_core.models.base import ApiModel
from api_utils.db import track_table

from .user import ApiUser

if TYPE_CHECKING:
    from collections.abc import Sequence

########################################################################################


@track_table()
class ApiUserGroups(ApiModel):
    api_user = ForeignKey(
        on_delete=DB_CASCADE,
        related_name="+",
        to=ApiUser,
    )

    group = ForeignKey(
        on_delete=DB_CASCADE,
        related_name="+",
        to=Group,
    )

    class Meta(ApiModel.Meta):
        constraints: Sequence[UniqueConstraint] = (
            UniqueConstraint(
                fields=["api_user", "group"],
                name="unq_%(class)s_apiuser_group",
            ),
        )


########################################################################################


@track_table()
class ApiUserPermissions(ApiModel):
    api_user = ForeignKey(
        on_delete=CASCADE,
        related_name="+",
        to=ApiUser,
    )

    permission = ForeignKey(
        on_delete=CASCADE,
        related_name="+",
        to=Permission,
    )

    class Meta(ApiModel.Meta):
        constraints: Sequence[UniqueConstraint] = (
            UniqueConstraint(
                fields=["api_user", "permission"],
                name="unq_%(class)s_apiuser_permission",
            ),
        )
