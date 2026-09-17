from api_core.schemas.base import DTO

from .types import Email, VerificationToken

########################################################################################


class EmailConfirmPost(DTO):
    token: VerificationToken


########################################################################################


class EmailResendPost(DTO):
    email: Email
