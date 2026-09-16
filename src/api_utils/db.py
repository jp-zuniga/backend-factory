from functools import cache
from typing import TYPE_CHECKING, Final, Literal

from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db.models import Index, Q, Transform
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.transaction import get_connection
from pghistory import track

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from django.db.models.options import Options

    from api_utils.types import DatabaseModel


########################################################################################


class ImmutableUnaccent(Transform):
    bilateral: Final[bool] = True
    function: Final[str] = "public.immutable_unaccent"
    lookup_name: Final[str] = "im_unaccent"


########################################################################################


@cache
def model_permission(
    action: Literal["add", "change", "delete", "view"],
    model: type[DatabaseModel],
) -> str:
    meta: Options = model._meta  # ruff: ignore[private-member-access]

    return f"{meta.app_label}.{action}_{meta.model_name}"


########################################################################################


def set_immediate_constraints() -> None:
    """
    Execute SQL to immediately evaluate deferred constraints during a transaction.

    Used in `api_core.services.operations` to construct nested
    errors that point to the database column that failed.

    Should only ever be called from within a `django.db.transaction.atomic` block.

    The query is rolled back at the end of the transaction.
    """

    with get_connection().cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


########################################################################################


def track_table[Table: type[DatabaseModel]](
    exclude: Sequence[str] | None = None,
    meta: dict | None = None,
) -> Callable[[Table], Table]:
    """
    Build a decorator that tracks a model's history with `pghistory`.

    Args:
        meta: Extra `Meta` options for the generated event model.
        exclude: Names of the tracked model's fields that must never
                 be copied into the event model, e.g. secrets.

    Returns:
        A decorator that attaches the event model to its table.

    """

    meta: dict = meta or {}
    meta: dict = meta | {
        "indexes": (
            *(meta.pop("indexes", ())),
            GinIndex(
                condition=Q(pgh_context__isnull=False),
                fields=["pgh_context"],
                name="gin_%(class)s_ctx_path",
                opclasses=["jsonb_path_ops"],
            ),
            GinIndex(
                OpClass(
                    expression=KeyTextTransform("url", "pgh_context"),
                    name="gin_trgm_ops",
                ),
                condition=Q(pgh_context__isnull=False),
                name="gin_%(class)s_ctx_url",
            ),
            Index(
                KeyTransform("id", KeyTransform("user", "pgh_context")),
                condition=Q(pgh_context__isnull=False, pgh_context__has_key="user"),
                name="idx_%(class)s_ctx_userid",
            ),
            Index(
                fields=["pgh_created_at"],
                name="idx_%(class)s_pghcreatedat",
            ),
            Index(
                fields=["pgh_label"],
                name="idx_%(class)s_pghlabel",
            ),
            Index(
                fields=["id"],
                name="idx_%(class)s_id",
            ),
        ),
    }

    def decorator(model: Table) -> Table:
        return track(
            obj_field=None,
            context_field=None,  # ty: ignore[invalid-argument-type]
            context_id_field=None,  # ty: ignore[invalid-argument-type]
            append_only=True,
            exclude=exclude,  # ty: ignore[invalid-argument-type]
            model_name=f"{model.__name__}Event",
            meta=meta,
        )(model)

    return decorator
