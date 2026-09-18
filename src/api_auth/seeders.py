from django.contrib.auth.models import Group, Permission

from api_auth.enums import ApiUserTypes
from api_core.seeding import register_structural

########################################################################################


@register_structural(app_label="apiauth", name="groups_and_permissions")
def seed_groups_and_permissions() -> None:
    # ruff: disable[commented-out-code]
    # admin_only: Q = (
    #     Q(content_type__app_label__icontains="auth")
    #     | Q(content_type__app_label__icontains="pghistory")
    #     | Q(content_type__app_label__icontains="blocklist")
    #     | Q(content_type__app_label__icontains="contenttypes")
    # )

    # read_only: Q = Q(codename__icontains="view")
    # ruff: enable[commented-out-code]

    for v in ApiUserTypes.values:
        Group.objects.get_or_create(name=v)

    Group.objects.get(
        name=ApiUserTypes.ADMIN.value,
    ).permissions.add(*Permission.objects.all())
