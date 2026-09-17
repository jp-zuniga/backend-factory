from typing import Final

from faker import Faker
from hypothesis.strategies import (
    DrawFn,
    SearchStrategy,
    booleans,
    builds,
    characters,
    composite,
    integers,
    just,
    lists,
    sampled_from,
    text,
)
from polyfactory.factories.pydantic_factory import ModelFactory

from api_auth.enums import ApiUserTypes, TokenTypes
from api_auth.models import ApiUser
from api_auth.schemas.login import MobileLoginPost, WebLoginPost
from api_auth.schemas.logout import MobileLogoutPost
from api_auth.schemas.refresh import MobileRefreshPost
from api_auth.schemas.user import ApiClientPost, ApiStaffPost
from api_auth.schemas.verify import MobileVerifyPost
from api_core.schemas.pagination import PageQuery
from api_tests.conftest import PASSWORD

########################################################################################

FAKER: Final[Faker] = Faker(locale="es")

########################################################################################


class MobileLoginPostFactory(ModelFactory[MobileLoginPost]):
    __model__ = MobileLoginPost


class WebLoginPostFactory(ModelFactory[WebLoginPost]):
    __model__ = WebLoginPost


class MobileLogoutPostFactory(ModelFactory[MobileLogoutPost]):
    __model__ = MobileLogoutPost


class MobileRefreshPostFactory(ModelFactory[MobileRefreshPost]):
    __model__ = MobileRefreshPost


class MobileVerifyPostFactory(ModelFactory[MobileVerifyPost]):
    __model__ = MobileVerifyPost

    @classmethod
    def type(cls) -> TokenTypes:
        return TokenTypes.ACCESS


class ApiClientPostFactory(ModelFactory[ApiClientPost]):
    __model__ = ApiClientPost

    @classmethod
    def email(cls) -> str:
        return FAKER.unique.email()

    @classmethod
    def group(cls) -> ApiUserTypes:
        return ApiUserTypes.CLIENT

    @classmethod
    def password1(cls) -> str:
        return PASSWORD

    @classmethod
    def password2(cls) -> str:
        return PASSWORD

    @classmethod
    def username(cls) -> str:
        return FAKER.unique.user_name()[:100]


class ApiStaffPostFactory(ModelFactory[ApiStaffPost]):
    __model__ = ApiStaffPost

    @classmethod
    def email(cls) -> str:
        return FAKER.unique.email()

    @classmethod
    def groups(cls) -> None:
        return None

    @classmethod
    def password1(cls) -> str:
        return PASSWORD

    @classmethod
    def password2(cls) -> str:
        return PASSWORD

    @classmethod
    def permissions(cls) -> None:
        return None

    @classmethod
    def username(cls) -> str:
        return FAKER.unique.user_name()[:100]


class PageQueryFactory(ModelFactory[PageQuery]):
    __model__ = PageQuery

    @classmethod
    def page(cls) -> int:
        return 1

    @classmethod
    def page_size(cls) -> int:
        return 20


########################################################################################


def build_users(count: int, *, prefix: str = "random") -> list[ApiUser]:
    return [
        ApiUser.objects.create_user(
            username=f"{prefix}-{index}",
            email=f"{prefix}-{index}@unit.example.com",
            first_name=FAKER.first_name(),
            last_name=FAKER.last_name(),
            password=PASSWORD,
        )
        for index in range(count)
    ]


########################################################################################

IDENTIFIERS: Final[SearchStrategy[str]] = text(
    alphabet=characters(categories=("Lu", "Ll", "Nd"), max_codepoint=122),
    min_size=1,
    max_size=30,
)

########################################################################################

CRUMBS: Final[SearchStrategy[list[int | str]]] = lists(
    integers(min_value=0, max_value=99) | IDENTIFIERS,
    min_size=1,
    max_size=4,
)

FIELD_ERRORS: Final[SearchStrategy] = builds(
    dict,
    zip_strategy := just(()),
) | lists(
    builds(tuple, lists(IDENTIFIERS, min_size=2, max_size=2)),
    min_size=1,
    max_size=4,
).map(dict)

SAFE_TEXT: Final[SearchStrategy[str]] = text(
    alphabet=characters(
        min_codepoint=33,
        max_codepoint=126,
        exclude_characters="\\'\"",
    ),
    max_size=40,
)

########################################################################################

FLAGS: Final[SearchStrategy[bool]] = booleans()

PAGE_NUMBERS: Final[SearchStrategy[int]] = integers(min_value=1, max_value=1000)

PAGE_SIZES: Final[SearchStrategy[int]] = integers(min_value=1, max_value=100)

TOKEN_TYPES: Final[SearchStrategy[TokenTypes]] = sampled_from(TokenTypes)

USER_TYPES: Final[SearchStrategy[ApiUserTypes]] = sampled_from(ApiUserTypes)

########################################################################################


@composite
def camel_identifiers(draw: DrawFn) -> str:
    head: str = draw(
        text(alphabet=characters(categories=("Lu",)), min_size=1, max_size=1)
    )

    tail: str = draw(text(alphabet=characters(categories=("Ll",)), max_size=12))

    return f"{head}{tail}"
