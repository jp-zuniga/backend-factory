from api_core.schemas.base import DTO

from .types import RequiredEmail, VerificationToken

########################################################################################


class EmailConfirmPost(DTO):
    token: VerificationToken


########################################################################################


class EmailResendPost(DTO):
    email: RequiredEmail
