from collections.abc import Mapping
from datetime import timedelta
from http import HTTPStatus
from time import sleep

import pytest

from django.contrib.auth.models import Group
from dmr.test import DMRClient

from api_auth.enums import ApiUserTypes, VerificationPurposes
from api_auth.models import ApiUser
from api_auth.services.verification import LIFETIMES
from api_tests.conftest import PASSWORD
from api_tests.helpers import PatchedHttpResponse, assert_field_error, route

########################################################################################

pytestmark = pytest.mark.django_db

########################################################################################


@pytest.fixture
def sent_mail(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    captured: list[dict] = []

    async def fake_send_template(  # ruff: ignore[unused-async]
        *,
        purpose: VerificationPurposes,
        context: Mapping[str, object],
        to: str,
    ) -> None:
        captured.append({"context": context, "purpose": purpose, "to": to})

    monkeypatch.setattr(
        "api_auth.services.verification.send_template",
        fake_send_template,
    )

    return captured


@pytest.fixture
def inactive_unverified_user(seeded_groups: dict[str, Group]) -> ApiUser:
    user: ApiUser = ApiUser.objects.create_user(
        email="dormant@unit.example.com",
        is_active=False,
        password=PASSWORD,
        username="dormant",
    )

    user.groups.add(seeded_groups[ApiUserTypes.CLIENT.value])  # ty: ignore[unresolved-attribute]

    return user


########################################################################################


def test_email_resend_issues_a_code_for_an_unverified_user(
    dmr_client: DMRClient,
    unverified_user: ApiUser,
    sent_mail: list[dict],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": unverified_user.email},
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.content == b""

    assert len(sent_mail) == 1
    assert sent_mail[0]["to"] == unverified_user.email
    assert sent_mail[0]["purpose"] == VerificationPurposes.EMAIL
    assert sent_mail[0]["context"]["token"]


def test_email_resend_is_silent_for_a_verified_user(
    dmr_client: DMRClient,
    client_user: ApiUser,
    sent_mail: list[dict],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": client_user.email},
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert sent_mail == []


def test_email_resend_is_silent_for_an_unknown_address(
    dmr_client: DMRClient,
    db: None,
    sent_mail: list[dict],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": "nadie@unit.example.com"},
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert sent_mail == []


def test_email_resend_is_silent_for_an_inactive_user(
    dmr_client: DMRClient,
    inactive_unverified_user: ApiUser,
    sent_mail: list[dict],
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": inactive_unverified_user.email},
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert sent_mail == []


def test_email_resend_invalidates_the_previous_code(
    dmr_client: DMRClient,
    unverified_user: ApiUser,
    sent_mail: list[dict],
) -> None:
    first: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": unverified_user.email},
    )
    second: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": unverified_user.email},
    )

    assert first.status_code == HTTPStatus.ACCEPTED
    assert second.status_code == HTTPStatus.ACCEPTED
    assert len(sent_mail) == 2

    stale: str = sent_mail[0]["context"]["token"]

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-confirm"),
        data={"token": stale},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.token")


########################################################################################


def test_email_confirm_verifies_the_account(
    dmr_client: DMRClient,
    unverified_user: ApiUser,
    sent_mail: list[dict],
) -> None:
    resend: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": unverified_user.email},
    )

    assert resend.status_code == HTTPStatus.ACCEPTED

    token: str = sent_mail[0]["context"]["token"]

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-confirm"),
        data={"token": token},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT

    unverified_user.refresh_from_db()

    assert unverified_user.email_verified_at is not None


def test_email_confirm_rejects_a_reused_token(
    dmr_client: DMRClient,
    unverified_user: ApiUser,
    sent_mail: list[dict],
) -> None:
    resend: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": unverified_user.email},
    )

    assert resend.status_code == HTTPStatus.ACCEPTED

    token: str = sent_mail[0]["context"]["token"]

    dmr_client.post(route("auth-email-confirm"), data={"token": token})

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-confirm"),
        data={"token": token},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.token")


def test_email_confirm_rejects_an_unknown_token(
    dmr_client: DMRClient,
    db: None,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-confirm"),
        data={"token": "a" * 32},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.token")


def test_email_confirm_rejects_a_malformed_token(
    dmr_client: DMRClient,
    db: None,
) -> None:
    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-confirm"),
        data={"token": "too-short"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.token")


def test_email_confirm_rejects_an_expired_code(
    dmr_client: DMRClient,
    unverified_user: ApiUser,
    sent_mail: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `expires_at` is read-only once a code exists, so the only way to
    # produce an expired one is to shrink its lifetime before issuing it
    monkeypatch.setitem(
        LIFETIMES,
        VerificationPurposes.EMAIL,
        timedelta(milliseconds=1),
    )

    resend: PatchedHttpResponse = dmr_client.post(
        route("auth-email-resend"),
        data={"email": unverified_user.email},
    )

    assert resend.status_code == HTTPStatus.ACCEPTED

    token: str = sent_mail[0]["context"]["token"]

    sleep(0.2)

    response: PatchedHttpResponse = dmr_client.post(
        route("auth-email-confirm"),
        data={"token": token},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_field_error(response, "body.token")
