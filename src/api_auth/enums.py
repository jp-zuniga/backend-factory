from django.db.models import TextChoices

########################################################################################


class ApiUserTypes(TextChoices):
    ADMIN = "Administrador"
    CLIENT = "Cliente"
    STAFF = "Personal"


########################################################################################


class TokenTypes(TextChoices):
    ACCESS = "access"
    CHALLENGE = "challenge"
    REFRESH = "refresh"


########################################################################################


class VerificationPurposes(TextChoices):
    EMAIL = "email_verification"


########################################################################################


class PermissionTypes(TextChoices):
    ADD = "add"
    CHANGE = "change"
    DELETE = "delete"
    VIEW = "view"
