# Deploying Zingor

Operator-facing notes for running Zingor in production. (Player-facing
documentation lives in `docs/` and is published to Read the Docs.)

## Production topology

Zingor runs on a single Ubuntu VPS as two systemd services behind Caddy:

| Piece | What it is | Version-controlled as |
| --- | --- | --- |
| `zingor.service` | gunicorn serving `zingor.wsgi:application` on `127.0.0.1:8000` | `ops/zingor.service` |
| `zingor-huey.service` | the Huey consumer (`manage.py run_huey`) that runs background/periodic tasks | `ops/zingor-huey.service` |
| Caddy | TLS termination; proxies to gunicorn and serves `/static/*` off disk | `ops/Caddyfile.snippet` |
| SQLite | `db.sqlite3` (app data) and `huey.db` (task queue), both in the checkout root | — (gitignored) |

The checkout lives at `/home/maxwell/zingor` and runs as the `maxwell`
user. Those paths are hard-coded in `deploy.sh` and in the unit files; to
host Zingor elsewhere, change them in all three places.

Both databases are plain files in the checkout root and are *not* in git.
`deploy.sh` does a `git checkout --force`, which does not touch untracked
files, so deploys leave them alone — but nothing else backs them up.

## Host requirements

- Python 3.11 or newer (`requires-python` in `pyproject.toml`; the
  `.python-version` file pins what `uv` installs).
- [`uv`](https://docs.astral.sh/uv/), installed for the service user.
  `zingor-huey.service` invokes it by absolute path
  (`/home/maxwell/.local/bin/uv`), which is where the standalone installer
  puts it.
- `git`, `systemd`, and a Caddy install that includes `ops/Caddyfile.snippet`.
- Passwordless `sudo` for the service user. `deploy.sh` runs over a
  non-interactive SSH session and shells out to `sudo cp`,
  `sudo systemctl daemon-reload`, and `sudo systemctl restart`; a password
  prompt would hang the deploy.

No database server, cache, or message broker is needed: SQLite and Huey's
SqliteHuey backend cover both.

## Environment variables

`zingor/settings.py` calls `load_dotenv(BASE_DIR / ".env")` at import time,
so **all configuration comes from `.env` in the checkout root**, not from
the systemd units — the units deliberately set no `Environment=` or
`EnvironmentFile=` directives. `.env` is gitignored and is the only
server-local state `deploy.sh` will never overwrite. Copy `.env.example` to
`.env` and fill it in.

Every process (gunicorn, the Huey consumer, `manage.py`) reads the same
file, so a config change needs a restart of *both* services.

### Core

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | **yes** | — | Django signing key. Startup fails without it. Generate a fresh random value per deployment; never reuse the example. |
| `DEBUG` | no | `false` | Must stay `false` in production. It also switches on `ManifestStaticFilesStorage` (content-hashed static filenames) and takes Huey out of `immediate` mode, so tasks actually need the consumer. |
| `ALLOWED_HOSTS` | yes in production | empty | Comma-separated hostnames Django will serve, e.g. `zingor.maxwelljoslyn.com`. |
| `CSRF_TRUSTED_ORIGINS` | yes in production | empty | Comma-separated origins *including scheme*, e.g. `https://zingor.maxwelljoslyn.com`. Required because Caddy terminates TLS and proxies over plain HTTP. |
| `SENTRY_DSN` | no | empty | Sentry project DSN. Empty disables reporting. Note that `send_default_pii` is on, so request headers and IPs are sent. |

### Email

Registration confirmation and password reset need working mail. With the
defaults, mail is printed to the service log instead of being sent.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `EMAIL_BACKEND` | no | `django.core.mail.backends.console.EmailBackend` | Set to `django.core.mail.backends.smtp.EmailBackend` to actually send. |
| `EMAIL_HOST` | no | `localhost` | SMTP host. |
| `EMAIL_PORT` | no | `25` | SMTP port. |
| `EMAIL_HOST_USER` | no | empty | SMTP username. |
| `EMAIL_HOST_PASSWORD` | no | empty | SMTP password. |
| `EMAIL_USE_TLS` | no | `false` | `true` for STARTTLS. |
| `DEFAULT_FROM_EMAIL` | no | `no-reply@zingor.local` | From address on outgoing mail. |

### Features

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `REGISTRATION_ENABLED` | no | `true` | `false` hides self-serve registration. |
| `EMAIL_CONFIRMATION_REQUIRED` | no | `true` (`false` when `DEBUG`) | Whether new accounts must confirm by email before logging in. Leave it on unless mail is deliberately unconfigured. |
| `GITHUB_FEEDBACK_REPO` | no | empty | `owner/repo` that the in-app feedback form files issues against. |
| `GITHUB_FEEDBACK_TOKEN` | no | empty | GitHub token with issue-creation rights on that repo. If either of these is empty, the feedback form reports that it is unconfigured. |

## First-time server setup

1. Create the service user and clone the repo to `/home/maxwell/zingor`.
2. Install `uv`, then `uv sync --frozen` to build `.venv` (the units run
   `.venv/bin/gunicorn` directly).
3. Write `.env` (see above) and `chmod 600` it — it holds `SECRET_KEY` and
   any SMTP/GitHub credentials.
4. `uv run python manage.py migrate` and
   `uv run python manage.py createsuperuser`.
5. Install the units and start them:

   ```
   sudo cp ops/zingor.service ops/zingor-huey.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now zingor.service zingor-huey.service
   ```

   After this, `deploy.sh` keeps the installed units in sync with `ops/`
   on every deploy, copying only when they differ.
6. Add `ops/Caddyfile.snippet` to the Caddy config and reload Caddy. Caddy
   serves `/static/*` straight from `staticfiles/`, which `collectstatic`
   populates — so the app never serves static files itself.
7. Install the deploy SSH key's public half in the service user's
   `authorized_keys`, and set the `SSH_PRIVATE_KEY` and `KNOWN_HOSTS`
   secrets on the GitHub repo.

## Deploying

`.github/workflows/deploy.yaml` runs the test suite on every push to
`master` and deploys only on a `v*` tag push or a manual
`workflow_dispatch`. It SSHes in and runs `deploy.sh`, passing the tag name
(tag deploys ship exactly that commit) or `origin/master` (manual deploys
ship master HEAD).

`deploy.sh` can also be run by hand on the server:

```
/home/maxwell/zingor/deploy.sh            # deploy origin/master
/home/maxwell/zingor/deploy.sh v0.4.0     # deploy a specific ref
```

It fetches, checks the ref out detached, re-execs itself so the newly
checked-out script runs the rest, then `uv sync --frozen`, `migrate`,
`collectstatic`, unit sync, and a restart of both services.

## The Huey consumer

Background work — currently the once-a-minute
[external sync](docs/external-synchronization.md) poll in
`characters/tasks.py` — runs in `zingor-huey.service`, not in the web
process. Nothing else picks it up in production: `HUEY["immediate"]` is
tied to `DEBUG`, so with `DEBUG=false` a stopped consumer means tasks are
queued in `huey.db` and never run, silently, with no user-visible error.

Check on it with:

```
sudo systemctl status zingor-huey.service
journalctl -u zingor-huey.service -f
```

The consumer runs a single threaded worker, so tasks execute one at a time.
The djhuey stats dashboard in the Django admin records task events to a
`huey_event` table in the main database.

To exercise a sync by hand without waiting for the schedule:

```
uv run python manage.py sync_wiki
```
