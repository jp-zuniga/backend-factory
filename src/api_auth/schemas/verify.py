from typing import Annotated

from pydantic import Field

from api_auth.enums import TokenTypes
from api_core.schemas.base import DTO

from .types import JwtToken

########################################################################################


class MobileVerifyPost(DTO):
    token: JwtToken
    type: Annotated[TokenTypes, Field(strict=False)]


########################################################################################


class WebVerifyResponse(DTO):
    access: bool
    refresh: bool
