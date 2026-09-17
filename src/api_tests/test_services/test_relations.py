from typing import Annotated

import pytest

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch
from pydantic import Field, PositiveInt

from api_auth.models import ApiUser, ApiUserGroups
from api_auth.schemas.group import GroupGet, GroupInlineGet
from api_auth.schemas.permission import PermissionGet
from api_auth.schemas.through import ApiUserGroupsLinkGet, ApiUserPermissionsLinkGet
from api_auth.schemas.user import (
    ApiUserGet,
    ApiUserGroupsGet,
    ApiUserGroupsWrite,
    ApiUserInlineGet,
)
from api_core.schemas.get import BaseGet
from api_core.services.relations import (
    MAX_PREFETCH_DEPTH,
    RelationResolver,
    build_prefetch,
    collect_fk_paths,
    collect_m2m_names,
    collect_nested_relations,
    collect_unique_fields,
    resolve_collection,
    resolve_nested_relation,
    supports_copy,
    unwrap_annotation,
    unwrap_list_annotation,
)

pytestmark = pytest.mark.django_db

########################################################################################


class _AliasedGet(BaseGet[PositiveInt]):
    nested: Annotated[GroupInlineGet, Field(exclude=True)]


########################################################################################


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (int, int),
        (str, str),
        (GroupInlineGet, GroupInlineGet),
        (int | None, int),
        (GroupInlineGet | None, GroupInlineGet),
        (int | str, None),
        (list[int], None),
        (list[GroupInlineGet], None),
    ],
)
def test_unwrap_annotation(annotation: type, expected: type | None) -> None:
    assert unwrap_annotation(annotation) is expected


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (list[GroupInlineGet], GroupInlineGet),
        (list[GroupInlineGet] | None, GroupInlineGet),
        (list[int], int),
        (set[str], str),
        (tuple[PermissionGet], PermissionGet),
        (dict[str, int], str),
        (int, None),
        (GroupInlineGet, None),
        (int | str, None),
    ],
)
def test_unwrap_list_annotation(annotation: type, expected: type | None) -> None:
    assert unwrap_list_annotation(annotation) is expected


########################################################################################


def test_collect_m2m_names_finds_nested_collections() -> None:
    assert collect_m2m_names(ApiUserGet) == frozenset({"groups", "permissions"})
    assert collect_m2m_names(GroupGet) == frozenset({"permissions"})
    assert collect_m2m_names(ApiUserGroupsGet) == frozenset({"groups"})


def test_collect_m2m_names_ignores_flat_schemas() -> None:
    assert collect_m2m_names(ApiUserInlineGet) == frozenset()
    assert collect_m2m_names(GroupInlineGet) == frozenset()


def test_collect_m2m_names_ignores_scalar_collections() -> None:
    assert collect_m2m_names(ApiUserGroupsWrite) == frozenset()


########################################################################################


def test_collect_fk_paths_walks_single_relations() -> None:
    assert collect_fk_paths(PermissionGet) == frozenset({"content_type"})
    assert collect_fk_paths(ApiUserGroupsLinkGet) == frozenset({"api_user", "group"})


def test_collect_fk_paths_builds_dotted_paths() -> None:
    assert collect_fk_paths(ApiUserPermissionsLinkGet) == frozenset({
        "api_user",
        "permission",
        "permission__content_type",
    })


def test_collect_fk_paths_ignores_collections() -> None:
    assert collect_fk_paths(ApiUserGet) == frozenset()
    assert collect_fk_paths(ApiUserInlineGet) == frozenset()


def test_collect_fk_paths_respects_annotated_metadata() -> None:
    assert collect_fk_paths(_AliasedGet) == frozenset({"nested"})


def test_collect_fk_paths_uses_prefix() -> None:
    assert collect_fk_paths(PermissionGet, "permission") == frozenset({
        "permission__content_type",
    })


########################################################################################


def test_collect_nested_relations_finds_reverse_foreign_keys() -> None:
    assert "permission_set" in collect_nested_relations(ContentType)
    assert "blocklistedjwtoken_set" in collect_nested_relations(ApiUser)


def test_collect_nested_relations_skips_suppressed_accessors() -> None:
    nested: frozenset[str] = collect_nested_relations(ApiUser)

    assert not any(name.startswith("apiusergroups") for name in nested)
    assert "groups" not in nested


def test_collect_nested_relations_skips_many_to_many() -> None:
    assert "users" not in collect_nested_relations(Group)


########################################################################################


def test_collect_unique_fields_skips_primary_key() -> None:
    unique: frozenset[str] = collect_unique_fields(Group)

    assert "name" in unique
    assert "id" not in unique


def test_collect_unique_fields_on_through_model() -> None:
    assert "id" not in collect_unique_fields(ApiUserGroups)


########################################################################################


def test_resolve_collection_forward_many_to_many() -> None:
    field = resolve_collection(ApiUser, "groups")

    assert field is not None
    assert field.related_model is Group


def test_resolve_collection_reverse_many_to_many() -> None:
    field = resolve_collection(Group, "users")

    assert field is not None
    assert field.related_model is ApiUser


