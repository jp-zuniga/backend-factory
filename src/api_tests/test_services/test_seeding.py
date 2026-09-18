import pytest

from api_core import seeding
from api_core.seeding import (
    SeederError,
    describe_seeder,
    filter_seeders,
    get_fixture_seeders,
    get_structural_seeders,
    parse_app_filter,
    register_fixture,
    register_structural,
    run_seeders,
    run_structural_seeders,
)

########################################################################################


@pytest.fixture(autouse=True)
def clean_registries() -> None:
    for registry in seeding.REGISTRIES.values():
        registry.clear()


########################################################################################


def test_register_fixture_adds_entry() -> None:
    @register_fixture(app_label="alpha")
    def seed_alpha() -> None:
        pass

    entries = get_fixture_seeders()

    assert [(e.app_label, e.name) for e in entries] == [("alpha", "seed_alpha")]
    assert entries[0].func is seed_alpha
    assert get_structural_seeders() == []


def test_register_structural_adds_entry() -> None:
    @register_structural(app_label="alpha")
    def seed_alpha() -> None:
        pass

    entries = get_structural_seeders()

    assert [(e.app_label, e.name) for e in entries] == [("alpha", "seed_alpha")]
    assert entries[0].func is seed_alpha
    assert get_fixture_seeders() == []


def test_fixture_and_structural_registries_are_independent() -> None:
    @register_fixture(app_label="alpha", name="shared")
    def seed_fixture() -> None:
        pass

    @register_structural(app_label="alpha", name="shared")
    def seed_structural() -> None:
        pass

    assert [e.func for e in get_fixture_seeders()] == [seed_fixture]
    assert [e.func for e in get_structural_seeders()] == [seed_structural]


def test_register_uses_explicit_name() -> None:
    @register_fixture(app_label="alpha", name="custom")
    def seed_alpha() -> None:
        pass

    assert get_fixture_seeders()[0].name == "custom"


def test_register_rejects_duplicate_keys_within_same_kind() -> None:
    @register_fixture(app_label="alpha", name="dup")
    def seed_one() -> None:
        pass

    with pytest.raises(ValueError, match=r"alpha\.dup"):

        @register_fixture(app_label="alpha", name="dup")
        def seed_two() -> None:
            pass


def test_get_ordered_seeders_respects_depends_on() -> None:
    calls: list[str] = []

    @register_fixture(
        app_label="billing",
        name="invoices",
        depends_on=(("apiauth", "users"),),
    )
    def seed_invoices() -> None:
        calls.append("invoices")

    @register_fixture(app_label="apiauth", name="users")
    def seed_users() -> None:
        calls.append("users")

    for entry in get_fixture_seeders():
        entry.func()

    assert calls == ["users", "invoices"]


def test_get_ordered_seeders_is_stable_without_dependencies() -> None:
    @register_fixture(app_label="apiauth", name="first")
    def seed_first() -> None:
        pass

    @register_fixture(app_label="apiauth", name="second")
    def seed_second() -> None:
        pass

    names = [e.name for e in get_fixture_seeders()]

    assert names == ["first", "second"]


def test_get_ordered_seeders_raises_on_dangling_dependency() -> None:
    @register_fixture(
        app_label="billing",
        name="invoices",
        depends_on=(("apiauth", "users"),),
    )
    def seed_invoices() -> None:
        pass

    with pytest.raises(ValueError, match=r"apiauth\.users"):
        get_fixture_seeders()


def test_get_ordered_seeders_raises_on_cycle() -> None:
    @register_fixture(app_label="a", name="one", depends_on=(("a", "two"),))
    def seed_one() -> None:
        pass

    @register_fixture(app_label="a", name="two", depends_on=(("a", "one"),))
    def seed_two() -> None:
        pass

    with pytest.raises(ValueError, match="Ciclo de dependencias"):
        get_fixture_seeders()


