import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(key, default=""):
    return os.environ.get(key, default)


def env_list(key, default=""):
    return [item.strip() for item in env(key, default).split(",") if item.strip()]


LOG_DIR = Path(env("DJANGO_LOG_DIR", str(BASE_DIR / "logs")))
_DEFAULT_KEY = "insecure-development-key-do-not-use-in-production"
SECRET_KEY = env("DJANGO_SECRET_KEY", _DEFAULT_KEY)
DEBUG = env("DJANGO_DEBUG", "0") == "1"
# The refuse-to-boot check for the default key lives in wsgi.py: it can only
# run after the full settings (including local_settings) have loaded.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
for _key, _default in (
    ("PGHOST", "127.0.0.1"),
    ("PGPORT", "5432"),
    ("PGDATABASE", "gutenberg"),
    ("PGUSER", "gutenberg"),
):
    os.environ.setdefault(_key, env(_key, _default))
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "catalog.apps.CatalogConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "catalog.middleware.SecurityHeadersMiddleware",
]
ROOT_URLCONF = "catalog.urls"
WSGI_APPLICATION = "catalog.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "catalog" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.middleware.brand",
            ]
        },
    }
]
DATABASES = {
    "default": {
        # Auth/session/admin tables live in the same Postgres server as the
        # book data, but in their own schema (default: "django"), so the two
        # never mix. The schema is created automatically on first connect.
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("PGDATABASE", "gutenberg"),
        "USER": env("PGUSER", "gutenberg"),
        "PASSWORD": env("PGPASSWORD", ""),
        "HOST": env("PGHOST", "127.0.0.1"),
        "PORT": env("PGPORT", "5432"),
        "OPTIONS": {"options": "-csearch_path=%s" % env("DJANGO_DB_SCHEMA", "django")},
    },
}
AUTH_SCHEMA = env("DJANGO_DB_SCHEMA", "django")
MIGRATION_MODULES = {"catalog": None}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": env("DJANGO_CACHE_DIR", str(BASE_DIR / "cache")),
        "OPTIONS": {"MAX_ENTRIES": 2000},
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "catalog_manager.log"),
            "maxBytes": 5000000,
            "backupCount": 5,
            "formatter": "plain",
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["console", "file"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", "America/New_York")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "books"
LOGOUT_REDIRECT_URL = "login"
ADMIN_URL = env("DJANGO_ADMIN_URL", "admin").strip("/")
SESSION_COOKIE_NAME = "catalog_cat"
CSRF_COOKIE_NAME = "catalog_cat_csrf"
CSRF_COOKIE_HTTPONLY = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 1048576
SESSION_COOKIE_AGE = int(env("DJANGO_SESSION_AGE", "43200"))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
secure = env("DJANGO_SECURE_COOKIES", "0" if DEBUG else "1") == "1"
if secure:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
# The redirect stays opt-in: behind a TLS-terminating proxy that does not
# pass X-Forwarded-Proto it loops, so the proxy should send http -> https.
if env("DJANGO_SSL_REDIRECT", "0") == "1":
    SECURE_SSL_REDIRECT = True
PAGE_SIZE = int(env("CATALOG_PAGE_SIZE", "50"))
RATE_LOGIN = env("CATALOG_RATE_LOGIN", "10/m")
RATE_LOGIN_USER = env("CATALOG_RATE_LOGIN_USER", "10/m")
RATE_POST = env("CATALOG_RATE_POST", "60/m")
CATALOG_TRUSTED_PROXIES = env_list("CATALOG_TRUSTED_PROXIES", "127.0.0.1,::1")
# Callable path: django-ratelimit resolves X-Real-IP only from trusted proxies.
RATELIMIT_IP_META_KEY = "catalog.proxy.client_ip"
# Who may use the site: membership in this Django auth group (see
# catalog/apps.py, which creates it on migrate).
CATALOGUER_GROUP = env("DJANGO_CATALOGUER_GROUP", "cataloguer")
os.makedirs(LOG_DIR, exist_ok=True)
