from typing import TYPE_CHECKING

from dmr.routing import Router

from api_auth.controllers.csrf import CsrfController
from api_auth.controllers.email import EmailConfirmController, EmailResendController
from api_auth.controllers.group import (
    GroupDetailController,
    GroupListAllController,
    GroupListController,
)
from api_auth.controllers.login import MobileLoginController, WebLoginController
from api_auth.controllers.logout import MobileLogoutController, WebLogoutController
from api_auth.controllers.permission import (
    PermissionDetailController,
    PermissionListAllController,
    PermissionListController,
)
from api_auth.controllers.profile import ProfileController
from api_auth.controllers.refresh import MobileRefreshController, WebRefreshController
from api_auth.controllers.register import RegisterController
from api_auth.controllers.twofactor import (
    MobileTwoFactorController,
    TwoFactorConfirmController,
    TwoFactorController,
    TwoFactorDisableController,
    TwoFactorRecoveryController,
    TwoFactorSetupController,
    WebTwoFactorController,
)
from api_auth.controllers.user import (
    ApiUserDetailController,
    ApiUserGroupsController,
    ApiUserGroupsLinkController,
    ApiUserListAllController,
    ApiUserListController,
    ApiUserPermissionsController,
    ApiUserPermissionsLinkController,
)
from api_auth.controllers.verify import MobileVerifyController, WebVerifyController
from api_core.controllers.routers import (
    route_controllers,
    route_inferred_controller,
    route_link_controller,
)

if TYPE_CHECKING:
    from typing import Final

########################################################################################

router: Final[Router] = Router(
    prefix="",
    tags=["auth"],
    urls=(
        *route_controllers(
            ApiUserDetailController,
            ApiUserListController,
            ApiUserListAllController,
            CsrfController,
            EmailConfirmController,
            EmailResendController,
            GroupDetailController,
            GroupListController,
            GroupListAllController,
            MobileLoginController,
            MobileLogoutController,
            MobileRefreshController,
            MobileTwoFactorController,
            MobileVerifyController,
            PermissionDetailController,
            PermissionListController,
            PermissionListAllController,
            ProfileController,
            RegisterController,
            TwoFactorConfirmController,
            TwoFactorController,
            TwoFactorDisableController,
            TwoFactorRecoveryController,
            TwoFactorSetupController,
            WebLoginController,
            WebLogoutController,
            WebRefreshController,
            WebTwoFactorController,
            WebVerifyController,
            prefix="auth",
        ),
        route_inferred_controller(
            ctrl=ApiUserGroupsController,
            prefix="auth",
            suffix="groups",
            tail="groups",
        ),
        route_inferred_controller(
            ctrl=ApiUserPermissionsController,
            prefix="auth",
            suffix="permissions",
            tail="permissions",
        ),
        route_link_controller(ApiUserGroupsLinkController, "auth"),
        route_link_controller(ApiUserPermissionsLinkController, "auth"),
    ),
)
