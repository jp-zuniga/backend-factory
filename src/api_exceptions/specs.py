from http import HTTPStatus
from typing import TYPE_CHECKING

from dmr import HeaderSpec, ResponseSpec

from .errors import (
    ApiError,
    BadRequestError,
    ConflictError,
    ContentTooLargeError,
    ForbiddenError,
    NotFoundError,
    ThrottleExceededError,
    UnacceptableHeaderError,
    UnauthorizedError,
    UnsupportedMediaError,
)
from .schemas import ApiErrorResponse

if TYPE_CHECKING:
    from collections.abc import Sequence

########################################################################################

ApiErrorSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(ApiError),
    status_code=ApiError.default_http_status,
)

NotAllowedSpec = ResponseSpec(
    return_type=ApiErrorSpec.return_type,
    status_code=HTTPStatus.METHOD_NOT_ALLOWED,
)

########################################################################################

BadRequestSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(BadRequestError),
    status_code=BadRequestError.default_http_status,
)

ConflictSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(ConflictError),
    status_code=ConflictError.default_http_status,
)

ContentTooLargeSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(ContentTooLargeError),
    status_code=ContentTooLargeError.default_http_status,
)

ForbiddenSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(ForbiddenError),
    status_code=ForbiddenError.default_http_status,
)

NotFoundSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(NotFoundError),
    status_code=NotFoundError.default_http_status,
)


ThrottleExceededSpec = ResponseSpec(
    headers={
        "Retry-After": HeaderSpec(skip_validation=True),
        "X-RateLimit-Limit": HeaderSpec(skip_validation=True),
        "X-RateLimit-Remaining": HeaderSpec(skip_validation=True),
        "X-RateLimit-Reset": HeaderSpec(skip_validation=True),
    },
    return_type=ApiErrorResponse.from_exc(ThrottleExceededError),
    status_code=ThrottleExceededError.default_http_status,
)

UnacceptableHeaderSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(UnacceptableHeaderError),
    status_code=UnacceptableHeaderError.default_http_status,
)

UnauthorizedSpec = ResponseSpec(
    headers={"WWW-Authenticate": HeaderSpec(required=False, skip_validation=True)},
    return_type=ApiErrorResponse.from_exc(UnauthorizedError),
    status_code=UnauthorizedError.default_http_status,
)

UnsupportedMediaSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(UnsupportedMediaError),
    status_code=UnsupportedMediaError.default_http_status,
)

########################################################################################

ERROR_SPECS: Sequence[ResponseSpec] = (
    BadRequestSpec,
    ApiErrorSpec,
    ConflictSpec,
    ContentTooLargeSpec,
    ForbiddenSpec,
    NotAllowedSpec,
    UnacceptableHeaderSpec,
    NotFoundSpec,
    ThrottleExceededSpec,
    UnauthorizedSpec,
    UnsupportedMediaSpec,
)
