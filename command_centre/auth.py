"""Sign-in, sign-out and the request's authenticated :class:`Actor`.

The original application trusted identity headers injected by its hosting
platform. A self-hosted Flask app has to establish identity itself, so this
module provides email + password accounts with signed session cookies.

Accounts are created with ``flask --app wsgi create-user EMAIL``. The very first
account can also be created from the sign-in page; after that, self-service
sign-up stays off unless ``ALLOW_SIGNUP=1`` (see README for the caveat: email
addresses are not verified, and an email address is what grants workspace access).
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

import click
from flask import Blueprint, Flask, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .work import Actor, DomainError, now_iso, uid

bp = Blueprint("auth", __name__)

MIN_PASSWORD = 10
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# A throwaway hash so unknown-email logins cost the same as wrong-password ones.
_DUMMY_HASH = generate_password_hash("not-a-real-password")

_failures: dict[str, deque] = defaultdict(deque)
WINDOW, MAX_FAILURES = 15 * 60, 8


class Unauthenticated(DomainError):
    status = 401


def same_origin() -> bool:
    """CSRF defence for state-changing requests: Origin (or Referer) must be this host."""
    for header in ("Origin", "Referer"):
        value = request.headers.get(header)
        if value:
            return urlsplit(value).netloc == request.host
    return False


def current_user():
    uid_ = session.get("uid")
    if not uid_:
        return None
    if "user" not in g:
        g.user = get_db().execute("SELECT id, email FROM users WHERE id=?", (uid_,)).fetchone()
    return g.user


def require_actor() -> Actor:
    user = current_user()
    if user is None:
        raise Unauthenticated("Sign in to continue")
    return Actor(user["id"], user["email"])


def normalise_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def create_user(email: str, password: str) -> str:
    email = normalise_email(email)
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ValueError("An account with that email already exists.")
    user_id = uid()
    db.execute(
        "INSERT INTO users(id, email, password_hash, created) VALUES(?,?,?,?)",
        (user_id, email, generate_password_hash(password), now_iso()),
    )
    return user_id


def _throttle_key(email: str) -> str:
    return f"{request.remote_addr}|{email}"


def _throttled(key: str) -> bool:
    q = _failures[key]
    cutoff = time.monotonic() - WINDOW
    while q and q[0] < cutoff:
        q.popleft()
    return len(q) >= MAX_FAILURES


def _signup_open() -> bool:
    if current_app.config["ALLOW_SIGNUP"]:
        return True
    return get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone() is None


def _start_session(user_id: str) -> None:
    session.clear()  # new session on every login (prevents fixation)
    session["uid"] = user_id
    session.permanent = True


@bp.before_request
def _csrf():
    if request.method == "POST" and not same_origin():
        abort(403, "Invalid request origin")


@bp.get("/login")
def login_form():
    if current_user():
        return redirect(url_for("main.index"))
    return render_template("login.html", signup_open=_signup_open())


@bp.post("/login")
def login():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    key = _throttle_key(email)
    if _throttled(key):
        flash("Too many attempts. Wait a few minutes and try again.")
        return render_template("login.html", signup_open=_signup_open()), 429
    row = get_db().execute("SELECT id, password_hash FROM users WHERE email=?", (email,)).fetchone()
    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)
    if not (row and ok):
        _failures[key].append(time.monotonic())
        flash("That email and password do not match.")
        return render_template("login.html", signup_open=_signup_open()), 401
    _failures.pop(key, None)
    _start_session(row["id"])
    return redirect(url_for("main.index"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not _signup_open():
        abort(404)
    if request.method == "GET":
        return render_template("register.html")
    try:
        password = request.form.get("password") or ""
        if password != (request.form.get("confirm") or ""):
            raise ValueError("The two passwords do not match.")
        user_id = create_user(request.form.get("email", ""), password)
    except ValueError as exc:
        flash(str(exc))
        return render_template("register.html"), 400
    _start_session(user_id)
    return redirect(url_for("main.index"))


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_form"))


def init_app(app: Flask) -> None:
    app.register_blueprint(bp)

    @app.cli.command("create-user")
    @click.argument("email")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_user_command(email, password):
        """Create a sign-in account."""
        try:
            create_user(email, password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from None
        click.echo(f"Created account for {email.strip().lower()}")

    @app.cli.command("set-password")
    @click.argument("email")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def set_password_command(email, password):
        """Change an account's password."""
        if len(password) < MIN_PASSWORD:
            raise click.ClickException(f"Use a password of at least {MIN_PASSWORD} characters.")
        cur = get_db().execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (generate_password_hash(password), email.strip().lower()),
        )
        if not cur.rowcount:
            raise click.ClickException("No account with that email.")
        click.echo("Password updated.")
