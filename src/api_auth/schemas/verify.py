from api_auth.enums import TokenTypes
from api_core.schemas.base import DTO, PermissiveDTO
from api_core.schemas.get import LaxEnum

from .types import JwtToken

########################################################################################


class MobileVerifyPost(DTO):
    token: JwtToken

    # a json body carries the member's value, never the member itself
    type: LaxEnum[TokenTypes]


########################################################################################


class WebVerifyPost(PermissiveDTO):
    access: JwtToken | None = None
    refresh: JwtToken | None = None


########################################################################################


class WebVerifyResponse(DTO):
    access: bool
    refresh: bool
