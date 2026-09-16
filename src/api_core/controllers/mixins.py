from collections.abc import Sequence
from http import HTTPMethod, HTTPStatus
from typing import TYPE_CHECKING, ClassVar, override

from django.db.models import QuerySet
from django.http import HttpResponse
from dmr import Controller
from dmr.negotiation import request_renderer
from dmr.response import build_response
from dmr.security import AsyncAuth
from dmr.throttling import AsyncThrottle, Rate

from api_auth.services.permissions import DEFAULT_PERMISSIONS
from api_core.services.relations import collect_fk_attnames
from api_exceptions.schemas import ApiErrorResponse

from .providers import HandleNotAllowedProvider, QuerySetProvider
from .throttles import build_throttle

if TYPE_CHECKING:
    from .models import ModelController

########################################################################################


class DefaultOrderMixin(QuerySetProvider):
    @override
    def build_qs(self) -> QuerySet:
        return super().build_qs().order_by("pk")


########################################################################################


class HandleNotAllowedMixin(HandleNotAllowedProvider):
    @override
    def handle_method_not_allowed(self, method: str) -> HttpResponse:
        # gracias convenciones de python por:
        if TYPE_CHECKING:
            assert isinstance(self, Controller)

        allowed = ", ".join(sorted(self.api_endpoints.keys()))

        return self._maybe_wrap(
            build_response(
                headers={"Allow": allowed},
                raw_data=ApiErrorResponse(
                    detail=f"Este controlador no procesa peticiones {method}.",
                    field_errors={"method": f"Métodos permitidos: {allowed}."},
                ),
                renderer=request_renderer(self.request),
                serializer=self.serializer,
                status_code=HTTPStatus.METHOD_NOT_ALLOWED,
            )
        )


########################################################################################


class ParentScopedMixin(QuerySetProvider):
    """
    Restrict a controller to the rows that hang off one parent row.

    `parent_field` names the foreign key that points at the parent.
    Everything else follows from it: the key's column (`parent_id`)
    is the url parameter, the path schema field, and the lookup, so
    the three can never drift apart.
    """

    parent_field: ClassVar[str]

    @classmethod
    def parent_param(cls) -> str:
        if TYPE_CHECKING:
            assert issubclass(cls, ModelController)

        attnames: dict[str, str] = collect_fk_attnames(cls.model)

        field: str | None = getattr(cls, "parent_field", None)

        if field not in attnames:
            raise TypeError(
                f"{cls.__name__}.parent_field debe nombrar una llave foránea "
                f"de {cls.model.__name__}, no {field!r}.",
            )

        return attnames[field]

    @property
    def parent_id(self) -> str:
        return self.kwargs[self.parent_param()]  # ty: ignore[unresolved-attribute]

    @override
    def build_qs(self) -> QuerySet:
        scope: dict = {self.parent_field: self.parent_id}

        return super().build_qs().filter(**scope)


########################################################################################


class PublicControllerMixin:
    auth: ClassVar[Sequence[AsyncAuth] | None] = None


########################################################################################


class StrictThrottlingMixin:
    throttling: ClassVar[Sequence[AsyncThrottle]] = (build_throttle(10, Rate.minute),)


########################################################################################


class OpenReadMixin:
    """
    Let any authenticated client read; writes still need permissions.
    """

    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = DEFAULT_PERMISSIONS | {
        HTTPMethod.GET: (),
    }


########################################################################################


class OpenCreateMixin(OpenReadMixin):
    """
    Let any authenticated client read and create; edits still need permissions.
    """

    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = (
        OpenReadMixin.permissions
        | {
            HTTPMethod.POST: (),
        }
    )


########################################################################################


class ReadOnlyMixin:
    """
    Answer reads to any authenticated client and refuse every other method.
    """

    permissions: ClassVar[dict[HTTPMethod, Sequence[str]]] = {HTTPMethod.GET: ()}
