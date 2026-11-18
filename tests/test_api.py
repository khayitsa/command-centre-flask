"""HTTP tests (port of the original tests/api.test.mjs, plus auth/CSRF/grants)."""
import json

import pytest

from command_centre.auth import create_user

PW = "correct horse battery"


@pytest.fixture()
def accounts(app):
    with app.app_context():
        for email in ("owner@example.test", "review@example.test", "stranger@example.test"):
            create_user(email, PW)


def make_client(app, email):
    c = app.test_client()
    r = c.post("/login", data={"email": email, "password": PW}, headers={"Origin": "http://localhost"})
    assert r.status_code == 302, r.data
    return c


def post(c, body, origin="http://localhost"):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    r = c.post("/api/workspace", data=json.dumps(body), headers=headers)
    return r.status_code, r.get_json()


def blank_task(w, me, **kw):
    t = {"id": "qa-task", "title": "QA handover", "company": w["companies"][0]["id"],
         "department": w["departments"][0]["id"], "project": "", "owner": me["id"], "contributors": [],
         "reviewer": "", "reviewRequired": False, "status": "To do", "priority": "High",
         "start": "2026-11-10", "due": "2026-11-12", "milestone": False, "estimate": 2,
         "dependencies": [], "waitingOn": "", "blockReason": "", "description": "Synthetic test only",
         "evidence": "", "steps": [], "created": "", "updated": "", "completed": ""}
    return {**t, **kw}


def test_full_round_trip_matches_original_harness(app, accounts):
    c = make_client(app, "owner@example.test")
    status, data = post(c, {"type": "create", "name": "API test"})
    assert status == 200
    w, me = data["workspace"], data["me"]

    def change(action):
        nonlocal w
        status, data = post(c, {"workspace": w["id"], "revision": w["revision"], "action": action})
        assert status == 200, data
        w = data["workspace"]
        return w

    change({"type": "entity", "kind": "companies", "name": "QA Company"})
    change({"type": "entity", "kind": "departments", "name": "QA Department"})
    change({"type": "task", "task": blank_task(w, me)})
    status, data = post(c, {"workspace": w["id"], "revision": 0, "action": {"type": "transition", "id": "qa-task", "status": "Done"}})
    assert status == 409 and "Someone changed" in data["error"]
    status, _ = post(c, {"workspace": w["id"], "revision": w["revision"], "action": {"type": "transition", "id": "qa-task", "status": "Done"}}, origin="https://untrusted.example")
    assert status == 403
    change({"type": "transition", "id": "qa-task", "status": "Done"})
    persisted = c.get(f"/api/workspace?id={w['id']}").get_json()
    assert persisted["workspace"]["tasks"][0]["status"] == "Done"
    assert len([e for e in persisted["workspace"]["events"] if e["to"] == "Done"]) == 1
    assert persisted["workspace"]["tasks"][0]["start"] == "2026-11-10"
    assert c.get("/api/workspace").get_json()["workspaces"] == [{"id": w["id"], "name": "API test"}]


def test_requires_sign_in_and_same_origin(app, accounts):
    anon = app.test_client()
    r = anon.get("/api/workspace")
    assert r.status_code == 401 and r.get_json()["error"] == "Sign in to continue"
    assert anon.get("/", follow_redirects=False).status_code == 302
    c = make_client(app, "owner@example.test")
    assert post(c, {"type": "create", "name": "x"}, origin=None)[0] == 403       # no Origin/Referer
    assert post(c, {"type": "create", "name": "x"}, origin="null")[0] == 403
    assert post(anon, {"type": "create", "name": "x"})[0] == 401
    r = c.post("/api/workspace", data="{}", headers={"Origin": "http://localhost", "Content-Type": "text/plain"})
    assert r.status_code == 400
    r = c.post("/api/workspace", data="[1]", headers={"Origin": "http://localhost", "Content-Type": "application/json"})
    assert r.status_code == 400 and "JSON object" in r.get_json()["error"]
    # charset suffix is fine now (the original rejected it)
    r = c.post("/api/workspace", data=json.dumps({"type": "create", "name": "ok"}),
               headers={"Origin": "http://localhost", "Content-Type": "application/json; charset=utf-8"})
    assert r.status_code == 200


