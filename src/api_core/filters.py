from typing import TYPE_CHECKING, override

from django.db.models import Q, TextChoices
from django_filters import CharFilter, ChoiceFilter, NumberFilter, RangeFilter
from django_filters.constants import EMPTY_VALUES

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet

########################################################################################


class FloatFilter(NumberFilter):
    pass


class FloatRangeFilter(RangeFilter):
    pass


class DecimalFilter(NumberFilter):
    pass


class DecimalRangeFilter(RangeFilter):
    pass


class IntFilter(NumberFilter):
    pass


class IntRangeFilter(RangeFilter):
    pass


########################################################################################


class LoweredFilter(CharFilter):
    @override
    def __init__(
        self,
        field_name: str | None = None,
        lookup_expr: str | None = None,
        *,
        distinct: bool = False,
        exclude: bool = False,
        label: str | None = None,
        method: str | None = None,
        **kwargs: object,
    ) -> None:
        lookup_expr = lookup_expr or "im_unaccent__icontains"

        super().__init__(
            field_name=field_name,
            lookup_expr=lookup_expr,
            distinct=distinct,
            exclude=exclude,
            label=label,
            method=method,
            **kwargs,
        )


########################################################################################


class LoweredSearchFilter(LoweredFilter):
    @override
    def __init__(
        self,
        field_name: str | None = None,
        lookup_expr: str | None = None,
        *search_fields: str,
        distinct: bool = False,
        exclude: bool = False,
        label: str | None = None,
        method: str | None = None,
        **kwargs: object,
    ) -> None:
        self.search_fields: Sequence[str] = search_fields

        super().__init__(
            field_name=field_name,
            lookup_expr=lookup_expr,
            distinct=distinct,
            exclude=exclude,
            label=label,
            method=method,
            **kwargs,
        )

    @override
    def filter(self, qs: QuerySet, value: str | None) -> QuerySet:
        if value in EMPTY_VALUES or not self.search_fields:
            return qs

        if self.distinct:
            qs: QuerySet = qs.distinct()

        query = Q()

        for field in self.search_fields:
            query |= Q(**{f"{field}__{self.lookup_expr}": value})

        qs: QuerySet = qs.filter(query) if not self.exclude else qs.exclude(query)

        return qs


########################################################################################


class TypedChoiceFilter(ChoiceFilter):
    @override
    def __init__(
        self,
        field_name: str | None = None,
        lookup_expr: str | None = None,
        *,
        distinct: bool = False,
        enum: type[TextChoices] | None = None,
        exclude: bool = False,
        label: str | None = None,
        method: str | None = None,
        **kwargs: object,
    ) -> None:
        if enum is None or not issubclass(TextChoices, enum):
            raise ValueError(
                "Must provide a TextChoices subclass for enum keyword-argument.",
            )

        self.enum = enum

        kwargs.setdefault("choices", enum.choices)

        super().__init__(
            field_name=field_name,
            lookup_expr=lookup_expr,
            distinct=distinct,
            exclude=exclude,
            label=label,
            method=method,
            **kwargs,
        )


########################################################################################


class TypedLoweredFilter(TypedChoiceFilter, LoweredFilter):
    pass
