import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate
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
    """The cataloguer group gates the whole site; make sure it exists."""
    from django.contrib.auth.models import Group

    Group.objects.get_or_create(name=settings.CATALOGUER_GROUP)
