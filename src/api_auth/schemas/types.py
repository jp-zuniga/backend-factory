from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from api_auth.models import ApiUser
from api_core.schemas.validators import empty_or_email

########################################################################################

type Email = Annotated[
    str,
    AfterValidator(func=empty_or_email),
    AfterValidator(func=ApiUser.objects.normalize_email),
    StringConstraints(max_length=254),
]

type RequiredEmail = Annotated[
    Email,
    AfterValidator(func=ApiUser.objects.normalize_email),
    StringConstraints(max_length=254, min_length=1),
]

type JwtToken = Annotated[str, StringConstraints(max_length=512, min_length=1)]
type Password = Annotated[str, StringConstraints(max_length=256, min_length=1)]
type TwoFactorCode = Annotated[str, StringConstraints(max_length=32, min_length=6)]
type Username = Annotated[str, StringConstraints(max_length=100, min_length=1)]

type VerificationToken = Annotated[
    str,
    StringConstraints(max_length=64, min_length=32, pattern=r"^[A-Za-z0-9_-]+$"),
]
