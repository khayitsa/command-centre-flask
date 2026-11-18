"""JSON API for workspaces. Same contract as the original ``/api/workspace`` route."""
from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from . import work
from .auth import require_actor, same_origin
from .db import get_db
from .work import Actor, DomainError, Forbidden, NotFound

bp = Blueprint("api", __name__)

MAX_WORKSPACES_PER_OWNER = 20


class Conflict(DomainError):
    status = 409


def _dump(w: dict) -> str:
    return json.dumps(w, ensure_ascii=False, separators=(",", ":"))


def _member_or_404(w: dict, actor: Actor) -> dict:
    # Same answer for "no such workspace" and "not yours": ids are not an oracle.
    try:
        return work.member(w, actor)
    except Forbidden:
        raise NotFound("Workspace not found") from None


def _payload(w: dict, actor: Actor) -> dict:
    return {
        "workspace": work.scope(w, actor),
        "me": work.member(w, actor),
        "development": bool(current_app.debug),
    }


@bp.get("/api/workspace")
def read():
    actor = require_actor()
    db = get_db()
    wid = request.args.get("id")
    if not wid:
        rows = db.execute(
            "SELECT w.id, w.name FROM workspaces w WHERE w.owner=? OR EXISTS "
            "(SELECT 1 FROM workspace_grants g WHERE g.workspace=w.id AND g.email=?) ORDER BY w.rowid",
            (actor.id, actor.email),
        ).fetchall()
        return jsonify({"workspaces": [{"id": r["id"], "name": r["name"]} for r in rows],
                        "development": bool(current_app.debug)})
    row = db.execute("SELECT data FROM workspaces WHERE id=?", (wid,)).fetchone()
    if row is None:
        raise NotFound("Workspace not found")
    w = json.loads(row["data"])
    _member_or_404(w, actor)
    return jsonify(_payload(w, actor))


def _body() -> dict[str, Any]:
    if request.mimetype != "application/json":
        raise DomainError("Send JSON with Content-Type: application/json")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise DomainError("Request body must be a JSON object")
    return body


@bp.post("/api/workspace")
def write():
    if not same_origin():
        raise Forbidden("Invalid request origin or type")
    actor = require_actor()
    body = _body()
    db = get_db()

    if body.get("type") == "create":
        owned = db.execute("SELECT count(*) FROM workspaces WHERE owner=?", (actor.id,)).fetchone()[0]
        if owned >= MAX_WORKSPACES_PER_OWNER:
            raise DomainError("Workspace limit reached")
        w = work.create_workspace(body.get("name"), actor)
        db.execute(
            "INSERT INTO workspaces(id, owner, name, revision, data) VALUES(?,?,?,?,?)",
            (w["id"], actor.id, w["name"], w["revision"], _dump(w)),
        )
        return jsonify(_payload(w, actor))

    wid, revision, action = body.get("workspace"), body.get("revision"), body.get("action")
    if not isinstance(wid, str) or isinstance(revision, bool) or not isinstance(revision, int) or not isinstance(action, dict):
        raise DomainError("Malformed request")

    db.execute("BEGIN IMMEDIATE")  # serialise writers; the revision check below is then race-free
    try:
        row = db.execute("SELECT data, revision FROM workspaces WHERE id=?", (wid,)).fetchone()
        if row is None:
            raise NotFound("Workspace not found")
        w = json.loads(row["data"])
        _member_or_404(w, actor)
        if revision != row["revision"]:
            raise Conflict("Someone changed this workspace. Refresh and retry; your changes were not saved.")
        nxt = work.apply(w, actor, action)
        cur = db.execute(
            "UPDATE workspaces SET data=?, revision=? WHERE id=? AND revision=?",
            (_dump(nxt), nxt["revision"], wid, row["revision"]),
        )
        if cur.rowcount != 1:
            raise Conflict("Concurrent change. Refresh and retry.")
        if action["type"] == "person":
            # apply() validated the person, so the id and email are well-formed here.
            person = next(p for p in nxt["people"] if p["id"] == action["person"]["id"])
            key = f"{wid}:{person['id']}"
            db.execute("DELETE FROM workspace_grants WHERE key=?", (key,))
            if person["email"]:
                db.execute(
                    "INSERT INTO workspace_grants(key, workspace, email) VALUES(?,?,?)",
                    (key, wid, person["email"].lower()),
                )
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    return jsonify(_payload(nxt, actor))
