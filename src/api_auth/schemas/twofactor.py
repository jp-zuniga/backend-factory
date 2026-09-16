from datetime import datetime

from pydantic import NonNegativeInt, PositiveInt

from api_core.schemas.base import DTO, PermissiveDTO

from .types import JwtToken, Password, TwoFactorCode

########################################################################################


class TwoFactorStatusGet(DTO):
    confirmed_at: datetime | None
    enabled: bool
    pending: bool
    recovery_codes: NonNegativeInt


########################################################################################


class TwoFactorSetupResponse(DTO):
    secret: str
    uri: str


########################################################################################


class TwoFactorRecoveryResponse(DTO):
    codes: tuple[str, ...]


########################################################################################


class TwoFactorCodePost(DTO):
    code: TwoFactorCode


########################################################################################


class TwoFactorDisablePost(TwoFactorCodePost):
    password: Password


########################################################################################


class MobileTwoFactorPost(TwoFactorCodePost):
    challenge: JwtToken


########################################################################################


class WebTwoFactorPost(TwoFactorCodePost):
    pass


########################################################################################


class WebChallengeCookies(PermissiveDTO):
    challenge: JwtToken | None = None


########################################################################################


class MobileChallengeResponse(DTO):
    challenge: str
    expires_in: PositiveInt


########################################################################################


class WebChallengeResponse(DTO):
    expires_in: PositiveInt
