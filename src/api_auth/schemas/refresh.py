from pydantic import ConfigDict

from api_auth.schemas.types import JwtToken
from api_core.schemas.base import DTO, PermissiveDTO

########################################################################################


class RefreshInput(DTO):
    access: JwtToken | None = None
    refresh: JwtToken


########################################################################################


class MobileRefreshPost(RefreshInput):
    pass


########################################################################################


class MobileRefreshResponse(DTO):
    access: str
    refresh: str


########################################################################################


class WebRefreshPost(PermissiveDTO, RefreshInput):
    # see `WebLogoutPost`: cookies arrive with company
    model_config = ConfigDict(extra="ignore")

    refresh: JwtToken | None = None
