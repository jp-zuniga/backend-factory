from typing import TYPE_CHECKING

from .base import ModelController
from .detail import (
    ModelDetailController,
    ModelManyToManyDetailController,
    ModelNestedDetailController,
    ModelReadOnlyDetailController,
    ModelReadUpdateDetailController,
)
from .list import (
    ModelListAllController,
    ModelListController,
    ModelManyToManyListController,
    ModelNestedListController,
    ModelReadOnlyListController,
)
from .scoped import (
    ScopedDetailController,
    ScopedListController,
    ScopedReadOnlyListController,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

########################################################################################

__all__: Sequence[str] = (
    "ModelController",
    "ModelDetailController",
    "ModelListAllController",
    "ModelListController",
    "ModelManyToManyDetailController",
    "ModelManyToManyListController",
    "ModelNestedDetailController",
    "ModelNestedListController",
    "ModelReadOnlyDetailController",
    "ModelReadOnlyListController",
    "ModelReadUpdateDetailController",
    "ScopedDetailController",
    "ScopedListController",
    "ScopedReadOnlyListController",
)
