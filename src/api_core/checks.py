from typing import TYPE_CHECKING

from django.apps import apps
from django.core.checks import (
    Error as CheckError,
    Tags,
    register,
)

from api_core.models.base import ApiModel

if TYPE_CHECKING:
    from pgtrigger import Trigger

########################################################################################


@register(check=Tags.models)
def check_api_model_triggers(
    *args,  # ruff: ignore[missing-type-args, unused-function-argument]
    **kwargs,  # ruff: ignore[missing-type-kwargs, unused-function-argument]
) -> list[CheckError]:
    errors = []

    for model in apps.get_models():
        if issubclass(model, ApiModel) and not model._meta.abstract:
            base = ApiModel

            for specific in model.__mro__[1:]:
                if issubclass(base, ApiModel) and specific._meta.abstract:
                    base = specific

            required_triggers: set[Trigger] = set(
                base._meta.original_attrs.get("triggers", ())
            )

            subcls_triggers: set[Trigger] = set(
                model._meta.original_attrs.get("triggers", ())
            )

            if not required_triggers.issubset(subcls_triggers):
                errors.append(
                    CheckError(
                        id="api_core.E001",
                        hint=(
                            f"Añade `*{base.__name__}.Meta.triggers,` "
                            "al definir nuevos triggers en `Meta`."
                        ),
                        msg=(
                            "Modelos concretos con custom triggers "
                            f"deben heredar `{base.__name__}.Meta.triggers`."
                        ),
                        obj=model,
                    )
                )

    return errors