def test_oversized_and_malformed_requests_get_json_errors(app, accounts):
    c = make_client(app, "owner@example.test")
    r = c.post("/api/workspace", data="x" * 2_100_000, headers={"Origin": "http://localhost", "Content-Type": "application/json"})
    assert r.status_code == 413 and "error" in r.get_json()
    ws = post(c, {"type": "create", "name": "W"})[1]["workspace"]
    assert post(c, {"workspace": ws["id"], "revision": "0", "action": {"type": "x"}})[0] == 400
    assert post(c, {"workspace": ws["id"], "revision": True, "action": {"type": "x"}})[0] == 400
    assert post(c, {"workspace": ws["id"], "revision": 0})[0] == 400
    assert post(c, {"workspace": "nope", "revision": 0, "action": {"type": "x"}})[0] == 404
    status, data = post(c, {"type": "create", "name": "   "})
    assert status == 400 and "required" in data["error"]


def test_invited_member_gets_access_by_email_and_only_sees_their_scope(app, accounts):
    owner = make_client(app, "owner@example.test")
    _, data = post(owner, {"type": "create", "name": "Team"})
    w, me = data["workspace"], data["me"]

    def change(client, action, ws):
        status, d = post(client, {"workspace": ws["id"], "revision": ws["revision"], "action": action})
        return status, d

    for kind, name in (("companies", "A"), ("companies", "B")):
        _, d = change(owner, {"type": "entity", "kind": kind, "name": name}, w)
        w = d["workspace"]
    a_id, b_id = w["companies"][0]["id"], w["companies"][1]["id"]
    reviewer = {"id": "rev", "name": "Rita", "email": "Review@Example.test", "department": "", "role": "Member",
                "companies": [a_id], "departments": []}
    status, d = change(owner, {"type": "person", "person": reviewer}, w)
    assert status == 200
    w = d["workspace"]
    for company, tid in ((a_id, "ta"), (b_id, "tb")):
        t = {**blank_task({"companies": [{"id": company}], "departments": [{"id": ""}]}, me, id=tid, department="", company=company, title=f"Task {tid}")}
        status, d = change(owner, {"type": "task", "task": t}, w)
        assert status == 200, d
        w = d["workspace"]

    rita = make_client(app, "review@example.test")
    listing = rita.get("/api/workspace").get_json()["workspaces"]
    assert listing == [{"id": w["id"], "name": "Team"}]
    view = rita.get(f"/api/workspace?id={w['id']}").get_json()
    assert [t["id"] for t in view["workspace"]["tasks"]] == ["ta"]
    assert view["me"]["id"] == "rev" and view["workspace"]["ownerId"] == ""
    assert "Task tb" not in json.dumps(view)
    # members cannot administer
    status, d = post(rita, {"workspace": w["id"], "revision": w["revision"], "action": {"type": "entity", "kind": "companies", "name": "Z"}})
    assert status == 403 and "administrators" in d["error"]

    # a signed-in stranger learns nothing about the workspace
    stranger = make_client(app, "stranger@example.test")
    assert stranger.get("/api/workspace").get_json()["workspaces"] == []
    assert stranger.get(f"/api/workspace?id={w['id']}").status_code == 404
    assert post(stranger, {"workspace": w["id"], "revision": w["revision"], "action": {"type": "comment", "id": "ta", "note": "hi"}})[0] == 404

    # changing the email revokes the grant
    _, d = change(owner, {"type": "person", "person": {**reviewer, "email": "someone-else@example.test"}}, w)
    assert rita.get("/api/workspace").get_json()["workspaces"] == []


