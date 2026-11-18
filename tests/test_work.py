"""Domain tests. The first six are ports of the original tests/work.test.ts;
the rest are regression tests for bugs found while converting to Flask."""
import json
import time

import pytest

from command_centre.work import (
    Actor, DomainError, Forbidden, NotFound, apply, blank_task, create_workspace, scope,
)

OWNER = Actor("owner-id", "owner@example.test")
OTHER = Actor("another", "elsewhere@example.test")
REVIEWER = Actor("review-id", "review@example.test")


def person(id, name, email="", department="", role="Member", companies=(), departments=()):
    return {"id": id, "name": name, "email": email, "department": department, "role": role,
            "companies": list(companies), "departments": list(departments)}


def setup():
    w = create_workspace("Example", OWNER)
    w = apply(w, OWNER, {"type": "entity", "kind": "companies", "name": "Company A"})
    w = apply(w, OWNER, {"type": "entity", "kind": "companies", "name": "Company B"})
    w = apply(w, OWNER, {"type": "entity", "kind": "departments", "name": "Delivery"})
    w = apply(w, OWNER, {"type": "person", "person": person(
        "reviewer", "Reviewer", "review@example.test", companies=[w["companies"][0]["id"]])})
    return w


def task(w, **fields):
    return {**blank_task(w, w["people"][0]), "title": "Deliver work", **fields}


def save(w, actor, t):
    return apply(w, actor, {"type": "task", "task": t})


def move(w, actor, id, status, note=""):
    return apply(w, actor, {"type": "transition", "id": id, "status": status, "note": note})


# ----------------------------- ported originals ----------------------------- #

def test_organisation_boundary_and_company_scopes():
    w = setup()
    with pytest.raises(Forbidden, match="access denied"):
        scope(w, OTHER)
    w = save(w, OWNER, task(w))
    w = save(w, OWNER, task(w, company=w["companies"][1]["id"]))
    assert len(scope(w, REVIEWER)["tasks"]) == 1
    assert len(scope(w, REVIEWER)["companies"]) == 1
    with pytest.raises(NotFound, match="not found"):
        move(w, REVIEWER, w["tasks"][1]["id"], "Done")
    with pytest.raises(Forbidden, match="administrators"):
        apply(w, REVIEWER, {"type": "person", "person": w["people"][0]})


def test_review_requires_evidence_steps_and_separate_authorised_reviewer():
    w = setup()
    step = {"id": "step", "title": "Prepare", "owner": w["people"][0]["id"], "done": False}
    w = save(w, OWNER, task(w, reviewRequired=True, reviewer="reviewer", steps=[step]))
    tid = w["tasks"][0]["id"]
    with pytest.raises(DomainError, match="review first"):
        move(w, OWNER, tid, "Done")
    with pytest.raises(DomainError, match="handover"):
        move(w, OWNER, tid, "In review")
    w = apply(w, OWNER, {"type": "step", "id": tid, "step": "step", "done": True})
    with pytest.raises(DomainError, match="evidence"):
        move(w, OWNER, tid, "In review")
    w = save(w, OWNER, {**w["tasks"][0], "evidence": "Completed output"})
    w = move(w, OWNER, tid, "In review")
    with pytest.raises(Forbidden, match="assigned reviewer"):
        move(w, OWNER, tid, "Done")
    with pytest.raises(DomainError, match="reopen"):
        save(w, OWNER, {**w["tasks"][0], "title": "Changed"})
    w = move(w, REVIEWER, tid, "Changes requested", "Correct the result")
    w = move(w, OWNER, tid, "In review")
    w = move(w, REVIEWER, tid, "Done")
    assert w["tasks"][0]["completed"]
    w = move(w, OWNER, tid, "In progress")
    assert w["tasks"][0]["completed"] == ""
    assert len([e for e in w["events"] if e["to"] == "Done"]) == 1


def test_dependency_cycles_and_prerequisites_block_premature_progress():
    w = setup()
    w = save(w, OWNER, task(w, id="a"))
    w = save(w, OWNER, task(w, id="b", dependencies=["a"]))
    with pytest.raises(DomainError, match="cycle"):
        save(w, OWNER, {**w["tasks"][0], "dependencies": ["b"]})
    with pytest.raises(DomainError, match="prerequisite"):
        move(w, OWNER, "b", "In progress")
    w = move(w, OWNER, "a", "Done")
    assert move(w, OWNER, "b", "In progress")["tasks"][1]["status"] == "In progress"


def test_date_changes_only_cascade_explicitly_and_validate_each_task():
    w = setup()
    w = save(w, OWNER, task(w, id="a", start="2026-11-10", due="2026-11-11"))
    w = save(w, OWNER, task(w, id="b", start="2026-11-12", due="2026-11-13", dependencies=["a"]))
    one = apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-11", "due": "2026-11-12", "shift": False})
    assert one["tasks"][1]["start"] == "2026-11-12"
    both = apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-11", "due": "2026-11-12", "shift": True})
    assert both["tasks"][1]["start"] == "2026-11-13"
    with pytest.raises(DomainError, match="on or after"):
        apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-14", "due": "2026-11-12"})
    with pytest.raises(DomainError):
        apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-02-30", "due": "2026-03-01"})


