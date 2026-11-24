import os

from django.core.exceptions import ImproperlyConfigured
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "catalog.settings")
application = get_wsgi_application()

from django.conf import settings

from .settings.common import _DEFAULT_KEY

# Runs at server boot, after local_settings has had its say.
if not settings.DEBUG and settings.SECRET_KEY == _DEFAULT_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG=0.")
