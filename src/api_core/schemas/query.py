from .base import DTO

########################################################################################


class UpdateManyToManyQuery(DTO):
    overwrite: bool


########################################################################################


class PatchManyToManyQuery(UpdateManyToManyQuery):
    overwrite: bool = False


########################################################################################


class PutManyToManyQuery(UpdateManyToManyQuery):
    overwrite: bool = True
