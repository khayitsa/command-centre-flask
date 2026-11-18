"""SQLite access. One connection per request; writes use explicit transactions."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id       TEXT PRIMARY KEY,
    owner    TEXT NOT NULL,
    name     TEXT NOT NULL,
    revision INTEGER NOT NULL,
    data     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workspaces_owner ON workspaces(owner);
CREATE TABLE IF NOT EXISTS workspace_grants (
    key       TEXT PRIMARY KEY,
    workspace TEXT NOT NULL,
    email     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workspace_grants_email ON workspace_grants(email);
CREATE INDEX IF NOT EXISTS workspace_grants_workspace ON workspace_grants(workspace);
"""


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None -> autocommit; transactions are explicit (BEGIN IMMEDIATE).
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(app: Flask) -> None:
    conn = connect(app.config["DATABASE"])
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    init_db(app)
