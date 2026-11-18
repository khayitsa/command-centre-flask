# Command Centre — Flask edition

Task coordination and reporting: companies, departments, projects and people; accountable
owners, handover steps, separate reviewers, dependencies, a Gantt chart, reports and CSV
import/export. This is the original Next.js/Cloudflare "Command Centre developer package"
converted to a self-contained Flask app, with the bugs found along the way fixed
(see [`BUGFIXES.md`](BUGFIXES.md)).

* **Backend:** Flask + SQLite. All rules and permissions live in `command_centre/work.py`.
* **Frontend:** the original React interface, pre-built into `static/dist/`. **You do not need
  Node to run the app**; Node is only needed if you want to change the UI.

## Run it locally

```sh
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask --app wsgi create-user you@example.com               # asks for a password (min. 10 chars)
python run.py                                              # http://127.0.0.1:5000
```

`python run.py` is a local development server (debug mode, plain-http cookies). Never expose it.

## Accounts and access

The original relied on its hosting platform to say who the user was. A Flask app has to do
that itself, so there are email + password accounts with signed session cookies.

* Accounts are created by whoever runs the server: `flask --app wsgi create-user EMAIL`
  (`flask --app wsgi set-password EMAIL` resets a password).
* On a brand-new database the sign-in page offers "Create an account" **once**, for the first
  user. After that self-service sign-up is closed (`ALLOW_SIGNUP=1` reopens it).
* **Workspace access is granted by email.** An admin adds a *person* with a sign-in email inside
  the workspace; whoever signs in with an account using that exact email gets that person's role
  and scope. Because emails are not verified, only enable `ALLOW_SIGNUP=1` if you accept that
  anyone who can register an address can claim access granted to it. Prefer `create-user`.
* Roles: **Admin** (structure, people, import, everything), **Manager** (all tasks in scope),
  **Member** (own tasks and assigned steps). Only the assigned reviewer can approve.
  Company/department scopes are an intersection; an empty list means unrestricted.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | generated into `instance/secret_key` | Signs session cookies. Set it explicitly in production. |
| `DATABASE` | `instance/command_centre.db` | SQLite file. Keep it backed up. |
| `ALLOW_SIGNUP` | `0` | `1` = anyone can register. See the warning above. |
| `SESSION_COOKIE_SECURE` | `1` | Cookies only over HTTPS. Set `0` only for plain-http intranet use. |

## Deploy on PythonAnywhere

1. Upload and unzip the project (e.g. to `~/command-centre-flask`).
2. In a Bash console: create a virtualenv, `pip install -r requirements.txt`.
3. **Web** tab → *Add a new web app* → *Manual configuration* (same Python version) → set the
   virtualenv path.
4. Edit the WSGI file so it contains:
   ```python
   import sys
   path = '/home/YOURNAME/command-centre-flask'
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import application
   ```
   (Leave `SECRET_KEY`/`DATABASE` unset to use `instance/`; if you do set `DATABASE`, export the
   same value in the console before running `create-user`, or the CLI will use a different file.)
5. In the console: `cd ~/command-centre-flask && flask --app wsgi create-user you@example.com`
6. Reload the web app. PythonAnywhere is HTTPS, so secure cookies work out of the box.

Any other host works the same way: `gunicorn wsgi:application` behind HTTPS.

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest -q          # 28 tests: domain rules, API, auth, CSRF, access grants
```

## Changing the UI

The UI source is in `frontend/src/` (React + TypeScript). After editing:

```sh
cd frontend
npm ci
npm run typecheck
npm run build        # writes static/dist/app.js and app.css
```

## Layout

```
wsgi.py, run.py               entry points
command_centre/work.py        domain rules, permissions, validation (the integration boundary)
command_centre/api.py         /api/workspace (same JSON contract as the original)
command_centre/auth.py        sign-in/out, accounts, CSRF origin check, CLI commands
command_centre/db.py          SQLite schema and connections
templates/, static/           pages, icons, built UI (static/dist)
frontend/                     UI source and build config
tests/                        pytest suite
```

## How data is stored (unchanged design)

Each workspace is one validated JSON document in SQLite with a revision number. Every change
goes through `work.apply()`; stale writes get HTTP 409 instead of overwriting someone else's
work. Limits: 5,000 tasks and about 1.5 million characters per workspace, 500 tasks per CSV
import. For larger deployments, normalise tasks and events into their own tables first. The
activity log is an application record, not tamper-proof compliance storage.

## What was left out

The Cloudflare Worker/D1 hosting, the ChatGPT "Sites" identity and connector scaffolding, and
the Electron/Capacitor native shells (`native/`) were specific to the original hosting model and
are not part of this Flask app. The prototype's browser-storage data (`command-centre-v1`) is
still not imported; the app offers an "Export earlier data" button if it finds any.
