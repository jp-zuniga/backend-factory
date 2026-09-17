from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum, EnumType
from functools import cache
from typing import get_args
from uuid import UUID

from django_filters import (
    AllValuesFilter,
    AllValuesMultipleFilter,
    BaseCSVFilter,
    BaseInFilter,
    BaseRangeFilter,
    BooleanFilter,
    ChoiceFilter as UntypedChoiceFilter,
    DateFilter,
    DateFromToRangeFilter,
    DateRangeFilter,
    DateTimeFilter,
    DateTimeFromToRangeFilter,
    DurationFilter,
    FilterSet,
    IsoDateTimeFilter,
    IsoDateTimeFromToRangeFilter,
    LookupChoiceFilter,
    MultipleChoiceFilter,
    NumberFilter,
    NumericRangeFilter,
    OrderingFilter,
    RangeFilter,
    TimeFilter,
    TimeRangeFilter,
    TypedChoiceFilter as EnumlessChoiceFilter,
    TypedMultipleChoiceFilter as EnumlessMultipleChoiceFilter,
    UUIDFilter,
)
from pydantic import Field, create_model, model_validator

from api_core.filters import (
    DecimalFilter,
    DecimalRangeFilter,
    FloatFilter,
    FloatRangeFilter,
    IntFilter,
    IntRangeFilter,
    TypedChoiceFilter,
)
from api_core.schemas.base import DTO
from api_core.schemas.filters import FilterQuery
from api_exceptions.enums import BadRequestErrorTypes, RequestScopes
from api_exceptions.errors import BadRequestError

########################################################################################


def build_filter_query[  # ruff: ignore[complex-structure, too-many-branches, too-many-statements]
    Q: type[FilterQuery],
    F: type[FilterSet],
](
    base: Q,
    cls: F,
    exclusive: Sequence[tuple[str, str]] | None = None,
    inclusive: Sequence[tuple[str, str]] | None = None,
    **defaults: bool | str,
) -> Q:
    kwargs: dict = {"__base__": base}

    for name, field in cls.base_filters.items():  # ty:ignore[unresolved-attribute]
        match field:
            # simple cases:
            case BooleanFilter():
                hint = bool
            case DateFilter():
                hint = date
            case DateTimeFilter() | IsoDateTimeFilter():
                hint = datetime
            case DurationFilter():
                hint = timedelta
            case DecimalFilter():
                hint = Decimal
            case FloatFilter():
                hint = float
            case IntFilter():
                hint = int
            case TimeFilter():
                hint = time
            case TypedChoiceFilter():
                hint = field.enum
            case UUIDFilter():
                hint = UUID
            # complex cases:
            case RangeFilter():
                match field:
                    case DateFromToRangeFilter():
                        bounds_and_hint = ("after", "before", date)
                    case DateTimeFromToRangeFilter() | IsoDateTimeFromToRangeFilter():
                        bounds_and_hint = ("after", "before", datetime)
                    case DecimalRangeFilter():
                        bounds_and_hint = ("min", "max", Decimal)
                    case FloatRangeFilter():
                        bounds_and_hint = ("min", "max", float)
                    case IntRangeFilter():
                        bounds_and_hint = ("min", "max", int)
                    case TimeRangeFilter():
                        bounds_and_hint = ("after", "before", time)
                    case _:
                        raise TypeError(
                            f"{field.__class__.__name__} "
                            "is an unknown, and therefore untyped, "
                            "subclass of RangeFilter.",
                        )

                lower, upper, range_hint = bounds_and_hint

                kwargs[f"{name}_{lower}"] = (range_hint | None, None)
                kwargs[f"{name}_{upper}"] = (range_hint | None, None)
                continue
            case OrderingFilter() if choices := field.extra.get("choices"):
                hint = build_filter_order_enum(
                    cls.__name__.replace("FilterSet", "Order"),
                    tuple(choices),
                )
            # unsupported:
            case (
                AllValuesFilter()
                | AllValuesMultipleFilter()
                | BaseCSVFilter()
                | BaseInFilter()
                | BaseRangeFilter()
                | DateRangeFilter()
                | EnumlessChoiceFilter()
                | EnumlessMultipleChoiceFilter()
                | LookupChoiceFilter()
                | MultipleChoiceFilter()
                | NumberFilter()
                | NumericRangeFilter()
                | UntypedChoiceFilter()
            ):
                raise TypeError(
                    (
                        f"{field.__class__.__name__} does not "
                        "declare any ordering choices."
                    )
                    if isinstance(field, OrderingFilter)
                    else (
                        f"{field.__class__.__name__} "
                        "is either generic over several types "
                        "or not designed for usage within a REST API, "
                        "and therefore unsupported."
                    ),
                )
            # fallback:
            case _:
                hint = str

        kwargs[name] = (
            hint | None,
            Field(default=None, examples=[member.value for member in hint])
            if isinstance(hint, EnumType)
            else None,
        )

    for name, default in defaults.items():
        if name not in kwargs:
            continue

        types: Sequence[type] = get_args(tp=kwargs[name][0])

        enums: Sequence[type[Enum]] = tuple(
            filter(lambda t: isinstance(t, EnumType), types)
        )

        if enums:
            # if the previous loop works as intended,
            # `types` should be a two-tuple in the form (type, None);
            # therefore, if there's an enum in there, it's index 0.
            members: frozenset = frozenset(member.value for member in enums[0])

            if default not in members:
                raise ValueError(
                    f"'{default}' no es un valor válido para el filtro '{name}'; "
                    f"se esperaba uno de: {', '.join(sorted(members))}.",
                )

            kwargs[name] = (kwargs[name][0], enums[0](default))
            continue

        if type(default) in types:
            kwargs[name] = (kwargs[name][0], default)

    kwargs["__validators__"] = build_filter_validators(exclusive, inclusive)

    return create_model(
        cls.__name__.replace("FilterSet", "Query"),
        **kwargs,
    )


