from http import HTTPStatus

from django.views.decorators.debug import sensitive_variables
from dmr import Body, modify

from api_auth.schemas.verification import EmailConfirmPost, EmailResendPost
from api_auth.services.account import confirm_email, resend_verification
from api_core.controllers.serializers import CustomPydanticFastSerializer

from .base import AuthController

########################################################################################


class EmailConfirmController(AuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.NO_CONTENT)
    @sensitive_variables()
    async def post(self, parsed_body: Body[EmailConfirmPost]) -> None:  # ruff: ignore[no-self-use]
        await confirm_email(parsed_body.token)


########################################################################################


class EmailResendController(AuthController[CustomPydanticFastSerializer]):
    @modify(status_code=HTTPStatus.ACCEPTED)
    async def post(self, parsed_body: Body[EmailResendPost]) -> None:  # ruff: ignore[no-self-use]
        await resend_verification(parsed_body.email)
