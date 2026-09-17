from http import HTTPStatus
from json import loads

import pytest

from dmr.test import DMRRequestFactory

from api_exceptions.errors import ForbiddenError, NotFoundError, UnauthorizedError
from api_utils.factories import build_4xx_handler, build_500_handler

########################################################################################


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (HTTPStatus.NOT_FOUND, NotFoundError),
        (HTTPStatus.FORBIDDEN, ForbiddenError),
        (HTTPStatus.UNAUTHORIZED, UnauthorizedError),
        (HTTPStatus.BAD_REQUEST, None),
    ],
)
def test_build_4xx_handler_reports_the_matching_error(
    dmr_rf: DMRRequestFactory,
    status: HTTPStatus,
    error: type[Exception] | None,
) -> None:
    handler = build_4xx_handler(status)

    response = handler(dmr_rf.get("/"), Exception("boom"))  # ty: ignore[missing-argument]

    assert response.status_code == status

    payload: dict = loads(response.content)

    if error is not None:
        assert payload["detail"] == error.default_detail  # ty: ignore[unresolved-attribute]


def test_build_500_handler_reports_a_server_error(dmr_rf: DMRRequestFactory) -> None:
    handler = build_500_handler()
    response = handler(dmr_rf.get("/"))  # ty: ignore[missing-argument]

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
