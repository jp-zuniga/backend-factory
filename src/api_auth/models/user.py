from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Group, Permission, PermissionsMixin
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db.models import (
    BooleanField,
    CharField,
    DateTimeField,
    EmailField,
    Index,
    ManyToManyField,
    Q,
    UniqueConstraint,
)
from django.db.models.functions import Lower, Upper
from pgtrigger import (
    Before,
    F as TriggerF,
    Insert,
    Protect,
    Q as TriggerQ,
    Trigger,
    Update,
)

from api_core.models.base import ApiSoftDeleteModel
from api_utils.db import ImmutableUnaccent, track_table

from .manager import ApiUserManager

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

    from django.db.models import QuerySet

    from ty_extensions import Intersection

########################################################################################


@track_table()
class ApiUser(ApiSoftDeleteModel, AbstractBaseUser, PermissionsMixin):
    first_name = CharField(db_default="", default="", max_length=100)
    last_name = CharField(db_default="", default="", max_length=100)
    email = EmailField(db_default="", default="")
    username = CharField(max_length=100)
    password = CharField(max_length=128)

    email_verified_at = DateTimeField(db_default=None, default=None, null=True)

    is_staff = BooleanField(db_default=False, default=False)
    is_superuser = BooleanField(db_default=False, default=False)

    groups = ManyToManyField(
        related_name="users",
        through="ApiUserGroups",
        to=Group,
    )

    permissions = ManyToManyField(
        related_name="users",
        through="ApiUserPermissions",
        to=Permission,
    )

    objects: ClassVar[Intersection[ApiUserManager, QuerySet]] = ApiUserManager()

    last_login = None
    user_permissions = None

    EMAIL_FIELD: Final[str] = "email"
    USERNAME_FIELD: Final[str] = "username"

    class Meta(ApiSoftDeleteModel.Meta):
        constraints: Sequence[UniqueConstraint] = (
            UniqueConstraint(
                Lower("email"),
                condition=Q(email__len__gt=0, is_active=True),
                name="unq_%(class)s_email",
            ),
            UniqueConstraint(
                Lower("username"),
                condition=Q(is_active=True),
                name="unq_%(class)s_username",
            ),
        )

        indexes: Sequence[Index] = (
            GinIndex(
                OpClass(
                    expression=Upper(ImmutableUnaccent("username")),
                    name="gin_trgm_ops",
                ),
                name="gin_%(class)s_username",
            ),
            GinIndex(
                OpClass(
                    expression=Upper(ImmutableUnaccent("email")),
                    name="gin_trgm_ops",
                ),
                condition=Q(email__len__gt=0),
                name="gin_%(class)s_email",
            ),
            Index(fields=["created_at"], name="idx_%(class)s_createdat"),
            Index(fields=["email_verified_at"], name="idx_%(class)s_emailverifiedat"),
            Index(fields=["is_active"], name="idx_%(class)s_isactive"),
        )

        ordering: Sequence[str] = ("username",)
        triggers: Sequence[Trigger] = (
            *ApiSoftDeleteModel.Meta.triggers,
            Protect(name="trg_apiuser_protect_insert", operation=Insert),
            Trigger(
                condition=TriggerQ(old__email__df=TriggerF("new__email")),
                func="NEW.email_verified_at = NULL; RETURN NEW;",
                name="trg_apiuser_unverify_email",
                operation=Update,
                when=Before,
            ),
        )
