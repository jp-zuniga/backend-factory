from typing import TYPE_CHECKING

from django.db.models import (
    DB_CASCADE,
    CharField,
    CheckConstraint,
    DateTimeField,
    EmailField,
    F,
    ForeignKey,
    Index,
    Q,
    UniqueConstraint,
)
from django.db.models.functions import Lower, Now
from django.utils.timezone import now
from pgtrigger import (
    Protect,
    Q as TriggerQ,
    ReadOnly,
    Update,
)

from api_auth.enums import VerificationPurposes
from api_core.models.base import ApiModel
from api_utils.db import track_table

from .user import ApiUser

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pgtrigger import Trigger

########################################################################################

LIVE: Q = Q(consumed_at__isnull=True, invalidated_at__isnull=True)

########################################################################################


@track_table(exclude=("token_hash",))
class VerificationCode(ApiModel):
    api_user = ForeignKey(
        on_delete=DB_CASCADE,
        related_name="verification_codes",
        to=ApiUser,
    )

    email = EmailField()
    purpose = CharField(max_length=30)
    token_hash = CharField(max_length=128)

    created_at = DateTimeField(db_default=Now(), default=now)
    expires_at = DateTimeField()

    consumed_at = DateTimeField(db_default=None, default=None, null=True)
    invalidated_at = DateTimeField(db_default=None, default=None, null=True)

    class Meta(ApiModel.Meta):
        constraints: Sequence[CheckConstraint | UniqueConstraint] = (
            CheckConstraint(
                condition=Q(purpose__in=VerificationPurposes.values),
                name="chk_%(class)s_purpose",
            ),
            CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="chk_%(class)s_lifetime",
            ),
            CheckConstraint(
                condition=Q(consumed_at__isnull=True) | Q(invalidated_at__isnull=True),
                name="chk_%(class)s_single_outcome",
            ),
            UniqueConstraint(fields=["token_hash"], name="unq_%(class)s_token"),
            UniqueConstraint(
                F("purpose"),
                Lower("email"),
                condition=LIVE,
                name="unq_%(class)s_live",
            ),
        )

        indexes: Sequence[Index] = (
            Index(
                condition=LIVE,
                fields=["expires_at"],
                name="idx_%(class)s_expiration",
            ),
        )

        ordering: Sequence[str] = ("created_at",)

        triggers: Sequence[Trigger] = (
            *ApiModel.Meta.triggers,
            ReadOnly(
                fields=[
                    "api_user",
                    "created_at",
                    "email",
                    "expires_at",
                    "purpose",
                    "token_hash",
                ],
                name="trg_verificationcode_readonly",
            ),
            Protect(
                condition=(
                    TriggerQ(old__consumed_at__isnull=False)
                    | TriggerQ(old__invalidated_at__isnull=False)
                ),
                name="trg_verificationcode_protect_settled",
                operation=Update,
            ),
        )
