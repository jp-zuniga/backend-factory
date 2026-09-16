from uuid import UUID

from django.db.models import ForeignKey, UUIDField
from pydantic import PositiveInt, create_model

from api_core.schemas.path import InstancePath, UuidInstancePath
from api_utils.types import DatabaseModel

########################################################################################


def build_scoped_path(
    model: type[DatabaseModel],
    parent_field: str,
    *,
    base: type[InstancePath] = UuidInstancePath,
) -> type[InstancePath]:
    """
    Build the path schema a scoped detail endpoint parses.

    The parent's key is named after the column the relation writes,
    which is both the url parameter a scoped controller reads and a
    valid lookup against the sub-resource's table.

    Args:
        model: The sub-resource's model.
        parent_field: The relation on *model* that points at the parent.
        base: The path schema the sub-resource's own key comes from.

    Returns:
        A path schema with the sub-resource's key and its parent's.

    """

    field: ForeignKey = model._meta.get_field(parent_field)

    hint = UUID if isinstance(field.target_field, UUIDField) else PositiveInt

    kwargs: dict = {"__base__": base, str(field.attname): (hint, ...)}

    parent: str = parent_field.replace("_", " ").title().replace(" ", "")

    return create_model(
        f"{model.__name__}{parent}Path",
        **kwargs,
    )
