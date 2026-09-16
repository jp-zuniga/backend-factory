from typing import TYPE_CHECKING

from dmr.openapi import build_schema
from dmr.routing import Router

import api_auth.api

if TYPE_CHECKING:
    from typing import Final

    from dmr.openapi.openapi import OpenAPI

########################################################################################

router: Final[Router] = Router(prefix="")

# `Router.include` keeps each router's own tags, unlike splicing its urls
router.include(api_auth.api.router)

schema: Final[OpenAPI] = build_schema(router)