def test_failed_action_changes_nothing(app, accounts):
    c = make_client(app, "owner@example.test")
    w = post(c, {"type": "create", "name": "W"})[1]["workspace"]
    status, d = post(c, {"workspace": w["id"], "revision": 0, "action": {"type": "entity", "kind": "projects", "name": "P", "company": "missing"}})
    assert status == 400 and d["error"] == "Choose a company"
    again = c.get(f"/api/workspace?id={w['id']}").get_json()["workspace"]
    assert again["revision"] == 0 and again["events"] == []


def test_auth_pages_signup_policy_and_throttle(app):
    c = app.test_client()
    assert c.get("/register").status_code == 200            # first account may be created...
    r = c.post("/register", data={"email": "First@Example.test", "password": PW, "confirm": PW}, headers={"Origin": "http://localhost"})
    assert r.status_code == 302 and c.get("/").status_code == 200
    assert b'data-user="first@example.test"' in c.get("/").data
    c2 = app.test_client()
    assert c2.get("/register").status_code == 404           # ...then sign-up closes
    assert c2.post("/register", data={"email": "x@example.test", "password": PW, "confirm": PW}, headers={"Origin": "http://localhost"}).status_code == 404
    # CSRF on forms
    assert c2.post("/login", data={"email": "first@example.test", "password": PW}).status_code == 403
    assert c.post("/logout").status_code == 403
    assert c.post("/logout", headers={"Origin": "http://localhost"}).status_code == 302
    assert c.get("/", follow_redirects=False).status_code == 302
    for _ in range(8):
        assert c2.post("/login", data={"email": "first@example.test", "password": "wrong-password!"}, headers={"Origin": "http://localhost"}).status_code == 401
    assert c2.post("/login", data={"email": "first@example.test", "password": PW}, headers={"Origin": "http://localhost"}).status_code == 429


def test_short_passwords_and_duplicates_are_rejected(app):
    c = app.test_client()
    r = c.post("/register", data={"email": "a@example.test", "password": "short", "confirm": "short"}, headers={"Origin": "http://localhost"})
    assert r.status_code == 400 and b"at least 10" in r.data
    r = c.post("/register", data={"email": "nope", "password": PW, "confirm": PW}, headers={"Origin": "http://localhost"})
    assert r.status_code == 400


def test_security_headers_and_no_store(app, accounts):
    c = make_client(app, "owner@example.test")
    r = c.get("/")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "private, no-store" and r.headers["X-Frame-Options"] == "DENY"
    assert c.get("/api/workspace").headers["X-Content-Type-Options"] == "nosniff"


def test_secret_key_comes_from_env_or_a_private_generated_file(tmp_path, monkeypatch):
    import os
    import stat

    from command_centre import _secret_key, create_app

    # production path: no SECRET_KEY in the config at all
    monkeypatch.setenv("SECRET_KEY", "from-the-environment")
    app = create_app({"DATABASE": str(tmp_path / "a.db")})
    assert app.config["SECRET_KEY"] == "from-the-environment"

    monkeypatch.delenv("SECRET_KEY")
    first = _secret_key(str(tmp_path))
    assert len(first) == 64 and _secret_key(str(tmp_path)) == first
    mode = stat.S_IMODE(os.stat(tmp_path / "secret_key").st_mode)
    assert mode == 0o600


def test_sessions_work_without_a_test_supplied_secret(tmp_path, monkeypatch):
    from command_centre import create_app

    monkeypatch.setenv("SECRET_KEY", "another-secret")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "b.db"), "SESSION_COOKIE_SECURE": False})
    with app.app_context():
        create_user("someone@example.test", PW)
    c = app.test_client()
    r = c.post("/login", data={"email": "someone@example.test", "password": PW}, headers={"Origin": "http://localhost"})
    assert r.status_code == 302 and c.get("/").status_code == 200