def test_resolve_collection_reverse_foreign_key() -> None:
    field = resolve_collection(ContentType, "permission")

    assert field is not None
    assert field.related_model is Permission


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (ApiUser, "username"),
        (ApiUser, "campo_inexistente"),
        (ApiUserGroups, "api_user"),
        (Permission, "content_type"),
    ],
)
def test_resolve_collection_rejects_non_collections(model: type, name: str) -> None:
    assert resolve_collection(model, name) is None


########################################################################################


def test_resolve_nested_relation_matches_accessor() -> None:
    rel = resolve_nested_relation(ContentType, "permission_set")

    assert rel is not None
    assert rel.related_model is Permission
    assert rel.field.name == "content_type"


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (ApiUser, "groups"),
        (ContentType, "permission"),
        (Group, "accesor_inexistente"),
    ],
)
def test_resolve_nested_relation_rejects_unknown(model: type, name: str) -> None:
    assert resolve_nested_relation(model, name) is None


########################################################################################


def test_supports_copy_for_models_without_bare_db_defaults() -> None:
    assert supports_copy(Permission) is True
    assert supports_copy(Group) is True


def test_supports_copy_for_models_with_paired_defaults() -> None:
    assert supports_copy(ApiUser) is True
    assert supports_copy(ApiUserGroups) is True


########################################################################################


def test_build_prefetch_returns_name_for_leaf_schemas() -> None:
    assert build_prefetch(model=ApiUser, name="groups", schema=ApiUserGet) == "groups"


def test_build_prefetch_returns_name_for_scalar_collections() -> None:
    built = build_prefetch(model=ApiUser, name="groups", schema=ApiUserGroupsWrite)

    assert built == "groups"


def test_build_prefetch_returns_prefetch_when_child_has_relations() -> None:
    built = build_prefetch(model=ApiUser, name="permissions", schema=ApiUserGet)

    assert isinstance(built, Prefetch)
    assert built.prefetch_to == "permissions"
    assert built.queryset is not None
    assert built.queryset.query.select_related == {"content_type": {}}


def test_build_prefetch_nests_grandchildren() -> None:
    built = build_prefetch(model=ApiUser, name="groups", schema=_GroupsWithPermissions)

    assert isinstance(built, Prefetch)
    assert built.queryset is not None
    assert built.queryset._prefetch_related_lookups  # ruff: ignore[private-member-access]


def test_build_prefetch_stops_at_max_depth() -> None:
    built = build_prefetch(
        depth=MAX_PREFETCH_DEPTH,
        model=ApiUser,
        name="permissions",
        schema=ApiUserGet,
    )

    assert built == "permissions"


def test_build_prefetch_returns_name_for_unknown_field() -> None:
    built = build_prefetch(model=Group, name="permissions", schema=_MislabeledGet)

    assert built == "permissions"


########################################################################################


class _GroupsWithPermissions(BaseGet):
    groups: list[GroupGet]


class _MislabeledGet(BaseGet[PositiveInt]):
    permissions: list[GroupInlineGet]


########################################################################################


def test_resolver_exposes_derived_metadata() -> None:
    resolver = RelationResolver.build(ApiUser, ApiUserGet)

    assert resolver.model is ApiUser
    assert resolver.schema is ApiUserGet
    assert resolver.max_prefetch_depth == MAX_PREFETCH_DEPTH
    assert resolver.m2m_names == frozenset({"groups", "permissions"})
    assert resolver.fk_paths == frozenset()
    assert "blocklistedjwtoken_set" in resolver.nested_names


def test_resolver_prefetches_mix_names_and_objects() -> None:
    prefetches = RelationResolver.build(ApiUser, ApiUserGet).prefetches

    assert "groups" in prefetches
    assert any(isinstance(item, Prefetch) for item in prefetches)


def test_resolver_builds_annotated_queryset(db: None) -> None:
    qs = RelationResolver.build(ApiUser, ApiUserGet).build_qs()

    assert qs.model is ApiUser
    assert len(qs._prefetch_related_lookups) == 2  # ruff: ignore[private-member-access]
    assert qs.query.select_related is False


def test_resolver_applies_select_related(db: None) -> None:
    qs = RelationResolver.build(Permission, PermissionGet).build_qs()

    assert not qs._prefetch_related_lookups  # ruff: ignore[private-member-access]  # ty: ignore[redundant-condition]
    assert qs.query.select_related == {"content_type": {}}


def test_resolver_leaves_flat_queryset_untouched(db: None) -> None:
    qs = RelationResolver.build(ApiUser, ApiUserInlineGet).build_qs()

    assert not qs._prefetch_related_lookups  # ruff: ignore[private-member-access]  # ty: ignore[redundant-condition]
    assert qs.query.select_related is False


def test_resolver_honours_custom_depth() -> None:
    resolver = RelationResolver(max_prefetch_depth=0, model=ApiUser, schema=ApiUserGet)

    assert resolver.prefetches == frozenset({"groups", "permissions"})
