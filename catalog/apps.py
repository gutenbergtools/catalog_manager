import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

log = logging.getLogger(__name__)


class CatalogConfig(AppConfig):
    name = "catalog"
    verbose_name = "Catalog Manager"


_ensured = set()  # (schema, database) pairs already ensured


@receiver(connection_created)
def ensure_schema(sender, connection, **kwargs):
    """Django's tables live in their own schema; create it if it is missing.

    Runs once per process, on the first Postgres connection, so `migrate`
    works on a fresh database without a manual schema step. A user without
    CREATE rights just logs a warning: whoever runs the migration can then
    create the schema once with a privileged account.
    """
    if connection.vendor != "postgresql":
        return
    schema = settings.AUTH_SCHEMA
    options = (connection.settings_dict.get("OPTIONS") or {}).get("options") or ""
    if ("-csearch_path=%s" % schema) not in options.replace(" ", ""):
        # A local_settings DATABASES pin owns the layout; leave it alone.
        return
    key = (schema, connection.settings_dict.get("NAME"))
    if key in _ensured:
        return
    _ensured.add(key)
    if not schema.replace("_", "a").isalnum():
        log.warning("Auth schema name %r is not a plain identifier.", schema)
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS %s" % schema)
    except Exception:
        log.warning(
            "Could not create schema %s (missing privileges?). Create it once "
            "with a privileged account, then migrate again.",
            schema,
        )


@receiver(post_migrate)
def ensure_groups(sender, **kwargs):
    """The cataloguer group gates the whole site; make sure it exists and
    that existing administrators are members, so migrate repairs a fresh or
    upgraded deployment."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    group, _ = Group.objects.get_or_create(name=settings.CATALOGUER_GROUP)
    group.user_set.add(*get_user_model().objects.filter(is_superuser=True))


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def add_superuser_to_group(sender, instance, **kwargs):
    """Every administrator may use the site: createsuperuser and the admin
    user form both land in the cataloguer group, so nobody has to remember
    the extra step."""
    from django.contrib.auth.models import Group

    if instance.is_superuser:
        Group.objects.get_or_create(name=settings.CATALOGUER_GROUP)[0].user_set.add(instance)
