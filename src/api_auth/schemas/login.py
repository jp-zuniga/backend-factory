from api_core.schemas.base import DTO

from .types import Password, Username
from .user import ApiUserInlineGet

########################################################################################


class LoginInput(DTO):
    username: Username
    password: Password


########################################################################################


class MobileLoginPost(LoginInput):
    pass


########################################################################################


class MobileLoginResponse(DTO):
    access: str
    refresh: str
    user: ApiUserInlineGet


########################################################################################


class WebLoginPost(LoginInput):
    pass


########################################################################################


class WebLoginResponse(DTO):
    user: ApiUserInlineGet
