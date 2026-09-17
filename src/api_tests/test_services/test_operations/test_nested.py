from collections.abc import Sequence

import pytest

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.db.transaction import atomic

from api_auth.controllers.user import ApiUserListController
from api_core.services.operations.nested import (
    COPY_THRESHOLD,
    MAX_CONFLICTS,
    NestedCreateOperation,
    exec_nested_post,
    exec_nested_update,
    match_conflict_index,
    probe_conflict_index,
    scope_child_conflict,
    write_children,
    write_collection,
)
from api_exceptions.enums import ConflictErrorTypes
from api_exceptions.errors import ConflictError, NotFoundError

########################################################################################

pytestmark = pytest.mark.django_db(transaction=True)

########################################################################################


def permission_items(*codenames: str) -> Sequence[dict]:
    return tuple(
        {"codename": codename, "name": f"Puede {codename}"} for codename in codenames
    )


def duplicate_permission_error(content_type: ContentType) -> IntegrityError:
    Permission.objects.create(
        codename="duplicado",
        name="Duplicado",
        content_type=content_type,
    )

    try:
        with atomic():
            Permission.objects.create(
                codename="duplicado",
                name="Otro",
                content_type=content_type,
            )
    except IntegrityError as raised:
        return raised

    pytest.fail("Se esperaba una violacion de unicidad.")


########################################################################################


def test_nested_constants() -> None:
    assert COPY_THRESHOLD == 32
    assert MAX_CONFLICTS == COPY_THRESHOLD


def test_nested_resolve_fields_uses_nested_names(
    list_controller: ApiUserListController,
) -> None:
    assert "blocklistedjwtoken_set" in NestedCreateOperation.resolve_fields(
        list_controller,
    )


########################################################################################


def test_write_collection_creates_children(content_type: ContentType) -> None:
    write_collection(
        back_ref="content_type",
        child=Permission,
        items=permission_items("leer", "escribir"),
        obj=content_type,
        replace=False,
    )

    assert content_type.permission_set.count() == 2  # ty: ignore[unresolved-attribute]


def test_write_collection_is_a_noop_on_empty_items(content_type: ContentType) -> None:
    write_collection(
        back_ref="content_type",
        child=Permission,
        items=(),
        obj=content_type,
        replace=False,
    )

    assert content_type.permission_set.count() == 0  # ty: ignore[unresolved-attribute]


def test_write_collection_replaces_existing_children(content_type: ContentType) -> None:
    write_collection(
        back_ref="content_type",
        child=Permission,
        items=permission_items("viejo"),
        obj=content_type,
        replace=False,
    )

    write_collection(
        back_ref="content_type",
        child=Permission,
        items=permission_items("nuevo"),
        obj=content_type,
        replace=True,
    )

    assert [perm.codename for perm in content_type.permission_set.all()] == ["nuevo"]  # ty: ignore[unresolved-attribute]


def test_write_collection_clears_on_empty_replace(content_type: ContentType) -> None:
    write_collection(
        back_ref="content_type",
        child=Permission,
        items=permission_items("descartado"),
        obj=content_type,
        replace=False,
    )

    write_collection(
        back_ref="content_type",
        child=Permission,
        items=(),
        obj=content_type,
        replace=True,
    )

    assert content_type.permission_set.count() == 0  # ty: ignore[unresolved-attribute]


def test_write_collection_uses_copy_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
    content_type: ContentType,
) -> None:
    monkeypatch.setattr("api_core.services.operations.nested.COPY_THRESHOLD", 2)

    write_collection(
        back_ref="content_type",
        child=Permission,
        items=permission_items("uno", "dos", "tres"),
        obj=content_type,
        replace=False,
    )

    assert content_type.permission_set.count() == 3  # ty: ignore[unresolved-attribute]


########################################################################################


def test_write_children_ignores_none_values(content_type: ContentType) -> None:
    write_children(
        model=ContentType,
        nested={"permission_set": None},
        obj=content_type,
        replace=False,
    )

    assert content_type.permission_set.count() == 0  # ty: ignore[unresolved-attribute]


def test_write_children_ignores_unknown_relations(content_type: ContentType) -> None:
    write_children(
        model=ContentType,
        nested={"relacion_inexistente": permission_items("x")},
        obj=content_type,
        replace=False,
    )

    assert content_type.permission_set.count() == 0  # ty: ignore[unresolved-attribute]


def test_write_children_writes_collections(content_type: ContentType) -> None:
    write_children(
        model=ContentType,
        nested={"permission_set": permission_items("alfa", "beta")},
        obj=content_type,
        replace=False,
    )

    assert content_type.permission_set.count() == 2  # ty: ignore[unresolved-attribute]


def test_write_children_scopes_child_conflicts(content_type: ContentType) -> None:
    with pytest.raises(ConflictError) as raised:
        write_children(
            model=ContentType,
            nested={"permission_set": permission_items("choque", "choque")},
            obj=content_type,
            replace=False,
        )

    assert raised.value.detail == ConflictErrorTypes.UNIQUE.value
    assert all(
        key.startswith("body.permission_set") for key in raised.value.field_errors
    ), raised.value.field_errors


########################################################################################


