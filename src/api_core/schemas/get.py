from uuid import UUID

from pydantic import PositiveInt

from .base import DTO

########################################################################################

type PrimaryKey = UUID | PositiveInt

########################################################################################


class BaseGet[PK: PrimaryKey = UUID](DTO):
    id: PK
