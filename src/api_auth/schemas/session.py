from api_core.schemas.base import PermissiveDTO

from .types import JwtToken

########################################################################################


# a browser sends every cookie it holds, not just these two, so unknown
# ones are ignored instead of failing the request
class SessionCookies(PermissiveDTO):
    access: JwtToken | None = None
    refresh: JwtToken | None = None
