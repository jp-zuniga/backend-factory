from http import HTTPStatus

import pytest

from django.core.exceptions import TooManyFieldsSent, TooManyFilesSent
from dmr.exceptions import RequestSerializationError

from api_exceptions.enums import ContentTooLargeErrorTypes
from api_exceptions.errors import ContentTooLargeError

########################################################################################


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TooManyFieldsSent(), ContentTooLargeErrorTypes.FIELDS),
        (TooManyFilesSent(), ContentTooLargeErrorTypes.FILES),
        (ValueError("too big"), ContentTooLargeErrorTypes.BODY),
    ],
)
def test_from_upload_error_maps_the_matching_type(
    exc: Exception,
    expected: ContentTooLargeErrorTypes,
) -> None:
    error: ContentTooLargeError = ContentTooLargeError.from_upload_error(exc)  # ty: ignore[invalid-argument-type]

    assert error.detail == expected.value
    assert error.default_http_status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


########################################################################################


def test_unwrap_handles_a_direct_upload_error() -> None:
    error = ContentTooLargeError.unwrap(TooManyFilesSent())

    assert error is not None
    assert error.detail == ContentTooLargeErrorTypes.FILES.value


def test_unwrap_handles_a_wrapped_upload_error() -> None:
    try:
        try:
            raise TooManyFieldsSent  # ruff: ignore[raise-within-try]
        except TooManyFieldsSent as cause:
            raise RequestSerializationError from cause
    except RequestSerializationError as wrapped:
        error = ContentTooLargeError.unwrap(wrapped)

    assert error is not None
    assert error.detail == ContentTooLargeErrorTypes.FIELDS.value


def test_unwrap_ignores_unrelated_errors() -> None:
    assert ContentTooLargeError.unwrap(ValueError("nada que ver")) is None


def test_unwrap_ignores_a_serialization_error_without_an_upload_cause() -> None:
    with pytest.raises(RequestSerializationError) as wrapped:  # ruff: ignore[pytest-raises-with-multiple-statements]
        try:
            raise ValueError("otra cosa")  # ruff: ignore[raise-within-try]
        except ValueError as cause:
            raise RequestSerializationError from cause

    assert ContentTooLargeError.unwrap(wrapped.value) is None
