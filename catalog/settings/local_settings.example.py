"""Local overrides for Catalog Manager.

Copy this file to ``catalog/settings/local_settings.py`` (gitignored), then
replace the example hosts, database names and secret key below. It is loaded
after ``common.py``, so these values win over its environment defaults.

The settings that a production deployment needs are active here. Advanced
extras are at the bottom, commented out.
"""

# ---------------------------------------------------------------------------
# Core and security
# ---------------------------------------------------------------------------
# Never leave debug on in production.
# https://docs.djangoproject.com/en/5.2/ref/settings/#debug
DEBUG = False

# Replace with 50+ random characters. The app refuses to start on the
# development default when DEBUG is off.
# https://docs.djangoproject.com/en/5.2/ref/settings/#secret-key
SECRET_KEY = "replace-this-with-50-random-characters"

# Public host names Django may serve. Do not use "*" in production.
# https://docs.djangoproject.com/en/5.2/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["catalog.example.org"]

# HTTPS origins allowed to submit forms.
# https://docs.djangoproject.com/en/5.2/ref/settings/#csrf-trusted-origins
CSRF_TRUSTED_ORIGINS = ["https://catalog.example.org"]

# Trust the reverse proxy's protocol and public host.
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header
# https://docs.djangoproject.com/en/5.2/ref/settings/#use-x-forwarded-host
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Send HTTP to HTTPS. Requires the proxy to send X-Forwarded-Proto.
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = True

# Tell browsers to keep using HTTPS for one year.
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-hsts-seconds
SECURE_HSTS_SECONDS = 31536000

# Cookies are HTTPS-only and unreachable from JavaScript.
# https://docs.djangoproject.com/en/5.2/ref/settings/#session-cookie-secure
# https://docs.djangoproject.com/en/5.2/ref/settings/#csrf-cookie-secure
# https://docs.djangoproject.com/en/5.2/ref/settings/#session-cookie-httponly
# https://docs.djangoproject.com/en/5.2/ref/settings/#csrf-cookie-httponly
# https://docs.djangoproject.com/en/5.2/ref/settings/#session-cookie-samesite
# https://docs.djangoproject.com/en/5.2/ref/settings/#csrf-cookie-samesite
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Ask browsers not to guess content types, leak referrers, or frame the site.
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-content-type-nosniff
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-referrer-policy
# https://docs.djangoproject.com/en/5.2/ref/settings/#x-frame-options
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Password-set links are valid for two hours.
# https://docs.djangoproject.com/en/5.2/ref/settings/#password-reset-timeout
PASSWORD_RESET_TIMEOUT = 7200

# Password strength checks shown on the change-password page.
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Only these proxy addresses may supply X-Real-IP for rate limiting.
CATALOG_TRUSTED_PROXIES = ["127.0.0.1", "::1"]

# Users in this Django auth group may use the site.
CATALOGUER_GROUP = "cataloguer"

# Change the admin path away from the default.
ADMIN_URL = "admin"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Example database values (dummies). Replace them, or delete this block to
# use the PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD variables.
# AUTH_SCHEMA must match the search_path below.
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "catalog_dummy",
        "USER": "catalog_dummy_user",
        "PASSWORD": "change-me",
        "HOST": "127.0.0.1",
        "PORT": "5432",
        "OPTIONS": {"options": "-csearch_path=django"},
    }
}
AUTH_SCHEMA = "django"

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Production mail is relayed through the local host. A local MTA normally
# listens on port 25 without TLS; use 587 with TLS if your relay requires it.
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-host
EMAIL_HOST = "localhost"
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-port
EMAIL_PORT = 25
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-use-tls
EMAIL_USE_TLS = False
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-use-ssl
EMAIL_USE_SSL = False
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = "Catalog Manager <catalog@example.org>"
# https://docs.djangoproject.com/en/5.2/ref/settings/#server-email
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-timeout
EMAIL_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Advanced extras
# ---------------------------------------------------------------------------
# HSTS for every subdomain, and browser preload submission.
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-hsts-include-subdomains
# https://docs.djangoproject.com/en/5.2/ref/settings/#secure-hsts-preload
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# Session lifetime in seconds.
# https://docs.djangoproject.com/en/5.2/ref/settings/#session-cookie-age
# SESSION_COOKIE_AGE = 43200

# Authenticated SMTP, if the relay needs a user and password.
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-host-user
# https://docs.djangoproject.com/en/5.2/ref/settings/#email-host-password
# EMAIL_HOST_USER = "catalog@example.org"
# EMAIL_HOST_PASSWORD = ""
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True

# Where collectstatic writes, and where cache/log files live.
# https://docs.djangoproject.com/en/5.2/ref/settings/#static-root
# https://docs.djangoproject.com/en/5.2/ref/settings/#caches
# https://docs.djangoproject.com/en/5.2/ref/settings/#logging
# STATIC_ROOT = "/var/lib/catalog_manager/staticfiles"
# DJANGO_CACHE_DIR and DJANGO_LOG_DIR are read from the environment.

# Rows per listing page and rate limits.
# PAGE_SIZE = 50
# RATE_LOGIN = "10/m"
# RATE_LOGIN_USER = "10/m"
# RATE_POST = "60/m"

# Server time zone.
# https://docs.djangoproject.com/en/5.2/ref/settings/#time-zone
# TIME_ZONE = "America/New_York"