def test_members_cannot_edit_others_tasks_or_spoof_status():
    w = setup()
    w = save(w, OWNER, task(w))
    with pytest.raises(Forbidden, match="owner or a manager"):
        save(w, REVIEWER, w["tasks"][0])
    w = save(w, OWNER, {**w["tasks"][0], "status": "Done"})
    assert w["tasks"][0]["status"] == "To do"
    with pytest.raises(DomainError, match="Explain"):
        move(w, OWNER, w["tasks"][0]["id"], "Blocked", "")


def test_imports_are_atomic_fresh_todo_records_and_malicious_fields_rejected():
    w = setup()
    with pytest.raises(DomainError, match="company"):
        apply(w, OWNER, {"type": "import", "tasks": [task(w), task(w, company="foreign")]})
    assert len(w["tasks"]) == 0
    w = apply(w, OWNER, {"type": "import", "tasks": [task(w, status="Done", completed="fake")]})
    assert w["tasks"][0]["status"] == "To do"
    assert w["tasks"][0]["completed"] == ""
    with pytest.raises(DomainError):
        save(w, OWNER, {**w["tasks"][0], "unexpected": True})


# ------------------------------ regression tests ------------------------------ #

def test_task_edit_cannot_wipe_or_forge_block_reason():
    w = setup()
    w = save(w, OWNER, task(w, id="a"))
    w = move(w, OWNER, "a", "Blocked", "Waiting for the client")
    w = save(w, OWNER, {**w["tasks"][0], "blockReason": ""})
    assert w["tasks"][0]["status"] == "Blocked"
    assert w["tasks"][0]["blockReason"] == "Waiting for the client"
    w = move(w, OWNER, "a", "In progress")
    w = save(w, OWNER, {**w["tasks"][0], "blockReason": "forged"})
    assert w["tasks"][0]["blockReason"] == ""


def test_import_cannot_smuggle_block_reason_or_completed_steps():
    w = setup()
    step = {"id": "s", "title": "Do it", "owner": w["people"][0]["id"], "done": True}
    w = apply(w, OWNER, {"type": "import", "tasks": [task(w, blockReason="forged", steps=[step])]})
    t = w["tasks"][0]
    assert t["blockReason"] == "" and t["steps"][0]["done"] is False and t["steps"][0]["id"] != "s"


def restricted_manager_workspace():
    w = setup()
    d1 = w["departments"][0]["id"]
    w = apply(w, OWNER, {"type": "entity", "kind": "departments", "name": "Finance"})
    d2 = w["departments"][1]["id"]
    w = apply(w, OWNER, {"type": "person", "person": person(
        "m", "Manager", "m@example.test", d1, "Manager", departments=[d1])})
    w = save(w, OWNER, task(w, id="hidden", department=d2))
    w = save(w, OWNER, task(w, id="visible", department=d1, dependencies=["hidden"]))
    return w, Actor("mid", "m@example.test")


def test_restricted_user_saving_a_task_keeps_prerequisites_they_cannot_see():
    w, mgr = restricted_manager_workspace()
    mine = next(t for t in scope(w, mgr)["tasks"] if t["id"] == "visible")
    assert mine["dependencies"] == []  # hidden from the browser...
    w2 = save(w, mgr, {**mine, "title": "Renamed"})
    stored = next(t for t in w2["tasks"] if t["id"] == "visible")
    assert stored["title"] == "Renamed"
    assert stored["dependencies"] == ["hidden"]  # ...but never silently deleted


def test_restricted_user_cannot_add_prerequisites_they_cannot_see():
    w, mgr = restricted_manager_workspace()
    d1 = w["departments"][0]["id"]
    w = save(w, OWNER, task(w, id="other", department=d1))
    other = next(t for t in scope(w, mgr)["tasks"] if t["id"] == "other")
    with pytest.raises(Forbidden, match="Prerequisites"):
        save(w, mgr, {**other, "dependencies": ["hidden"]})


def test_done_or_in_review_tasks_cannot_be_rescheduled_until_reopened():
    w = setup()
    w = save(w, OWNER, task(w, id="a", start="2026-11-01", due="2026-11-02"))
    w = move(w, OWNER, "a", "Done")
    with pytest.raises(DomainError, match="Reopen"):
        apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-12-01", "due": "2026-12-02"})
    w = move(w, OWNER, "a", "In progress")
    w = apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-12-01", "due": "2026-12-02"})
    assert w["tasks"][0]["due"] == "2026-12-02"


def test_zero_day_shift_adds_no_noise_and_shifts_are_logged_once():
    w = setup()
    w = save(w, OWNER, task(w, id="a", start="2026-11-01", due="2026-11-05"))
    w = save(w, OWNER, task(w, id="b", start="2026-11-06", due="2026-11-07", dependencies=["a"]))
    n = len(w["events"])
    same_due = apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-02", "due": "2026-11-05", "shift": True})
    assert len(same_due["events"]) - n == 1 and same_due["tasks"][1]["start"] == "2026-11-06"
    moved = apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-01", "due": "2026-11-06", "shift": True})
    assert moved["events"][-1]["detail"].startswith("Shifted +1 day after")
    assert moved["tasks"][1]["due"] == "2026-11-08"