def test_match_conflict_index_finds_matching_item(content_type: ContentType) -> None:
    error: IntegrityError = duplicate_permission_error(content_type)

    items: Sequence[dict] = (
        {"content_type_id": content_type.pk, "codename": "otro"},
        {"content_type_id": content_type.pk, "codename": "duplicado"},
    )

    assert match_conflict_index(exc=error, items=items) == 1


def test_match_conflict_index_without_psql_context() -> None:
    assert match_conflict_index(exc=IntegrityError(), items=({"a": 1},)) is None


def test_match_conflict_index_without_matching_item(content_type: ContentType) -> None:
    error: IntegrityError = duplicate_permission_error(content_type)

    assert match_conflict_index(exc=error, items=({"codename": "ninguno"},)) is None


def test_match_conflict_index_on_empty_items(content_type: ContentType) -> None:
    error: IntegrityError = duplicate_permission_error(content_type)

    assert match_conflict_index(exc=error, items=()) is None


########################################################################################


def test_probe_conflict_index_finds_offending_position(
    content_type: ContentType,
) -> None:
    Permission.objects.create(
        codename="ocupado",
        name="Ocupado",
        content_type=content_type,
    )

    index: int | None = probe_conflict_index(
        back_ref="content_type",
        child=Permission,
        items=permission_items("libre", "ocupado"),
        obj=content_type,
    )

    assert index == 1


def test_probe_conflict_index_returns_none_when_clean(
    content_type: ContentType,
) -> None:
    index: int | None = probe_conflict_index(
        back_ref="content_type",
        child=Permission,
        items=permission_items("limpio-uno", "limpio-dos"),
        obj=content_type,
    )

    assert index is None


########################################################################################


def test_scope_child_conflict_without_items(content_type: ContentType) -> None:
    error: IntegrityError = duplicate_permission_error(content_type)

    conflict: ConflictError = scope_child_conflict(
        back_ref="content_type",
        child=Permission,
        exc=error,
        items=None,
        name="permission_set",
        obj=content_type,
    )

    assert all(
        key.startswith("body.permission_set") for key in conflict.field_errors
    ), conflict.field_errors
    assert not any(key.split(".")[-1].isdigit() for key in conflict.field_errors), (
        conflict.field_errors
    )


def test_scope_child_conflict_appends_matched_index(content_type: ContentType) -> None:
    error: IntegrityError = duplicate_permission_error(content_type)

    conflict: ConflictError = scope_child_conflict(
        back_ref="content_type",
        child=Permission,
        exc=error,
        items=(
            {"content_type_id": content_type.pk, "codename": "otro"},
            {"content_type_id": content_type.pk, "codename": "duplicado"},
        ),
        name="permission_set",
        obj=content_type,
    )

    assert any(".1." in key for key in conflict.field_errors), conflict.field_errors


def test_scope_child_conflict_falls_back_to_probing(content_type: ContentType) -> None:
    error: IntegrityError = duplicate_permission_error(content_type)

    conflict: ConflictError = scope_child_conflict(
        back_ref="content_type",
        child=Permission,
        exc=error,
        items=permission_items("sondeado", "duplicado"),
        name="permission_set",
        obj=content_type,
    )

    assert any(".1." in key for key in conflict.field_errors), conflict.field_errors


########################################################################################


def test_exec_nested_post_creates_parent_and_children(db: None) -> None:
    created = exec_nested_post(
        "permission_set",
        data={
            "app_label": "pruebas_anidadas",
            "model": "recurso",
            "permission_set": permission_items("ver", "editar"),
        },
        qs=ContentType.objects.all(),
    )

    ContentType.objects.clear_cache()

    assert created.app_label == "pruebas_anidadas"
    assert created.permission_set.count() == 2


def test_exec_nested_post_without_children(db: None) -> None:
    created = exec_nested_post(
        "permission_set",
        data={
            "app_label": "pruebas_anidadas",
            "model": "vacio",
            "permission_set": None,
        },
        qs=ContentType.objects.all(),
    )

    ContentType.objects.clear_cache()

    assert created.permission_set.count() == 0


def test_exec_nested_update_replaces_children(content_type: ContentType) -> None:
    Permission.objects.create(
        codename="antiguo",
        name="Antiguo",
        content_type=content_type,
    )

    updated = exec_nested_update(
        "permission_set",
        data={
            "model": "renombrado",
            "permission_set": permission_items("reciente"),
        },
        lookup={"id": content_type.pk},
        qs=ContentType.objects.all(),
    )

    ContentType.objects.clear_cache()

    assert updated.model == "renombrado"
    assert [perm.codename for perm in updated.permission_set.all()] == ["reciente"]


def test_exec_nested_update_keeps_children_when_absent(
    content_type: ContentType,
) -> None:
    Permission.objects.create(
        codename="preservado",
        name="Preservado",
        content_type=content_type,
    )

    updated = exec_nested_update(
        "permission_set",
        data={"model": "solo-scalar"},
        lookup={"id": content_type.pk},
        qs=ContentType.objects.all(),
    )

    ContentType.objects.clear_cache()

    assert updated.permission_set.count() == 1


def test_exec_nested_update_requires_existing_parent(db: None) -> None:
    with pytest.raises(NotFoundError):
        exec_nested_update(
            "permission_set",
            data={"model": "fantasma"},
            lookup={"id": 987654},
            qs=ContentType.objects.all(),
        )
