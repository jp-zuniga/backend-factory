from collections.abc import Sequence
from typing import TYPE_CHECKING

from django.db.models import Field, IntegerField, UUIDField
from django.urls import URLPattern, URLResolver
from dmr.routing import path

from api_core.controllers.base import BaseController
from api_core.controllers.mixins import ParentScopedMixin
from api_core.controllers.models.link import ModelLinkController
from api_utils.strings import camel_to_kebab
from api_utils.types import DatabaseModel

from .models import (
    ModelController,
    ModelDetailController,
    ModelListAllController,
    ModelListController,
    ModelReadOnlyDetailController,
    ModelReadOnlyListController,
    ModelReadUpdateDetailController,
)

########################################################################################

type URL = URLPattern | URLResolver

########################################################################################


def get_controller_endpoint(ctrl: type[BaseController]) -> str:
    resource: str = ctrl.__name__.removesuffix("Controller").removeprefix(ctrl.variant)

    return join_route(ctrl.namespace, camel_to_kebab(s=resource))


########################################################################################


def get_model_endpoint(ctrl: type[ModelController]) -> str:
    resource: str = ctrl.model.__name__.removeprefix("Api")

    return join_route(ctrl.namespace, camel_to_kebab(s=resource))


########################################################################################


def get_parent_model(ctrl: type[ParentScopedMixin]) -> type[DatabaseModel]:
    if TYPE_CHECKING:
        assert issubclass(ctrl, ModelController)

    field: Field = ctrl.model._meta.get_field(ctrl.parent_field)

    return field.related_model  # ty: ignore[invalid-return-type]


########################################################################################


def get_resource_name(model: type[DatabaseModel]) -> str:
    return camel_to_kebab(s=model.__name__.removeprefix("Api"))


########################################################################################


def get_pk_type(model: type[DatabaseModel]) -> str:
    pk: Field = model._meta.pk  # ty: ignore[invalid-assignment]

    if isinstance(pk, IntegerField):
        return "int"
    if isinstance(pk, UUIDField):
        return "uuid"

    return "str"


########################################################################################


def join_route(*parts: str) -> str:
    return "/".join(part for part in (raw.strip("/") for raw in parts) if part)


########################################################################################


def route_controller(  # ruff: ignore[too-many-arguments]
    *,
    ctrl: type[BaseController],
    endpoint: str | None = None,
    instance_param: tuple[str, str] | None = None,
    related_param: tuple[str, str] | None = None,
    suffix: str | None = None,
    tail: str | None = None,
) -> URL:
    normalized: str = join_route(endpoint or get_controller_endpoint(ctrl))

    name: str = normalized.replace("/", "-")

    if suffix is not None:
        name += f"-{suffix}"

    route: str = f"{normalized}/"

    if instance_param is not None:
        route += f"<{instance_param[0]}:{instance_param[1]}>/"

    if tail is not None:
        route += f"{join_route(tail)}/"

    if related_param:
        route += f"<{related_param[0]}:{related_param[1]}>/"

    return path(name=name, route=route, view=ctrl.as_view())


########################################################################################


def route_controllers(
    *ctrls: type[BaseController],
    prefix: str = "",
) -> Sequence[URL]:
    return tuple(route_inferred_controller(ctrl, prefix) for ctrl in ctrls)


########################################################################################


def route_inferred_controller(
    ctrl: type[BaseController],
    prefix: str,
    **kwargs: str | tuple[str, str] | None,
) -> URL:
    if issubclass(ctrl, ParentScopedMixin):
        return route_scoped_controller(ctrl=ctrl, prefix=prefix, **kwargs)  # ty: ignore[invalid-argument-type]

    if issubclass(
        ctrl,
        (
            ModelDetailController,
            ModelReadOnlyDetailController,
            ModelReadUpdateDetailController,
        ),
    ):
        kwargs["suffix"] = (
            f"detail-{kwargs['suffix']}" if "suffix" in kwargs else "detail"
        )

        return route_controller(
            ctrl=ctrl,
            endpoint=join_route(prefix, get_model_endpoint(ctrl)),
            instance_param=(get_pk_type(ctrl.model), "id"),
            **kwargs,  # ty: ignore[invalid-argument-type]
        )

    if issubclass(ctrl, ModelListAllController):
        return route_controller(
            ctrl=ctrl,
            endpoint=join_route(prefix, get_model_endpoint(ctrl), "all"),
            **kwargs,  # ty: ignore[invalid-argument-type]
        )

    if issubclass(ctrl, (ModelListController, ModelReadOnlyListController)):
        kwargs["suffix"] = f"list-{kwargs['suffix']}" if "suffix" in kwargs else "list"

        return route_controller(
            ctrl=ctrl,
            endpoint=join_route(prefix, get_model_endpoint(ctrl)),
            **kwargs,  # ty: ignore[invalid-argument-type]
        )

    return route_controller(
        ctrl=ctrl,
        endpoint=join_route(prefix, get_controller_endpoint(ctrl)),
        **kwargs,  # ty: ignore[invalid-argument-type]
    )


########################################################################################


def route_scoped_controller(
    *,
    ctrl: type[ParentScopedMixin],
    endpoint: str | None = None,
    prefix: str = "",
    suffix: str | None = None,
    tail: str | None = None,
) -> URL:
    """
    Route a sub-resource underneath its parent's endpoint.

    Every part of `parent/<parent_id>/children/<id>/` is read off
    the controller: the parent's endpoint and key type come from
    the relation named by `parent_field`, and the tail comes from
    the sub-resource's own model.

    Args:
        ctrl: The scoped controller to route.
        endpoint: The parent's endpoint, when it is not the parent
            model's own name.
        prefix: Path segments every route in the router shares.
        suffix: An explicit url name suffix.
        tail: The sub-resource's path segment, when it is not the
            child model's own name.

    Returns:
        The url pattern the controller answers on.

    """

    if TYPE_CHECKING:
        assert issubclass(ctrl, ModelController)

    parent: type[DatabaseModel] = get_parent_model(ctrl)

    detail: bool = issubclass(
        ctrl,
        (
            ModelDetailController,
            ModelReadOnlyDetailController,
            ModelReadUpdateDetailController,
        ),
    )

    segment: str = tail or get_resource_name(ctrl.model)

    return route_controller(
        ctrl=ctrl,
        endpoint=join_route(prefix, endpoint or get_resource_name(parent)),
        instance_param=(get_pk_type(parent), ctrl.parent_param()),
        related_param=((get_pk_type(ctrl.model), "id") if detail else None),
        suffix=suffix or f"{segment}-{'detail' if detail else 'list'}",
        tail=segment,
    )


########################################################################################


def route_link_controller(
    ctrl: type[ModelLinkController],
    prefix: str = "",
) -> URL:
    parent: type[DatabaseModel] = ctrl.parent_model()

    resource: str = parent.__name__.removeprefix("Api")

    return route_controller(
        ctrl=ctrl,
        endpoint=join_route(prefix, ctrl.namespace, camel_to_kebab(s=resource)),
        instance_param=(get_pk_type(parent), "id"),
        related_param=(get_pk_type(ctrl.related_model()), "related"),
        suffix=f"{ctrl.relation}-link",
        tail=ctrl.relation,
    )


########################################################################################


def sort_urls(urls: Sequence[URL]) -> Sequence[URL]:
    return sorted(urls, key=(lambda u: str(u.pattern)))