def test_scoped_copy_keeps_own_scope_and_people_waited_on_but_hides_admin_events():
    w = setup()
    d1 = w["departments"][0]["id"]
    co = w["companies"][0]["id"]
    w = apply(w, OWNER, {"type": "person", "person": person("m", "Mem", "m@example.test", d1, companies=[co], departments=[d1])})
    w = apply(w, OWNER, {"type": "person", "person": person("x", "Waited on", "", d1)})
    w = apply(w, OWNER, {"type": "person", "person": person("secret", "Unrelated Person", "", d1)})
    w = save(w, OWNER, task(w, id="a", department=d1, owner="m", waitingOn="x"))
    sc = scope(w, Actor("mid", "m@example.test"))
    ids = {p["id"] for p in sc["people"]}
    assert ids == {"m", "x"}
    me = next(p for p in sc["people"] if p["id"] == "m")
    assert me["companies"] == [co] and me["departments"] == [d1]
    other = next(p for p in sc["people"] if p["id"] == "x")
    assert other["email"] == "" and other["companies"] == []
    assert all(e["task"] for e in sc["events"])  # no "Saved person Unrelated Person"
    assert "Unrelated Person" not in json.dumps(sc)


def test_validation_rejects_bad_input_with_readable_messages():
    w = setup()
    with pytest.raises(DomainError, match="Estimated hours"):
        save(w, OWNER, task(w, estimate=float("nan")))
    with pytest.raises(DomainError, match="Estimated hours"):
        save(w, OWNER, task(w, estimate=True))
    with pytest.raises(DomainError, match="Title is required"):
        save(w, OWNER, task(w, title="   "))
    with pytest.raises(DomainError, match="valid email"):
        apply(w, OWNER, {"type": "person", "person": person("p", "P", "not-an-email")})
    with pytest.raises(DomainError, match="date like"):
        save(w, OWNER, task(w, start="١٢٣٤-١٢-٠١"))  # non-ASCII digits are not dates
    with pytest.raises(DomainError, match="Unknown operation"):
        apply(w, OWNER, {"type": "nope"})
    with pytest.raises(DomainError, match="Unknown operation"):
        apply(w, OWNER, None)


def test_person_email_is_normalised_and_unique_case_insensitively():
    w = setup()
    w = apply(w, OWNER, {"type": "person", "person": person("p", "P", "  Pat@Example.TEST ")})
    assert next(p for p in w["people"] if p["id"] == "p")["email"] == "pat@example.test"
    with pytest.raises(DomainError, match="already assigned"):
        apply(w, OWNER, {"type": "person", "person": person("q", "Q", "PAT@example.test")})
    owner_id = w["people"][0]["id"]
    with pytest.raises(DomainError, match="remain administrator"):
        apply(w, OWNER, {"type": "person", "person": person(owner_id, "Workspace owner", "owner@example.test", role="Member")})


def test_scoped_workspace_cannot_be_used_to_impersonate_the_owner():
    w = setup()
    sc = scope(w, REVIEWER)
    assert sc["ownerId"] == ""
    with pytest.raises(Forbidden):
        scope(sc, Actor("", ""))  # an empty identity must never match an empty ownerId


def test_cycle_check_scales_on_dense_dependency_graphs():
    w = setup()
    layers = [[f"l{i}a", f"l{i}b"] for i in range(40)]
    for i, layer in enumerate(layers):
        for tid in layer:
            w["tasks"].append(task(w, id=tid, dependencies=layers[i - 1] if i else []))
    start = time.perf_counter()
    save(w, OWNER, {**w["tasks"][-1], "title": "edit"})
    assert time.perf_counter() - start < 1.0


def test_shifting_dependants_respects_permissions_and_locked_tasks():
    w = setup()
    w = save(w, OWNER, task(w, id="a", start="2026-11-01", due="2026-11-02"))
    w = save(w, OWNER, task(w, id="b", start="2026-11-03", due="2026-11-04", dependencies=["a"]))
    w = save(w, OWNER, task(w, id="c", start="2026-11-05", due="2026-11-06", dependencies=["b"]))
    w2 = apply(w, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-02", "due": "2026-11-03", "shift": True})
    assert [t["start"] for t in w2["tasks"]] == ["2026-11-02", "2026-11-04", "2026-11-06"]  # chain follows
    # finish the whole chain, then reopen only the first task: "b" is now a locked dependant
    w3 = move(move(move(w, OWNER, "a", "Done"), OWNER, "b", "Done"), OWNER, "a", "In progress")
    with pytest.raises(DomainError, match="individually"):
        apply(w3, OWNER, {"type": "schedule", "id": "a", "start": "2026-11-02", "due": "2026-11-03", "shift": True})
