# Catalog Manager

Web UI for cataloging Project Gutenberg books: the record, authors, subjects, categories, languages, LoC classes and MARC fields. Edits are validated server-side, then applied to Postgres; every applied edit also writes its SQL to a `public.changelog` row, a history that is never replayed.

## Requirements

- Python 3.12 or newer.
- PostgreSQL with the Project Gutenberg catalog tables that `libgutenberg` expects.
- An existing catalog database and a role allowed to read and write it.
- A reverse proxy for anything other than local development.

The app keeps Django's auth/session/admin tables in the same Postgres server as the catalog, but in their own schema (default `django`). The two never mix.

## Configuration

There are two configuration layers:

1. **Environment variables** (recommended for secrets and hosts). Start from `.env.example`; `catalog/settings/common.py` reads these variables.
2. **`catalog/settings/local_settings.py`** (optional, gitignored). Copy `catalog/settings/local_settings.example.py` and replace its example hosts, database values and secret key. The example has the production-essential security settings active and keeps advanced extras commented. It is loaded after `common.py`, so it overrides those defaults.

The example file documents every security setting and links to the matching Django documentation page. The most important deployment settings are:

| Setting | Environment variable | What it does |
| --- | --- | --- |
| `SECRET_KEY` | `DJANGO_SECRET_KEY` | Signing key; required when `DEBUG` is off. |
| `DEBUG` | `DJANGO_DEBUG` | Must be `0` in production. |
| `ALLOWED_HOSTS` | `DJANGO_ALLOWED_HOSTS` | Host names Django may serve. |
| `CSRF_TRUSTED_ORIGINS` | `DJANGO_CSRF_TRUSTED_ORIGINS` | HTTPS origins trusted for forms. |
| `DATABASES` | `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` | Catalog and auth database. |
| `AUTH_SCHEMA` | `DJANGO_DB_SCHEMA` | Schema for Django's own tables (default `django`). |
| `DEFAULT_FROM_EMAIL` | – | Sender for password-set links. |

See `.env.example` for all environment variables, and `catalog/settings/local_settings.example.py` for the on-disk equivalents, dummy database values, and documentation links.

## Install and first run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # or requirements.lock
cp .env.example .env                        # edit it; never commit it
set -a; . ./.env; set +a                    # load it for the commands below
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py collectstatic --noinput
DJANGO_DEBUG=1 .venv/bin/python manage.py runserver 127.0.0.1:8000
```

`migrate` creates Django's tables and the `cataloguer` gate group, and adds existing superusers to it. Every new superuser joins the group on save, so `createsuperuser` needs no extra step. Add each other cataloger to that group through the Django admin; new accounts are created without a password and receive a one-time emailed link to choose their own. An admin action re-sends the link later. If email is not configured, the admin gets the link to pass along by hand.

Django creates the auth schema automatically on first connect when the database role has `CREATE` rights. If it does not, create it once with a privileged account and migrate again:

```sql
CREATE SCHEMA IF NOT EXISTS django;
```

Keep the schema name in `DJANGO_DB_SCHEMA` / `AUTH_SCHEMA`; it must match the `search_path` in `DATABASES`.

## Code layout

- `catalog/catalog.py` — read/search layer over the libgutenberg models.
- `catalog/clean.py` — forms and shared validation helpers.
- `catalog/changes.py` — applies one edit and records its changelog row.
- `catalog/ops/helpers.py` — the `Op` registry plus common edit helpers and factories.
- `catalog/ops/books.py` — the book record, book links and book-author links.
- `catalog/ops/authors.py` — authors and aliases.
- `catalog/ops/attributes.py` — MARC 21 attribute fields.
- `catalog/ops/entities.py` — subjects, categories, languages and LoC classes.
- `catalog/changelog.py` — builds the SQL recorded for each applied edit.

## Tests

```bash
.venv/bin/python manage.py test
```

The test command defaults to `catalog.settings.test`: Django's auth tables use in-memory SQLite, email is captured in memory, and a fixture (`catalog/fixtures/cataloger.json`) supplies a cataloger account. The catalog database and a running Postgres are not needed.

## Deploy

1. **Install** the locked requirements into a virtualenv:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.lock
   ```

2. **Configure** the environment file. It is optional by design so a missing file cannot stop the service, but production needs these values pinned: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `PGPASSWORD`. Keep the file readable only by the service account.

3. **Prepare the database.** Confirm the catalog tables exist and the app role can read and write them. Create the auth schema if the role lacks `CREATE`, then run:

   ```bash
   .venv/bin/python manage.py migrate
   .venv/bin/python manage.py createsuperuser
   .venv/bin/python manage.py collectstatic --noinput
   ```

4. **Check the deployment** before switching traffic:

   ```bash
   .venv/bin/python manage.py check --deploy
   ```

   With `DEBUG=0`, the app refuses to start on the built-in development key. Secure cookies are on by default; `DJANGO_SECURE_COOKIES=1` pins them. Enable `DJANGO_SSL_REDIRECT=1` only after the proxy sends `X-Forwarded-Proto`, or HTTPS requests will loop.

5. **Run the service.** The included `catalog_manager.service` is a starting point: it expects the app in `/var/lib/catalog_manager`, a `.env` beside it, and gunicorn on `127.0.0.1:8000`. Adjust `User`, paths and workers for the host.

6. **Put it behind a reverse proxy.** The proxy should terminate TLS, preserve the public `Host`, and send `X-Forwarded-Proto`, `X-Real-IP` and `X-Forwarded-For`. Set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` to the public names, and keep `CATALOG_TRUSTED_PROXIES` limited to the proxy addresses that may supply `X-Real-IP`.

7. **Email.** Configure the `EMAIL_*` settings so password-set links go out. Without email, the admin still gets each link to send by hand. Links are single-use and expire after `DJANGO_RESET_TIMEOUT` seconds (two hours by default).
