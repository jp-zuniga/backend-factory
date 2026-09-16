from pydantic import ConfigDict

from api_core.schemas.base import DTO, PermissiveDTO

from .types import JwtToken

########################################################################################

type LogoutPost = MobileLogoutPost | WebLogoutPost

########################################################################################


class LogoutInput(DTO):
    access: JwtToken | None = None
    refresh: JwtToken | None = None


########################################################################################


class MobileLogoutPost(LogoutInput):
    pass


########################################################################################


class WebLogoutPost(PermissiveDTO, LogoutInput):
    # a browser sends every cookie it holds, not just these two;
    # pydantic resolves `extra` from the last base, so it is spelled
    # out here instead of riding on the order of the bases above
    model_config = ConfigDict(extra="ignore")
