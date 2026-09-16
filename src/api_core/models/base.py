from typing import TYPE_CHECKING, override
from uuid import UUID, uuid7

from django.db.models import (
    BooleanField,
    DateTimeField,
    Index,
    Model,
    UUIDField,
)
from django.db.models.functions import UUID7, Now
from django.utils.timezone import now
from pgtrigger import (
    AnyChange,
    Before,
    Delete,
    Protect,
    ReadOnly,
    SoftDelete,
    Statement,
    Trigger,
    Truncate,
    Update,
)

from typing_extensions import disjoint_base

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import ClassVar

    from django.db.models import Manager, QuerySet
    from django.db.models.options import Options

    from .event import ApiEvent

    from ty_extensions import Intersection

########################################################################################


@disjoint_base
class ApiModel(Model):
    id = UUIDField(db_default=UUID7(), default=uuid7, primary_key=True)

    pk: UUID

    pgh_event_model: ClassVar[ApiEvent]

    objects: ClassVar[Intersection[Manager, QuerySet]]

    _default_manager: ClassVar[Intersection[Manager, QuerySet]]

    _meta: ClassVar[Options]

    class Meta:
        abstract: bool = True
        triggers: Sequence[Trigger] = (
            Trigger(
                level=Statement,
                name="trg_protect_truncate",
                operation=Truncate,
                when=Before,
                func="RAISE EXCEPTION 'No se permite truncar tablas.';",
            ),
            ReadOnly(fields=["id"], name="trg_readonly_primarykey"),
        )

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(id={self.pk})"


########################################################################################


@disjoint_base
class ApiTimestampedModel(ApiModel):
    """
    Base for tables that record when a row was written.

    `updated_at` is maintained by the database, so it stays honest
    no matter who writes the row: the ORM, a management command,
    a migration, or `psql`.
    """

    created_at = DateTimeField(db_default=Now(), default=now)
    updated_at = DateTimeField(db_default=Now(), default=now)

    class Meta(ApiModel.Meta):
        abstract: bool = True

        indexes: Sequence[Index] = (
            Index(fields=["created_at"], name="idx_%(class)s_createdat"),
            Index(fields=["updated_at"], name="idx_%(class)s_updatedat"),
        )

        # uuid7 primary keys are monotonic, so this is "newest first"
        ordering: Sequence[str] = ("-id",)

        triggers: Sequence[Trigger] = (
            *ApiModel.Meta.triggers,
            Trigger(
                condition=AnyChange(),
                name="trg_touch_updatedat",
                operation=Update,
                when=Before,
                func="NEW.updated_at = NOW(); RETURN NEW;",
            ),
        )


########################################################################################


@disjoint_base
class ApiAppendOnlyModel(ApiTimestampedModel):
    """
    Base for tables that are written once and never touched again.

    Rows can only be inserted: the database rejects every update
    and every delete, which is why there is no `updated_at`.
    """

    updated_at = None

    class Meta(ApiTimestampedModel.Meta):
        abstract: bool = True

        indexes: Sequence[Index] = (
            Index(fields=["created_at"], name="idx_%(class)s_createdat"),
        )

        triggers: Sequence[Trigger] = (
            *ApiModel.Meta.triggers,
            Protect(name="trg_append_only", operation=(Delete | Update)),
        )


########################################################################################


@disjoint_base
class ApiProtectedModel(ApiTimestampedModel):
    """
    Base for tables whose rows may be edited but never deleted.

    Use it for records that other tables, audits, or humans
    are expected to keep referring to.
    """

    class Meta(ApiTimestampedModel.Meta):
        abstract: bool = True

        triggers: Sequence[Trigger] = (
            *ApiTimestampedModel.Meta.triggers,
            Protect(name="trg_protect_delete", operation=Delete),
        )


########################################################################################


@disjoint_base
class ApiSoftDeleteModel(ApiTimestampedModel):
    """
    Base for tables where a delete only flips a flag.

    `DELETE` statements are rewritten into `is_active = False`,
    so references to the row survive and queries must filter it out.
    """

    is_active = BooleanField(db_default=True, default=True)

    class Meta(ApiTimestampedModel.Meta):
        abstract: bool = True

        indexes: Sequence[Index] = (
            *ApiTimestampedModel.Meta.indexes,
            Index(fields=["is_active"], name="idx_%(class)s_isactive"),
        )

        triggers: Sequence[Trigger] = (
            *ApiTimestampedModel.Meta.triggers,
            SoftDelete(field="is_active", name="trg_softdelete_isactive", value=False),
        )
