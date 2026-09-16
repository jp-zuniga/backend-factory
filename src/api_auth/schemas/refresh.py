from api_auth.schemas.types import JwtToken
from api_core.schemas.base import DTO

########################################################################################


class MobileRefreshPost(DTO):
    refresh: JwtToken


########################################################################################


class MobileRefreshResponse(DTO):
    access: str
    refresh: str
