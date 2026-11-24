# Catalog Manager

Web UI for cataloging Project Gutenberg books: the record, authors, subjects, categories, languages, LoC classes and MARC fields. Edits are validated server-side, then applied to Postgres; every applied edit also writes its SQL to a `public.changelog` row, a history that is never replayed.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
DJANGO_DEBUG=1 CATALOG_DEV_SUPERUSER=1 CATALOG_CATALOGERS=you@example.org \
    .venv/bin/python manage.py runserver 127.0.0.1:8000
```

Postgres via `PGHOST`/`PGDATABASE`/`PGUSER`. Debug and the superuser allowlist bypass (`CATALOG_DEV_SUPERUSER`) are off unless opted in; secure cookies are on unless `DJANGO_DEBUG=1`. Set `CATALOG_CATALOGERS` for production. Reverse proxy → `127.0.0.1:8000`, with `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` pinned to the hostname.

## Deploy

Set `DJANGO_SECRET_KEY`; with debug off the app refuses to start on the built-in key.
Run `manage.py check --deploy` before switching traffic, and `manage.py collectstatic`, which DEBUG off requires.
The service's `EnvironmentFile` is optional by design (a missing `.env` must not stop the unit), so pin `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `CATALOG_CATALOGERS` explicitly.
Set `DJANGO_SSL_REDIRECT=1` only once the proxy passes `X-Forwarded-Proto`, or the app will loop on https.
Pin exact versions: `pip install -r requirements.lock`.
