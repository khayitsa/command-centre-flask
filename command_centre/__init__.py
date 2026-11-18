"""Command Centre -- task coordination and reporting (Flask edition)."""
from __future__ import annotations

import logging
import mimetypes
import os
import secrets
import time
from datetime import timedelta
from pathlib import Path

from flask import Blueprint, Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from . import api, auth, db
from .work import DomainError

mimetypes.add_type("application/manifest+json", ".webmanifest")

main = Blueprint("main", __name__)

CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def _secret_key(instance_path: str) -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = Path(instance_path) / "secret_key"
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another worker won the race; use its key
        for _ in range(50):
            existing = path.read_text().strip()
            if existing:
                return existing
            time.sleep(0.05)
        raise
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    return key


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


def create_app(test_config: dict | None = None) -> Flask:
    root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__, instance_path=str(root / "instance"), instance_relative_config=True,
        static_folder=str(root / "static"), template_folder=str(root / "templates"),
    )
    app.config.update(
        DATABASE=os.environ.get("DATABASE", str(Path(app.instance_path) / "command_centre.db")),
        ALLOW_SIGNUP=_flag("ALLOW_SIGNUP", False),
        MAX_CONTENT_LENGTH=2_000_000,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        SESSION_COOKIE_SECURE=_flag("SESSION_COOKIE_SECURE", True),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):  # Flask pre-defines the key as None
        app.config["SECRET_KEY"] = _secret_key(app.instance_path)
    app.json.sort_keys = False
    db.init_app(app)
    auth.init_app(app)
    app.register_blueprint(api.bp)
    app.register_blueprint(main)

    @app.context_processor
    def _assets():
        def asset(name: str) -> str:
            f = Path(app.static_folder) / "dist" / name
            version = int(f.stat().st_mtime) if f.exists() else 0
            return url_for("static", filename=f"dist/{name}", v=version)
        return {"asset": asset}

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if not request.path.startswith("/static/"):
            resp.headers.setdefault("Content-Security-Policy", CSP)
            resp.headers["Cache-Control"] = "private, no-store"
        return resp

    @app.errorhandler(DomainError)
    def _domain_error(exc: DomainError):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=exc.description or exc.name), exc.code
        return exc

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        app.logger.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on the server."), 500
        raise exc

    if not app.debug:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return app


@main.get("/")
def index():
    user = auth.current_user()
    if user is None:
        return redirect(url_for("auth.login_form"))
    return render_template("index.html", user_email=user["email"])
