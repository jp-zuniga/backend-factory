from collections.abc import Iterable
from functools import cache, cached_property
from types import UnionType
from typing import TYPE_CHECKING, get_args, get_origin, override

from django.core.exceptions import FieldDoesNotExist
from django.db.models import NOT_PROVIDED, Prefetch

from api_core.controllers.providers import QuerySetProvider
from api_core.schemas.base import DTO
from api_core.schemas.get import BaseGet

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

    from django.db.models import (
        ForeignObjectRel,
        ManyToManyField,
        ManyToOneRel,
        OneToOneRel,
        QuerySet,
    )

    from api_utils.types import DatabaseModel


########################################################################################

MAX_PREFETCH_DEPTH: Final[int] = 3

########################################################################################


class RelationResolver[
    Model: DatabaseModel,
    Get: DTO,
](QuerySetProvider):
    def __init__(
        self,
        *,
        max_prefetch_depth: int = MAX_PREFETCH_DEPTH,
        model: type[Model],
        schema: type[Get],
    ) -> None:
        self.model: type[Model] = model
        self.schema: type[Get] = schema
        self.max_prefetch_depth: int = max_prefetch_depth

    @classmethod
    def build(
        cls,
        model: type[Model],
        schema: type[Get],
    ) -> RelationResolver[Model, Get]:
        return cls(model=model, schema=schema)

    @cached_property
    def fk_paths(self) -> frozenset[str]:
        return collect_fk_paths(self.schema)

    @cached_property
    def m2m_names(self) -> frozenset[str]:
        return collect_m2m_names(self.schema)

    @cached_property
    def nested_names(self) -> frozenset[str]:
        return collect_nested_relations(self.model)

    @cached_property
    def prefetches(self) -> frozenset[Prefetch | str]:
        return frozenset(
            build_prefetch(
                max_depth=self.max_prefetch_depth,
                model=self.model,
                name=name,
                schema=self.schema,
            )
            for name in self.m2m_names
        )

    @override
    def build_qs(self) -> QuerySet:
        qs: QuerySet = self.model._default_manager.all()

        if self.prefetches:
            qs: QuerySet = qs.prefetch_related(*self.prefetches)
        if self.fk_paths:
            qs: QuerySet = qs.select_related(*self.fk_paths)

        return qs


########################################################################################


@cache
def build_prefetch(  # ruff: ignore[too-many-arguments]
    *,
    depth: int = 0,
    max_depth: int = MAX_PREFETCH_DEPTH,
    model: type[DatabaseModel],
    name: str,
    seen: frozenset[tuple[type, type]] = frozenset(),
    schema: type[DTO],
) -> Prefetch | str:
    inner: type | None = unwrap_list_annotation(
        schema.model_fields[name].annotation,
    )

    if inner is None or not issubclass(inner, DTO):
        return name

    rel: ManyToManyField | ForeignObjectRel | None = resolve_collection(model, name)

    if rel is None:
        return name

    related: type[DatabaseModel] = rel.related_model

    if depth >= max_depth or (related, inner) in seen:
        return name

    nested: frozenset[tuple[type, type]] = seen | {(related, inner)}

    paths: frozenset[str] = collect_fk_paths(inner)

    children: Sequence[Prefetch | str] = tuple(
        build_prefetch(
            max_depth=max_depth,
            model=related,
            name=child,
            schema=inner,
            depth=(depth + 1),
            seen=nested,
        )
        for child in sorted(collect_m2m_names(inner))
    )

    if not paths and not children:
        return name

    qs: QuerySet = related._default_manager.all()

    if children:
        qs: QuerySet = qs.prefetch_related(*children)
    if paths:
        qs: QuerySet = qs.select_related(*sorted(paths))

    return Prefetch(lookup=name, queryset=qs)


########################################################################################


@cache
def collect_fk_paths(
    schema: type[DTO],
    prefix: str | None = None,
    seen: frozenset[type] = frozenset(),
) -> frozenset[str]:
    if schema in seen:
        return frozenset()

    nested: frozenset[type] = seen | {schema}

    paths: set[str] = set()

    for name, field_info in schema.model_fields.items():
        inner = unwrap_annotation(field_info.annotation)

        if inner is None or not isinstance(inner, type) or not issubclass(inner, DTO):
            continue

        full: str = f"{prefix}__{name}" if prefix is not None else name

        paths.add(full)

        paths |= collect_fk_paths(inner, full, nested)

    return frozenset(paths)