########################################################################################


@cache
def build_filter_order_enum(
    name: str,
    choices: Sequence[tuple[str, str]],
) -> type[Enum]:
    return Enum(
        names={
            (
                f"desc_{raw.removeprefix('-').replace('-', '_')}"
                if raw.startswith("-")
                else f"asc_{raw.replace('-', '_')}"
            ): raw
            for raw, _ in choices
        },
        value=name,
    )


########################################################################################


def build_filter_validators(
    exclusive: Sequence[tuple[str, str]] | None = None,
    inclusive: Sequence[tuple[str, str]] | None = None,
) -> dict:
    validators = {}

    if exclusive is not None:

        @model_validator(mode="after")
        def check_exclusive(self: DTO) -> DTO:
            msg = "Este parámetro es mutuamente exclusivo con el parámetro '{}'."

            for f1, f2 in exclusive:
                if getattr(self, f1, None) is True and getattr(self, f2, None) is True:
                    raise BadRequestError(
                        field_errors={f1: msg.format(f2), f2: msg.format(f1)},
                        type=BadRequestErrorTypes.FAILED_VALIDATION,
                    ).scoped(RequestScopes.QUERY)

            return self

        validators["check_exclusive"] = check_exclusive

    if inclusive is not None:

        @model_validator(mode="after")
        def check_inclusive(self: DTO) -> DTO:

            for f1, f2 in inclusive:
                if (
                    getattr(self, f1, None) is False
                    and getattr(self, f2, None) is False
                ):
                    msg = (
                        f"Para filtrar correctamente, debe seleccionar '{f1}' o '{f2}'."
                    )

                    raise BadRequestError(
                        field_errors={f1: msg, f2: msg},
                        type=BadRequestErrorTypes.FAILED_VALIDATION,
                    ).scoped(RequestScopes.QUERY)

            return self

        validators["check_inclusive"] = check_inclusive

    return validators
