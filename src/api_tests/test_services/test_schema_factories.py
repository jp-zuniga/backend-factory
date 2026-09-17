from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from django.contrib.auth.models import Group
from django_filters import (
    BooleanFilter,
    CharFilter,
    DateFilter,
    DateFromToRangeFilter,
    DateTimeFilter,
    DurationFilter,
    FilterSet,
    NumberFilter,
    OrderingFilter,
    RangeFilter,
    TimeFilter,
    UUIDFilter,
)

from api_auth.enums import ApiUserTypes
from api_auth.models import ApiUserGroups
from api_core.filters import (
    DecimalFilter,
    DecimalRangeFilter,
    FloatFilter,
    FloatRangeFilter,
    IntFilter,
    IntRangeFilter,
    TypedChoiceFilter,
)
from api_core.schemas.factories.filters import (
    build_filter_order_enum,
    build_filter_query,
)
from api_core.schemas.factories.path import build_scoped_path
from api_core.schemas.filters import UnpaginatedFilterQuery
from api_exceptions.errors import BadRequestError

########################################################################################


class _WideFilterSet(FilterSet):
    flag = BooleanFilter()
    day = DateFilter()
    moment = DateTimeFilter()
    span = DurationFilter()
    amount = DecimalFilter()
    ratio = FloatFilter()
    count = IntFilter()
    clock = TimeFilter()
    kind = TypedChoiceFilter(enum=ApiUserTypes)
    token = UUIDFilter()
    label = CharFilter()

    created = DateFromToRangeFilter()
    price = DecimalRangeFilter()
    score = FloatRangeFilter()
    age = IntRangeFilter()

    order = OrderingFilter(fields=("id",))

    class Meta:
        fields: tuple = ()
        model = Group


########################################################################################


def test_build_filter_query_maps_every_supported_filter_type() -> None:
    built = build_filter_query(UnpaginatedFilterQuery, _WideFilterSet)

    fields = built.model_fields

    assert fields["flag"].annotation == (bool | None)
    assert fields["day"].annotation == (date | None)
    assert fields["moment"].annotation == (datetime | None)
    assert fields["span"].annotation == (timedelta | None)
    assert fields["amount"].annotation == (Decimal | None)
    assert fields["ratio"].annotation == (float | None)
    assert fields["count"].annotation == (int | None)
    assert fields["clock"].annotation == (time | None)
    assert fields["token"].annotation == (UUID | None)
    assert fields["label"].annotation == (str | None)

    assert "created_after" in fields
    assert "created_before" in fields
    assert "price_min" in fields
    assert "price_max" in fields
    assert "score_min" in fields
    assert "score_max" in fields
    assert "age_min" in fields
    assert "age_max" in fields

    assert "order" in fields


def test_build_filter_query_applies_a_boolean_default() -> None:
    built = build_filter_query(UnpaginatedFilterQuery, _WideFilterSet, flag=True)

    assert built.model_fields["flag"].default is True


def test_build_filter_query_applies_a_valid_enum_default() -> None:
    built = build_filter_query(
        UnpaginatedFilterQuery,
        _WideFilterSet,
        kind=ApiUserTypes.CLIENT.value,
    )

    assert built.model_fields["kind"].default == ApiUserTypes.CLIENT


def test_build_filter_query_rejects_an_invalid_enum_default() -> None:
    with pytest.raises(ValueError, match="no es un valor válido"):
        build_filter_query(UnpaginatedFilterQuery, _WideFilterSet, kind="no-existe")


def test_build_filter_query_ignores_defaults_for_unknown_fields() -> None:
    built = build_filter_query(UnpaginatedFilterQuery, _WideFilterSet, nope=True)

    assert "nope" not in built.model_fields


########################################################################################


def test_build_filter_query_rejects_an_unsupported_filter() -> None:
    class _Unsupported(FilterSet):
        raw = NumberFilter()

        class Meta:
            fields: tuple = ()
            model = Group

    with pytest.raises(TypeError, match="unsupported"):
        build_filter_query(UnpaginatedFilterQuery, _Unsupported)


def test_build_filter_query_rejects_an_ordering_filter_without_choices() -> None:
    class _BareOrdering(FilterSet):
        order = OrderingFilter()

        class Meta:
            fields: tuple = ()
            model = Group

    with pytest.raises(TypeError, match="ordering choices"):
        build_filter_query(UnpaginatedFilterQuery, _BareOrdering)


def test_build_filter_query_rejects_an_unknown_range_filter() -> None:
    class _BareRange(FilterSet):
        span = RangeFilter()

        class Meta:
            fields: tuple = ()
            model = Group

    with pytest.raises(TypeError, match="unknown"):
        build_filter_query(UnpaginatedFilterQuery, _BareRange)


########################################################################################


def test_build_filter_query_enforces_exclusive_fields() -> None:
    built = build_filter_query(
        UnpaginatedFilterQuery,
        _WideFilterSet,
        exclusive=(("flag", "flag"),),
    )

    with pytest.raises(BadRequestError):
        built(flag=True)  # ty: ignore[unknown-argument]


def test_build_filter_query_enforces_inclusive_fields() -> None:
    class _Pair(FilterSet):
        left = BooleanFilter()
        right = BooleanFilter()

        class Meta:
            fields: tuple = ()
            model = Group

    built = build_filter_query(
        UnpaginatedFilterQuery,
        _Pair,
        inclusive=(("left", "right"),),
    )

    with pytest.raises(BadRequestError):
        built(left=False, right=False)  # ty: ignore[unknown-argument]

    assert built(left=True, right=False)  # ty: ignore[unknown-argument]


########################################################################################


def test_build_filter_order_enum_prefixes_ascending_and_descending() -> None:
    enum = build_filter_order_enum("Order", (("name", "Name"), ("-name", "-Name")))

    assert enum.asc_name.value == "name"  # ty: ignore[unresolved-attribute]
    assert enum.desc_name.value == "-name"  # ty: ignore[unresolved-attribute]


########################################################################################


def test_build_scoped_path_uses_the_foreign_keys_target_type() -> None:
    uuid_path = build_scoped_path(ApiUserGroups, "api_user")
    int_path = build_scoped_path(ApiUserGroups, "group")

    assert uuid_path.model_fields["api_user_id"].annotation is UUID
    assert int_path.model_fields["group_id"].annotation.__name__ == "int"
    assert "id" in uuid_path.model_fields