########################################################################################


@cache
def collect_m2m_names(schema: type[DTO]) -> frozenset[str]:
    return frozenset(
        name
        for name, field_info in schema.model_fields.items()
        if (inner := unwrap_list_annotation(field_info.annotation)) is not None
        and isinstance(inner, type)
        and issubclass(inner, BaseGet)
    )


########################################################################################


@cache
def collect_nested_relations(model: type[DatabaseModel]) -> frozenset[str]:
    return frozenset(
        name
        for rel in model._meta.related_objects
        if (rel.one_to_one or rel.one_to_many)
        and (name := rel.get_accessor_name()) is not None
    )


########################################################################################


@cache
def collect_fk_attnames(model: type[DatabaseModel]) -> dict[str, str]:
    """
    Map every foreign key's field name to the column it writes.

    Args:
        model: The model to inspect.

    Returns:
        Pairs of `("parent", "parent_id")`, one per concrete relation.

    """

    return {
        str(field.name): str(field.attname)
        for field in model._meta.concrete_fields
        if field.is_relation
    }


########################################################################################


def resolve_fk_attnames(data: dict, model: type[DatabaseModel]) -> dict:
    """
    Rewrite a payload so that foreign keys are assigned by id.

    A schema names a relation the way the API exposes it (`parent`),
    while a bare `QuerySet.create()` or `update()` call needs the
    column behind it (`parent_id`) to accept a raw key.

    Args:
        data: The payload dumped from a schema.
        model: The model the payload is written to.

    Returns:
        The same payload, keyed by column names.

    """

    attnames: dict[str, str] = collect_fk_attnames(model)

    return {attnames.get(name, name): value for name, value in data.items()}


########################################################################################


@cache
def collect_unique_fields(model: type[DatabaseModel]) -> frozenset[str]:
    return frozenset(
        str(field.name)
        for field in model._meta.get_fields()
        if getattr(field, "unique", False) and not getattr(field, "primary_key", False)
    )


########################################################################################


@cache
def resolve_collection(
    model: type[DatabaseModel],
    name: str,
) -> ManyToManyField | ForeignObjectRel | None:
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return None

    if not field.is_relation:
        return None

    if not field.many_to_many and not field.one_to_many:
        return None

    if field.related_model is None:
        return None

    return field


########################################################################################


@cache
def resolve_nested_relation(
    model: type[DatabaseModel],
    name: str,
) -> ManyToOneRel | OneToOneRel | None:
    for rel in model._meta.related_objects:
        if (rel.one_to_one or rel.one_to_many) and rel.get_accessor_name() == name:
            return rel

    return None


########################################################################################


@cache
def supports_copy(model: type[DatabaseModel]) -> bool:
    return not any(
        field.db_default is not NOT_PROVIDED and field.default is NOT_PROVIDED
        for field in model._meta.concrete_fields
    )


########################################################################################


@cache
def unwrap_annotation[T](annotation: type[T]) -> type | None:
    if isinstance(annotation, type):
        return annotation

    if get_origin(annotation) is UnionType:
        args: Sequence[tuple] = tuple(
            filter(
                lambda a: a is not type(None),
                get_args(annotation),
            )
        )

        if len(args) == 1 and isinstance(args[0], type):
            return args[0]

    return None


########################################################################################


@cache
def unwrap_list_annotation[T](annotation: type[T]) -> type | None:
    if get_origin(tp=annotation) is UnionType:
        args: Sequence[tuple] = tuple(
            filter(
                lambda a: a is not type(None),
                get_args(tp=annotation),
            )
        )

        if len(args) != 1:
            return None

        annotation = args[0]

    origin: type | None = get_origin(tp=annotation)

    if origin is not None and isinstance(origin, type) and issubclass(origin, Iterable):
        args: tuple = get_args(tp=annotation)

        if len(args) >= 1 and isinstance(args[0], type):
            return args[0]

    return None
