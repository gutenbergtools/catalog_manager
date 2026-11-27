"""Settings for the test suite: no catalog database or network is required.

Run the tests with ``python manage.py test``. Django's auth/session tables
live in an in-memory SQLite database, and the catalog itself is mocked or
replaced by small fixtures. Production settings in ``common.py`` are still
imported first, so template and middleware behaviour stays the same.
"""

from .common import *  # noqa: F403

# Django's own tables only; the catalog is a separate SQLAlchemy database.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# New passwords are quick to hash in tests; fixture hashes still verify.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Tests render templates without running collectstatic.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Keep test output in the terminal, not in logs/catalog_manager.log.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "CRITICAL"},
}
