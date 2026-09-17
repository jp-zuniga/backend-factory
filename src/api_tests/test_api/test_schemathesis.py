import hypothesis as ht
import pytest
import schemathesis

from pytest_django import Settings as PytestDjangoSettings
from pytest_django.live_server_helper import LiveServer
from schemathesis.checks import not_a_server_error
from schemathesis.config import (
    GenerationConfig,
    ProjectConfig,
    ProjectsConfig,
    SchemathesisConfig,
)
from schemathesis.generation import GenerationMode
from tracecov import CoverageMap
from tracecov.schemathesis import from_response

from api_auth.services.jwt import EncodedJwtPair

########################################################################################

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


@pytest.fixture(scope="session")
def schemathesis_schema(openapi_document: dict) -> schemathesis.BaseSchema:
    config = SchemathesisConfig(
        projects=ProjectsConfig(
            default=ProjectConfig(
                generation=GenerationConfig(
                    modes=[GenerationMode.POSITIVE, GenerationMode.NEGATIVE],
                ),
            ),
        ),
    )

    return schemathesis.openapi.from_dict(openapi_document, config=config)


########################################################################################

schema = schemathesis.pytest.from_fixture("schemathesis_schema")

########################################################################################


@pytest.fixture(autouse=True)
def live_server_static_url(settings: PytestDjangoSettings) -> None:
    # gracias django por:
    settings.STATIC_URL = "/static/"


########################################################################################


@schema.parametrize()
@ht.settings(
    deadline=None,
    max_examples=20,
    suppress_health_check=(
        ht.HealthCheck.function_scoped_fixture,
        ht.HealthCheck.too_slow,
    ),
)
def test_api_surface_never_crashes(
    case: schemathesis.Case,
    live_server: LiveServer,
    superuser_tokens: EncodedJwtPair,
    tracecov_map: CoverageMap | None,
) -> None:
    response = case.call(
        base_url=live_server.url,
        headers={"Authorization": f"Bearer {superuser_tokens.access}"},
    )

    if tracecov_map is not None:
        tracecov_map.record_schemathesis_interactions(
            case.method,
            case.operation.full_path,
            [from_response(case.method, response)],
        )

    case.validate_response(response, checks=[not_a_server_error])  # ty: ignore[invalid-argument-type]
