from typing import TYPE_CHECKING

from django.db.models import (
    DB_CASCADE,
    CharField,
    DateTimeField,
    ForeignKey,
    Index,
    OneToOneField,
    PositiveBigIntegerField,
    PositiveSmallIntegerField,
    UniqueConstraint,
)
from django.db.models.functions import Now
from django.utils.timezone import now
from pgtrigger import (
    F as TriggerF,
    Protect,
    Q as TriggerQ,
    ReadOnly,
    Update,
)

from api_core.models.base import ApiModel
from api_utils.db import track_table

from .user import ApiUser

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pgtrigger import Trigger

########################################################################################


@track_table(exclude=("secret",))
class ApiUserTotpDevice(ApiModel):
    api_user = OneToOneField(
        on_delete=DB_CASCADE,
        related_name="totp_device",
        to=ApiUser,
    )

    secret = CharField(max_length=64)

    created_at = DateTimeField(db_default=Now(), default=now)
    confirmed_at = DateTimeField(db_default=None, default=None, null=True)
    locked_until = DateTimeField(db_default=None, default=None, null=True)

    failures = PositiveSmallIntegerField(db_default=0, default=0)
    last_step = PositiveBigIntegerField(db_default=0, default=0)

    class Meta(ApiModel.Meta):
        indexes: Sequence[Index] = (
            Index(fields=["confirmed_at"], name="idx_%(class)s_confirmedat"),
            Index(fields=["locked_until"], name="idx_%(class)s_lockeduntil"),
        )

        ordering: Sequence[str] = ("created_at",)

        triggers: Sequence[Trigger] = (
            *ApiModel.Meta.triggers,
            ReadOnly(
                fields=["api_user", "created_at"],
                name="trg_apiusertotpdevice_readonly",
            ),
            Protect(
                condition=(
                    TriggerQ(old__confirmed_at__isnull=False)
                    & TriggerQ(new__secret__df=TriggerF("old__secret"))
                ),
                name="trg_apiusertotpdevice_protect_secret",
                operation=Update,
            ),
            Protect(
                condition=(
                    TriggerQ(old__confirmed_at__isnull=False)
                    & TriggerQ(new__confirmed_at__isnull=True)
                ),
                name="trg_apiusertotpdevice_protect_confirmedat",
                operation=Update,
            ),
        )


########################################################################################


@track_table(exclude=("code",))
class ApiUserRecoveryCode(ApiModel):
    device = ForeignKey(
        on_delete=DB_CASCADE,
        related_name="recovery_codes",
        to=ApiUserTotpDevice,
    )

    code = CharField(max_length=64)

    created_at = DateTimeField(db_default=Now(), default=now)
    used_at = DateTimeField(db_default=None, default=None, null=True)

    class Meta(ApiModel.Meta):
        constraints: Sequence[UniqueConstraint] = (
            UniqueConstraint(fields=["code"], name="unq_%(class)s_code"),
        )

        indexes: Sequence[Index] = (
            Index(fields=["used_at"], name="idx_%(class)s_usedat"),
        )

        ordering: Sequence[str] = ("created_at",)

        triggers: Sequence[Trigger] = (
            *ApiModel.Meta.triggers,
            ReadOnly(
                fields=["code", "created_at", "device"],
                name="trg_apiuserrecoverycode_readonly",
            ),
            Protect(
                condition=TriggerQ(old__used_at__isnull=False),
                name="trg_apiuserrecoverycode_protect_used",
                operation=Update,
            ),
        )
