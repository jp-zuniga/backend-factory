from datetime import date, datetime
from uuid import UUID

import hypothesis as ht
import hypothesis.strategies as st
import pytest

from pydantic_core import PydanticCustomError

from api_core.schemas.validators import (
    coerce_date,
    coerce_datetime,
    coerce_uuid,
    empty_or_email,
    empty_or_url,
)

########################################################################################


@ht.given(st.dates())
def test_coerce_date_parses_iso_strings(value: date) -> None:
    assert coerce_date(value.isoformat()) == value


@ht.given(
    st.text(
        alphabet=st.characters(categories=("L",)),
        min_size=1,
        max_size=20,
    ),
)
def test_coerce_date_passes_through_unparseable_strings(garbage: str) -> None:
    assert coerce_date(garbage) == garbage


def test_coerce_date_ignores_non_strings() -> None:
    assert coerce_date(None) is None
    assert coerce_date(42) == 42


########################################################################################


@ht.given(st.datetimes())
def test_coerce_datetime_parses_iso_strings(value: datetime) -> None:
    assert coerce_datetime(value.isoformat()) == value


def test_coerce_datetime_passes_through_unparseable_strings() -> None:
    assert coerce_datetime("no-es-una-fecha") == "no-es-una-fecha"


def test_coerce_datetime_ignores_non_strings() -> None:
    assert coerce_datetime(None) is None


########################################################################################


@ht.given(st.uuids())
def test_coerce_uuid_parses_canonical_strings(value: UUID) -> None:
    assert coerce_uuid(str(value)) == value


def test_coerce_uuid_passes_through_unparseable_strings() -> None:
    assert coerce_uuid("no-es-un-uuid") == "no-es-un-uuid"


def test_coerce_uuid_ignores_non_strings() -> None:
    assert coerce_uuid(None) is None


########################################################################################


def test_empty_or_email_accepts_the_empty_string() -> None:
    assert empty_or_email("") == ""  # ruff: ignore[compare-to-empty-string]


def test_empty_or_email_accepts_a_valid_address() -> None:
    assert empty_or_email("persona@unit.example.com") == "persona@unit.example.com"


def test_empty_or_email_rejects_an_invalid_address() -> None:
    with pytest.raises(PydanticCustomError) as raised:
        empty_or_email("no-es-un-correo")

    assert raised.value.context["msg"] == "Debe ser un correo válido."  # ty: ignore[not-subscriptable]


########################################################################################


def test_empty_or_url_accepts_the_empty_string() -> None:
    assert empty_or_url("") == ""  # ruff: ignore[compare-to-empty-string]


def test_empty_or_url_accepts_a_valid_url() -> None:
    assert empty_or_url("https://unit.example.com") == "https://unit.example.com"


def test_empty_or_url_rejects_an_invalid_url() -> None:
    with pytest.raises(PydanticCustomError) as raised:
        empty_or_url("no-es-un-url")

    assert raised.value.context["msg"] == "Debe ser un URL válido."  # ty: ignore[not-subscriptable]
