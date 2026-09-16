from api_core.schemas.base import DTO

from .types import JwtToken

########################################################################################


# both tokens are optional: either one names the whole session, so sending
# the one still at hand is enough to revoke the pair
class MobileLogoutPost(DTO):
    access: JwtToken | None = None
    refresh: JwtToken | None = None