def test_depends_on_cannot_cross_kinds() -> None:
    @register_structural(app_label="apiauth", name="users")
    def seed_users() -> None:
        pass

    @register_fixture(
        app_label="billing",
        name="invoices",
        depends_on=(("apiauth", "users"),),
    )
    def seed_invoices() -> None:
        pass

    with pytest.raises(ValueError, match=r"apiauth\.users"):
        get_fixture_seeders()


########################################################################################


def test_filter_seeders_only() -> None:
    @register_fixture(app_label="alpha")
    def seed_alpha() -> None:
        pass

    @register_fixture(app_label="beta")
    def seed_beta() -> None:
        pass

    filtered = filter_seeders(*get_fixture_seeders(), only=frozenset({"beta"}))

    assert [e.app_label for e in filtered] == ["beta"]


def test_filter_seeders_skip() -> None:
    @register_fixture(app_label="alpha")
    def seed_alpha() -> None:
        pass

    @register_fixture(app_label="beta")
    def seed_beta() -> None:
        pass

    filtered = filter_seeders(*get_fixture_seeders(), skip=frozenset({"beta"}))

    assert [e.app_label for e in filtered] == ["alpha"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", frozenset()),
        ("alpha", frozenset({"alpha"})),
        ("alpha,beta", frozenset({"alpha", "beta"})),
        (" alpha , beta ,", frozenset({"alpha", "beta"})),
    ],
)
def test_parse_app_filter(value: str, expected: frozenset[str]) -> None:
    assert parse_app_filter(value) == expected


def test_describe_seeder_without_dependencies() -> None:
    @register_fixture(app_label="alpha", name="seed")
    def seed_alpha() -> None:
        pass

    assert describe_seeder(get_fixture_seeders()[0]) == "alpha.seed"


def test_describe_seeder_with_dependencies() -> None:
    @register_fixture(app_label="apiauth", name="users")
    def seed_users() -> None:
        pass

    @register_fixture(
        app_label="billing",
        name="invoices",
        depends_on=(("apiauth", "users"),),
    )
    def seed_invoices() -> None:
        pass

    entry = next(e for e in get_fixture_seeders() if e.name == "invoices")

    assert describe_seeder(entry) == "billing.invoices (depende de: apiauth.users)"


########################################################################################


def test_run_seeders_calls_before_each_in_order(db: None) -> None:
    calls: list[str] = []

    @register_fixture(app_label="alpha", name="one")
    def seed_one() -> None:
        calls.append("run:one")

    @register_fixture(app_label="alpha", name="two")
    def seed_two() -> None:
        calls.append("run:two")

    run_seeders(
        *get_fixture_seeders(),
        before_each=lambda entry: calls.append(f"before:{entry.name}"),
    )

    assert calls == ["before:one", "run:one", "before:two", "run:two"]


def test_run_seeders_wraps_failures(db: None) -> None:
    @register_fixture(app_label="alpha", name="boom")
    def seed_boom() -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(SeederError, match=r"alpha\.boom.*kaboom") as excinfo:
        run_seeders(*get_fixture_seeders())

    assert isinstance(excinfo.value.__cause__, RuntimeError)


########################################################################################


def test_run_structural_seeders_runs_registered_entries(db: None) -> None:
    calls: list[str] = []

    @register_structural(app_label="alpha", name="one")
    def seed_one() -> None:
        calls.append("one")

    ran = run_structural_seeders()

    assert ran is True
    assert calls == ["one"]


def test_run_structural_seeders_respects_only_and_skip(db: None) -> None:
    calls: list[str] = []

    @register_structural(app_label="alpha", name="one")
    def seed_one() -> None:
        calls.append("one")

    @register_structural(app_label="beta", name="two")
    def seed_two() -> None:
        calls.append("two")

    run_structural_seeders(only=frozenset({"beta"}))

    assert calls == ["two"]


def test_run_structural_seeders_skips_when_configured_off(
    db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        seeding,
        "CONFIG",
        seeding.CONFIG.model_copy(update={"SKIP_SEEDERS": True}),
    )

    calls: list[str] = []

    @register_structural(app_label="alpha", name="one")
    def seed_one() -> None:
        calls.append("one")

    ran = run_structural_seeders()

    assert ran is False
    assert calls == []
