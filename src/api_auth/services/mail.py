from dataclasses import dataclass
from string import Template
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.core.mail import send_mail
from django.db.transaction import on_commit

from api_auth.enums import VerificationPurposes

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Final

########################################################################################


@dataclass(frozen=True, slots=True)
class MailTemplate:
    body: Template
    subject: Template


########################################################################################

MAIL_TEMPLATES: Final[dict[VerificationPurposes, MailTemplate]] = {
    VerificationPurposes.EMAIL: MailTemplate(
        body=Template(
            """
Hola:

Para confirmar su correo electrónico, ingrese al siguiente enlace:

${link}

Si su cliente de correo no admite enlaces, ingrese este código: ${token}

El enlace vence en ${hours} horas.

Si usted no creó esta cuenta, ignore este mensaje.
""".strip()
        ),
        subject=Template("Confirme su correo electrónico"),
    ),
}

########################################################################################


def render_template(
    purpose: VerificationPurposes,
    context: Mapping[str, object],
) -> tuple[str, str]:
    """
    Render the message associated with a verification purpose.

    Args:
        purpose: The purpose whose template must be rendered.
        context: The values of every placeholder in the template.

    Returns:
        The rendered subject and body.

    """

    template: MailTemplate = MAIL_TEMPLATES[purpose]

    return (
        template.subject.substitute(context),
        template.body.substitute(context),
    )


########################################################################################


async def send_template(
    purpose: VerificationPurposes,
    context: Mapping[str, object],
    to: str,
) -> None:
    subject, body = render_template(purpose, context)

    # delivery is deferred so that a rolled back transaction
    # never sends a message about a record that does not exist
    await sync_to_async(func=on_commit)(
        lambda: send_mail(
            from_email=None,
            message=body,
            recipient_list=[to],
            subject=subject,
        ),
    )
