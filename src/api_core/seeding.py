from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from django.apps import apps
from django.db.transaction import atomic
from pglock import advisory

from api_core.config import CONFIG

########################################################################################

type Seeder = Callable[[], None]
type SeederKey = tuple[str, str]

STRUCTURAL_LOCK_ID: Final[str] = "api_core.structural_seed"

########################################################################################


class SeederError(RuntimeError):
    pass


class SeederKind(StrEnum):
    FIXTURE = "fixture"
    STRUCTURAL = "structural"


@dataclass(frozen=True, slots=True)
class SeederEntry:
    func: Seeder
    app_label: str
    name: str
    depends_on: Sequence[SeederKey]
    registered_at: int


REGISTRIES: Final[dict[SeederKind, dict[SeederKey, SeederEntry]]] = {
    kind: {} for kind in SeederKind
}

########################################################################################


def register_fixture(
    *,
    app_label: str,
    name: str | None = None,
    depends_on: Sequence[SeederKey] = (),
) -> Callable[[Seeder], Seeder]:
    return base_register(
        SeederKind.FIXTURE,
        app_label=app_label,
        name=name,
        depends_on=depends_on,
    )


def register_structural(
    *,
    app_label: str,
    name: str | None = None,
    depends_on: Sequence[SeederKey] = (),
) -> Callable[[Seeder], Seeder]:
    return base_register(
        SeederKind.STRUCTURAL,
        app_label=app_label,
        name=name,
        depends_on=depends_on,
    )


########################################################################################


def base_register(
    kind: SeederKind,
    *,
    app_label: str,
    name: str | None,
    depends_on: Sequence[SeederKey],
) -> Callable[[Seeder], Seeder]:
    registry = REGISTRIES[kind]

    def decorator(func: Seeder) -> Seeder:
        key: SeederKey = (app_label, name or func.__name__)  # ty: ignore[unresolved-attribute]

        if key in registry:
            raise ValueError(
                f"Ya existe un seeder `{kind.value}` registrado como "
                f"`{key[0]}.{key[1]}`.",
            )

        registry[key] = SeederEntry(
            func=func,
            app_label=key[0],
            name=key[1],
            depends_on=tuple(depends_on),
            registered_at=len(registry),
        )

        return func

    return decorator


########################################################################################


def get_fixture_seeders() -> Sequence[SeederEntry]:
    return ordered_registry(REGISTRIES[SeederKind.FIXTURE])


def get_structural_seeders() -> Sequence[SeederEntry]:
    return ordered_registry(REGISTRIES[SeederKind.STRUCTURAL])


########################################################################################


def ordered_registry(registry: dict[SeederKey, SeederEntry]) -> Sequence[SeederEntry]:
    app_order: dict[str, int] = {
        config.label: index for index, config in enumerate(apps.get_app_configs())
    }

    for entry in registry.values():
        for dep in entry.depends_on:
            if dep not in registry:
                raise ValueError(
                    f"El seeder `{entry.app_label}.{entry.name}` depende de "
                    f"`{dep[0]}.{dep[1]}`, que no está registrado.",
                )

    def sort_key(key: SeederKey) -> tuple[int, int]:
        entry = registry[key]
        return (app_order.get(entry.app_label, len(app_order)), entry.registered_at)

    ordered: list[SeederEntry] = []
    done: set[SeederKey] = set()

    def visit(key: SeederKey, path: tuple[SeederKey, ...]) -> None:
        if key in done:
            return

        if key in path:
            cycle = " -> ".join(f"{k[0]}.{k[1]}" for k in (*path, key))
            raise ValueError(f"Ciclo de dependencias entre seeders: {cycle}.")

        entry = registry[key]

        for dep in sorted(entry.depends_on, key=sort_key):
            visit(dep, (*path, key))

        done.add(key)
        ordered.append(entry)

    for key in sorted(registry, key=sort_key):
        visit(key, ())

    return ordered


########################################################################################


def describe_seeder(entry: SeederEntry) -> str:
    deps = ", ".join(f"{dep[0]}.{dep[1]}" for dep in entry.depends_on)
    line = f"{entry.app_label}.{entry.name}"

    if deps:
        line += f" (needs: {deps})"

    return line


def filter_seeders(
    *entries: SeederEntry,
    only: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> Sequence[SeederEntry]:
    return [
        entry
        for entry in entries
        if (not only or entry.app_label in only) and entry.app_label not in skip
    ]


def parse_app_filter(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


########################################################################################


def run_seeders(
    *entries: SeederEntry,
    before_each: Callable[[SeederEntry], None] | None = None,
) -> None:
    for entry in entries:
        if before_each is not None:
            before_each(entry)

        try:
            with atomic():
                entry.func()
        except Exception as exc:
            raise SeederError(
                f"El seeder `{entry.app_label}.{entry.name}` falló: {exc}",
            ) from exc


def run_structural_seeders(
    *,
    before_each: Callable[[SeederEntry], None] | None = None,
    only: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> bool:
    if CONFIG.SKIP_SEEDERS:
        return False

    with advisory(lock_id=STRUCTURAL_LOCK_ID, timeout=0) as acquired:
        if not acquired:
            return False

        entries = filter_seeders(*get_structural_seeders(), only=only, skip=skip)

        run_seeders(*entries, before_each=before_each)

        return True
