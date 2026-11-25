# Catalog Manager

Web UI for cataloging Project Gutenberg books: the record, authors, subjects, categories, languages, LoC classes and MARC fields. Edits are validated server-side, then applied to Postgres; every applied edit also writes its SQL to a `public.changelog` row, a history that is never replayed.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
DJANGO_DEBUG=1 .venv/bin/python manage.py runserver 127.0.0.1:8000
# then add yourself to the gate group:
.venv/bin/python manage.py shell -c "from django.contrib.auth.models import User, Group; User.objects.get(username='you').groups.add(Group.objects.get(name='cataloguer'))"
```

Django's auth/session tables live in the same Postgres as the book data (`PGHOST`/`PGDATABASE`/`PGUSER`), in their own schema (`DJANGO_DB_SCHEMA`, default `django`), created automatically on first connect. Catalogers are the users in the `cataloguer` group (`DJANGO_CATALOGUER_GROUP`); `migrate` creates the group. New accounts: add a user in the Django admin with just a name, email and group, and the person receives a one-time emailed link to choose their own password, so no password ever travels in plain text; an admin action re-sends the link later, and without `EMAIL_*` configured the admin gets the link to pass along by hand. The same flow backs the sign-in page's "Forgot your password?". Secure cookies are on unless `DJANGO_DEBUG=1`. Reverse proxy → `127.0.0.1:8000`, with `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` pinned to the hostname.

## Deploy

Set `DJANGO_SECRET_KEY`; with debug off the app refuses to start on the built-in key.
Run `manage.py check --deploy` before switching traffic, and `manage.py collectstatic`, which DEBUG off requires.
The service's `EnvironmentFile` is optional by design (a missing `.env` must not stop the unit), so pin `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `PGPASSWORD` explicitly.
Set `DJANGO_SSL_REDIRECT=1` only once the proxy passes `X-Forwarded-Proto`, or the app will loop on https.
Pin exact versions: `pip install -r requirements.lock`.
