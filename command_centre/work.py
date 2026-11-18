"""Command Centre domain rules.

This module is the integration boundary of the application (it replaces the
original ``lib/work.ts``). Everything is plain JSON-compatible ``dict``/``list``
data so a workspace can be stored as one document and sent to the browser as-is.

Public surface:

* :func:`create_workspace`, :func:`blank_task`
* :func:`apply` -- the only way a workspace is ever changed
* :func:`scope` -- the view of a workspace an actor is allowed to see
* :func:`member`, :func:`can_see`

Errors are raised as :class:`DomainError` (HTTP 400), :class:`Forbidden`
(HTTP 403) or :class:`NotFound` (HTTP 404) with a message that is safe to show
to the user.
"""
from __future__ import annotations

import copy
import json
import math
import re
import uuid
from collections import deque
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

STAGES = ("To do", "In progress", "Waiting", "Blocked", "In review", "Changes requested", "Done")
PRIORITIES = ("Low", "Medium", "High")
ROLES = ("Admin", "Manager", "Member")
LOCKED = ("In review", "Done")  # content is frozen until withdrawn / reopened

MAX_TASKS = 5000
MAX_EVENTS = 50000
MAX_DOCUMENT_CHARS = 1_500_000
MAX_IMPORT = 500

TASK_FIELDS = (
    "id", "title", "company", "department", "project", "owner", "contributors",
    "reviewer", "reviewRequired", "status", "priority", "start", "due", "milestone",
    "estimate", "dependencies", "waitingOn", "blockReason", "description", "evidence",
    "steps", "created", "updated", "completed",
)
PERSON_FIELDS = ("id", "name", "email", "department", "role", "companies", "departments")
STEP_FIELDS = ("id", "title", "owner", "done")


class DomainError(Exception):
    """A rule was broken; the message is shown to the user."""

    status = 400


class Forbidden(DomainError):
    status = 403


class NotFound(DomainError):
    status = 404


class Actor(NamedTuple):
    id: str
    email: str


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def uid() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _text(v: Any, field: str, *, min_len: int = 0, max_len: int = 500) -> str:
    """Trimmed single-field text (mirrors the original ``z.string().trim()``)."""
    if not isinstance(v, str):
        raise DomainError(f"{field} must be text")
    v = v.strip()
    if len(v) < min_len:
        raise DomainError(f"{field} is required")
    if len(v) > max_len:
        raise DomainError(f"{field} must be at most {max_len} characters")
    return v


def _long_text(v: Any, field: str, max_len: int) -> str:
    if not isinstance(v, str):
        raise DomainError(f"{field} must be text")
    if len(v) > max_len:
        raise DomainError(f"{field} must be at most {max_len} characters")
    return v


def _id(v: Any, field: str = "id") -> str:
    if not isinstance(v, str):
        raise DomainError(f"{field} must be text")
    if len(v) > 100:
        raise DomainError(f"{field} is too long")
    return v


def _id_list(v: Any, field: str) -> list[str]:
    if not isinstance(v, list):
        raise DomainError(f"{field} must be a list")
    if len(v) > 100:
        raise DomainError(f"{field} can hold at most 100 entries")
    return [_id(x, field) for x in v]


def _bool(v: Any, field: str) -> bool:
    if not isinstance(v, bool):
        raise DomainError(f"{field} must be true or false")
    return v


def _date_value(v: Any, field: str = "Date") -> str:
    """``''`` or a real calendar date ``YYYY-MM-DD``."""
    if v == "":
        return ""
    if not isinstance(v, str) or not _DATE_RE.fullmatch(v):
        raise DomainError(f"{field} must be a date like 2026-11-30")
    try:
        if _date.fromisoformat(v).isoformat() != v:
            raise ValueError
    except ValueError:
        raise DomainError("Invalid calendar date") from None
    return v


def _email(v: Any) -> str:
    if v == "":
        return ""
    if not isinstance(v, str):
        raise DomainError("Email must be text")
    v = v.strip().lower()
    if v == "":
        return ""
    if len(v) > 254 or not _EMAIL_RE.fullmatch(v):
        raise DomainError("Enter a valid email address")
    return v


def _number(v: Any, field: str, lo: float, hi: float) -> float | int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise DomainError(f"{field} must be a number")
    if v < lo or v > hi:
        raise DomainError(f"{field} must be between {lo:g} and {hi:g}")
    return v


def _strict(raw: Any, allowed: tuple[str, ...], label: str) -> dict:
    if not isinstance(raw, dict):
        raise DomainError(f"{label} is malformed")
    extra = [k for k in raw if k not in allowed]
    if extra:
        raise DomainError(f"Unexpected field on {label}: {extra[0]}")
    missing = [k for k in allowed if k not in raw]
    if missing:
        raise DomainError(f"Missing field on {label}: {missing[0]}")
    return raw


def clean_person(raw: Any) -> dict:
    raw = _strict(raw, PERSON_FIELDS, "person")
    role = raw["role"]
    if role not in ROLES:
        raise DomainError("Unknown role")
    return {
        "id": _id(raw["id"]),
        "name": _text(raw["name"], "Name", min_len=1),
        "email": _email(raw["email"]),
        "department": _id(raw["department"], "Department"),
        "role": role,
        "companies": _id_list(raw["companies"], "Companies"),
        "departments": _id_list(raw["departments"], "Departments"),
    }


def clean_task(raw: Any) -> dict:
    raw = _strict(raw, TASK_FIELDS, "task")
    if raw["status"] not in STAGES:
        raise DomainError("Unknown status")
    if raw["priority"] not in PRIORITIES:
        raise DomainError("Unknown priority")
    steps_raw = raw["steps"]
    if not isinstance(steps_raw, list):
        raise DomainError("Steps must be a list")
    if len(steps_raw) > 100:
        raise DomainError("A task can have at most 100 steps")
    steps = []
    for s in steps_raw:
        s = _strict(s, STEP_FIELDS, "step")
        steps.append({
            "id": _id(s["id"], "Step id"),
            "title": _text(s["title"], "Step title", min_len=1),
            "owner": _id(s["owner"], "Step owner"),
            "done": _bool(s["done"], "Step status"),
        })
    if len({s["id"] for s in steps}) != len(steps):
        raise DomainError("Duplicate step")
    return {
        "id": _id(raw["id"]),
        "title": _text(raw["title"], "Title", min_len=1),
        "company": _id(raw["company"], "Company"),
        "department": _id(raw["department"], "Department"),
        "project": _id(raw["project"], "Project"),
        "owner": _id(raw["owner"], "Owner"),
        "contributors": _id_list(raw["contributors"], "Contributors"),
        "reviewer": _id(raw["reviewer"], "Reviewer"),
        "reviewRequired": _bool(raw["reviewRequired"], "Requires approval"),
        "status": raw["status"],
        "priority": raw["priority"],
        "start": _date_value(raw["start"], "Start date"),
        "due": _date_value(raw["due"], "Due date"),
        "milestone": _bool(raw["milestone"], "Milestone"),
        "estimate": _number(raw["estimate"], "Estimated hours", 0, 100000),
        "dependencies": _id_list(raw["dependencies"], "Prerequisites"),
        "waitingOn": _id(raw["waitingOn"], "Waiting on"),
        "blockReason": _text(raw["blockReason"], "Block reason"),
        "description": _long_text(raw["description"], "Brief", 20000),
        "evidence": _long_text(raw["evidence"], "Evidence", 10000),
        "steps": steps,
        "created": _text(raw["created"], "Created"),
        "updated": _text(raw["updated"], "Updated"),
        "completed": _text(raw["completed"], "Completed"),
    }


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #

def member(w: dict, actor: Actor) -> dict:
    """Return the workspace person that ``actor`` is, or raise ``Forbidden``."""
    if w["ownerId"] and w["ownerId"] == actor.id:
        return w["people"][0]
    email = (actor.email or "").lower()
    if email:
        for p in w["people"]:
            if p["email"] and p["email"].lower() == email:
                return p
    raise Forbidden("Workspace access denied")


def can_see(p: dict, t: dict) -> bool:
    """Company/department access is an intersection; an empty list means unrestricted."""
    if p["role"] == "Admin":
        return True
    companies, departments = p["companies"], p["departments"]
    dept = t.get("department")
    return (not companies or t.get("company") in companies) and (
        not departments or (bool(dept) and dept in departments)
    )


def _involved_ids(t: dict) -> set[str]:
    ids = {t["owner"], t["reviewer"], t["waitingOn"], *t["contributors"], *(s["owner"] for s in t["steps"])}
    ids.discard("")
    return ids


def scope(w: dict, actor: Actor) -> dict:
    """The workspace as ``actor`` is allowed to see it (never mutates ``w``)."""
    p = member(w, actor)
    if p["role"] == "Admin":
        return w
    tasks = [t for t in w["tasks"] if can_see(p, t)]
    visible = {t["id"] for t in tasks}
    involved: set[str] = {p["id"]}
    for t in tasks:
        involved |= _involved_ids(t)
    people = []
    for x in w["people"]:
        if x["id"] not in involved:
            continue
        mine = x["id"] == p["id"]
        people.append({
            **x,
            "email": x["email"] if mine else "",
            # Other people's access scopes are private; your own are not.
            "companies": list(x["companies"]) if mine else [],
            "departments": list(x["departments"]) if mine else [],
        })
    return {
        **w,
        "ownerId": "",
        "tasks": [{**t, "dependencies": [d for d in t["dependencies"] if d in visible]} for t in tasks],
        # Structure/access events (no task) describe administration and name people
        # the member may not see, so they stay admin-only.
        "events": [e for e in w["events"] if e["task"] and can_see(p, e)],
        "companies": [c for c in w["companies"] if not p["companies"] or c["id"] in p["companies"]],
        "departments": [d for d in w["departments"] if not p["departments"] or d["id"] in p["departments"]],
        "projects": [pr for pr in w["projects"] if not p["companies"] or pr["company"] in p["companies"]],
        "people": people,
    }


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #

def create_workspace(name: str, actor: Actor) -> dict:
    return {
        "id": uid(),
        "name": _text(name, "Workspace name", min_len=1),
        "ownerId": actor.id,
        "revision": 0,
        "companies": [],
        "departments": [],
        "people": [{
            "id": uid(), "name": "Workspace owner", "email": (actor.email or "").lower(),
            "department": "", "role": "Admin", "companies": [], "departments": [],
        }],
        "projects": [],
        "tasks": [],
        "events": [],
    }


def blank_task(w: dict, p: dict) -> dict:
    return {
        "id": uid(), "title": "", "company": w["companies"][0]["id"] if w["companies"] else "",
        "department": p.get("department") or "", "project": "", "owner": p["id"], "contributors": [],
        "reviewer": "", "reviewRequired": False, "status": "To do", "priority": "Medium",
        "start": "", "due": "", "milestone": False, "estimate": 0, "dependencies": [],
        "waitingOn": "", "blockReason": "", "description": "", "evidence": "", "steps": [],
        "created": "", "updated": "", "completed": "",
    }


# --------------------------------------------------------------------------- #
# Task validation
# --------------------------------------------------------------------------- #

def _check_no_cycle(w: dict, t: dict) -> None:
    """Reject dependency cycles through ``t`` (iterative, linear time)."""
    deps = {x["id"]: x["dependencies"] for x in w["tasks"] if x["id"] != t["id"]}
    deps[t["id"]] = t["dependencies"]
    state = {t["id"]: 1}  # 1 = on the current path, 2 = fully explored
    stack = [(t["id"], iter(deps[t["id"]]))]
    while stack:
        node, children = stack[-1]
        for child in children:
            seen = state.get(child)
            if seen == 1:
                raise DomainError("Dependencies would form a cycle")
            if seen is None:
                state[child] = 1
                stack.append((child, iter(deps.get(child, []))))
                break
        else:
            state[node] = 2
            stack.pop()


def assert_task(w: dict, t: dict) -> None:
    """Check a (schema-clean) task against the rest of the workspace."""
    if not any(c["id"] == t["company"] for c in w["companies"]):
        raise DomainError("Choose a company")
    if t["department"] and not any(d["id"] == t["department"] for d in w["departments"]):
        raise DomainError("Unknown department")
    if t["project"] and not any(p["id"] == t["project"] and p["company"] == t["company"] for p in w["projects"]):
        raise DomainError("Project belongs to another company")
    if t["start"] and t["due"] and t["due"] < t["start"]:
        raise DomainError("Due date must be on or after start date")
    if t["milestone"] and t["start"] != t["due"]:
        raise DomainError("Milestones need the same start and due date")
    people = {p["id"]: p for p in w["people"]}
    assigned = [t["owner"], t["reviewer"], *t["contributors"], *(s["owner"] for s in t["steps"]), t["waitingOn"]]
    for pid in filter(None, assigned):
        person = people.get(pid)
        if person is None or not can_see(person, t):
            raise DomainError("Assigned people must have access to this company and department")
    if not t["owner"]:
        raise DomainError("Choose an accountable owner")
    if t["reviewRequired"] and (
        not t["reviewer"] or t["reviewer"] == t["owner"] or t["reviewer"] in t["contributors"]
        or any(s["owner"] == t["reviewer"] for s in t["steps"])
    ):
        raise DomainError("Choose a separate reviewer")
    same_company = {x["id"] for x in w["tasks"] if x["company"] == t["company"]}
    for dep in t["dependencies"]:
        if dep == t["id"] or dep not in same_company:
            raise DomainError("Dependencies must be other tasks in the same company")
    _check_no_cycle(w, t)


def schedule_warnings(w: dict, t: dict) -> list[str]:
    by_id = {x["id"]: x for x in w["tasks"]}
    out = []
    for dep_id in t["dependencies"]:
        dep = by_id.get(dep_id)
        if dep and dep["due"] and t["start"] and dep["due"] > t["start"]:
            out.append(f"{dep['title']} finishes after this task starts")
    return out


# --------------------------------------------------------------------------- #
# The one entry point that changes a workspace
# --------------------------------------------------------------------------- #

def apply(w0: dict, actor: Actor, action: Any, at: str | None = None) -> dict:
    """Validate ``action`` for ``actor`` and return the next workspace revision.

    ``w0`` is never modified; any failure leaves it untouched (so imports and
    date cascades are atomic).
    """
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        raise DomainError("Unknown operation")
    at = at or now_iso()
    w = copy.deepcopy(w0)
    p = member(w, actor)
    admin = p["role"] == "Admin"

    def record(t: dict | None, kind: str, detail: str, frm: str = "", to: str = "") -> None:
        w["events"].append({
            "id": uid(), "at": at, "actor": p["name"],
            "task": t["id"] if t else "", "company": t["company"] if t else "",
            "department": t["department"] if t else "", "owner": t["owner"] if t else "",
            "type": kind, "detail": detail, "from": frm, "to": to,
        })

    kind = action["type"]
    if kind == "entity":
        _apply_entity(w, admin, action, record)
    elif kind == "person":
        _apply_person(w, admin, action, record)
    elif kind == "task":
        _apply_task(w, p, admin, action, at, record)
    elif kind in ("transition", "step", "comment", "schedule"):
        _apply_task_action(w, p, admin, action, at, record)
    elif kind == "import":
        _apply_import(w, admin, action, at, record)
    else:
        raise DomainError("Unknown operation")

    if len(w["tasks"]) > MAX_TASKS:
        raise DomainError("Workspace limit reached: 5,000 tasks")
    if len(json.dumps(w, ensure_ascii=False, separators=(",", ":"))) > MAX_DOCUMENT_CHARS:
        raise DomainError("Workspace storage limit reached. Export your data and contact your administrator.")
    if len(w["events"]) > MAX_EVENTS:
        raise DomainError("Activity limit reached; export and contact your administrator")
    w["revision"] += 1
    return w


def _apply_entity(w, admin, action, record):
    if not admin:
        raise Forbidden("Only administrators can change workspace structure")
    kind = action.get("kind")
    if kind not in ("companies", "departments", "projects"):
        raise DomainError("Unknown structure type")
    name = _text(action.get("name"), "Name", min_len=1)
    company = action.get("company")
    for x in w[kind]:
        if x["name"].casefold() == name.casefold() and (kind != "projects" or x.get("company") == company):
            raise DomainError("That name already exists")
    if kind == "projects":
        company = _id(company, "Company")
        if not any(c["id"] == company for c in w["companies"]):
            raise DomainError("Choose a company")
        w["projects"].append({"id": uid(), "name": name, "company": company})
    else:
        w[kind].append({"id": uid(), "name": name})
    record(None, "Structure", f"Added {name}")


def _apply_person(w, admin, action, record):
    if not admin:
        raise Forbidden("Only administrators can change access")
    person = clean_person(action.get("person"))
    if person["department"] and not any(d["id"] == person["department"] for d in w["departments"]):
        raise DomainError("Unknown department")
    if any(not any(c["id"] == i for c in w["companies"]) for i in person["companies"]) or any(
        not any(d["id"] == i for d in w["departments"]) for i in person["departments"]
    ):
        raise DomainError("Unknown access scope")
    if person["email"] and any(x["id"] != person["id"] and x["email"].lower() == person["email"] for x in w["people"]):
        raise DomainError("Email already assigned")
    owner = w["people"][0]
    if person["id"] == owner["id"] and (person["role"] != "Admin" or person["email"] != owner["email"]):
        raise DomainError("The workspace owner must remain administrator")
    for i, x in enumerate(w["people"]):
        if x["id"] == person["id"]:
            w["people"][i] = person
            break
    else:
        w["people"].append(person)
    record(None, "Access", f"Saved person {person['name']}")


def _apply_task(w, p, admin, action, at, record):
    t = clean_task(action.get("task"))
    old = next((x for x in w["tasks"] if x["id"] == t["id"]), None)
    if not can_see(p, t) or (old is not None and not can_see(p, old)):
        raise Forbidden("Task access denied")
    if old and not admin and p["role"] != "Manager" and old["owner"] != p["id"]:
        raise Forbidden("Only the owner or a manager can edit this task")
    if not old and not admin and p["role"] == "Member" and t["owner"] != p["id"]:
        raise Forbidden("You can create tasks assigned to yourself")
    if old and old["status"] in LOCKED:
        raise DomainError("Return or reopen this task before editing")

    if not admin:
        # The browser only ever receives prerequisites the user may see. Make sure
        # they cannot add ones they may not see, and that saving does not silently
        # delete the hidden ones the browser never knew about.
        visible = {x["id"] for x in w["tasks"] if can_see(p, x)}
        if any(d not in visible for d in t["dependencies"]):
            raise Forbidden("Prerequisites must be tasks you can access")
        if old:
            t["dependencies"] += [d for d in old["dependencies"] if d not in visible]

    # Server-owned fields: never trust the browser for these.
    t["status"] = old["status"] if old else "To do"
    t["blockReason"] = old["blockReason"] if old else ""
    t["created"] = old["created"] if old else at
    t["updated"] = at
    t["completed"] = old["completed"] if old else ""
    assert_task(w, t)
    if old:
        w["tasks"] = [t if x["id"] == t["id"] else x for x in w["tasks"]]
    else:
        w["tasks"].append(t)
    record(t, "Edited" if old else "Created", t["title"])


def _apply_task_action(w, p, admin, action, at, record):
    kind = action["type"]
    t = next((x for x in w["tasks"] if x["id"] == action.get("id")), None)
    if t is None or not can_see(p, t):
        raise NotFound("Task not found")
    edit = admin or p["role"] == "Manager" or t["owner"] == p["id"]

    if kind == "comment":
        record(t, "Update", _text(action.get("note"), "Update", min_len=1))
    elif kind == "step":
        step = next((s for s in t["steps"] if s["id"] == action.get("step")), None)
        if step is None or (not edit and step["owner"] != p["id"]):
            raise Forbidden("Step access denied")
        if t["status"] in LOCKED:
            raise DomainError("Reopen the task before changing steps")
        step["done"] = _bool(action.get("done"), "Step status")
        record(t, "Step", f"{step['title']}: {'complete' if step['done'] else 'reopened'}")
    elif kind == "schedule":
        _apply_schedule(w, p, admin, edit, t, action, at, record)
    else:
        _apply_transition(w, p, edit, t, action, at, record)
    t["updated"] = at


def _apply_schedule(w, p, admin, edit, t, action, at, record):
    if not edit:
        raise Forbidden("Only the owner or a manager can move dates")
    if t["status"] in LOCKED:
        raise DomainError("Reopen or withdraw this task before moving its dates")
    start = _date_value(action.get("start"), "Start date")
    due = _date_value(action.get("due"), "Due date")
    old_due = t["due"]
    t["start"], t["due"] = start, due
    assert_task(w, t)
    record(t, "Dates", f"{old_due or 'No deadline'} → {due or 'No deadline'}")
    if action.get("shift") is not True or not old_due or not due:
        return
    delta = (_date.fromisoformat(due) - _date.fromisoformat(old_due)).days
    if delta == 0:
        return
    children_of: dict[str, list[dict]] = {}
    for x in w["tasks"]:
        for d in x["dependencies"]:
            children_of.setdefault(d, []).append(x)
    seen = {t["id"]}
    queue = deque([t["id"]])
    while queue:
        current = queue.popleft()
        for child in children_of.get(current, []):
            if child["id"] in seen:
                continue
            seen.add(child["id"])
            if not can_see(p, child) or (not admin and p["role"] != "Manager" and child["owner"] != p["id"]):
                raise Forbidden("You cannot shift a dependent task outside your editing permissions")
            if child["status"] in LOCKED:
                raise DomainError("A dependent task is in review or complete; move dates individually")
            for f in ("start", "due"):
                if child[f]:
                    try:
                        child[f] = (_date.fromisoformat(child[f]) + timedelta(days=delta)).isoformat()
                    except OverflowError:
                        raise DomainError("Shifted date is out of range") from None
            child["updated"] = at
            assert_task(w, child)
            unit = "day" if abs(delta) == 1 else "days"
            record(child, "Dates", f"Shifted {delta:+d} {unit} after {t['title']}")
            queue.append(child["id"])


def _apply_transition(w, p, edit, t, action, at, record):
    nxt = action.get("status")
    if nxt not in STAGES:
        raise DomainError("Unknown status")
    note = _text(action.get("note") or "", "Note")
    in_review = t["status"] == "In review"
    if in_review and nxt in ("Done", "Changes requested"):
        if t["reviewer"] != p["id"]:
            raise Forbidden("Only the assigned reviewer can decide")
        if nxt == "Changes requested" and not note:
            raise DomainError("Explain what needs changing")
    else:
        if not edit:
            raise Forbidden("Only the owner or a manager can move this task")
        if nxt == "Changes requested":
            raise DomainError("Changes are requested during review")
        if t["status"] == "Done" and nxt != "In progress":
            raise DomainError("Reopen a completed task to In progress")
        if in_review and nxt != "In progress":
            raise DomainError("Withdraw review to In progress")
        if nxt == "Done" and t["reviewRequired"]:
            raise DomainError("This task requires review first")
    if nxt in ("In progress", "In review", "Done"):
        prerequisites = set(t["dependencies"])
        if any(x["id"] in prerequisites and x["status"] != "Done" for x in w["tasks"]):
            raise DomainError("Finish prerequisite tasks first")
    if nxt in ("In review", "Done"):
        if any(not s["done"] for s in t["steps"]):
            raise DomainError("Complete all handover steps first")
        if nxt == "In review" and (not t["reviewRequired"] or not t["reviewer"]):
            raise DomainError("Configure a reviewer first")
        if t["reviewRequired"] and not t["evidence"].strip():
            raise DomainError("Add evidence or an output link before review")
    if nxt in ("Blocked", "Waiting") and not note:
        raise DomainError("Explain the blocker or what you are waiting for")
    frm = t["status"]
    t["status"] = nxt
    t["blockReason"] = note if nxt in ("Blocked", "Waiting") else ""
    t["completed"] = at if nxt == "Done" else ""
    record(t, "Status", note or f"{frm} → {nxt}", frm, nxt)


def _apply_import(w, admin, action, at, record):
    if not admin:
        raise Forbidden("Only administrators can import tasks")
    raw = action.get("tasks")
    if not isinstance(raw, list):
        raise DomainError("Nothing to import")
    if len(raw) > MAX_IMPORT:
        raise DomainError(f"Import at most {MAX_IMPORT} tasks at a time")
    incoming = [clean_task(r) for r in raw]
    if len(w["tasks"]) + len(incoming) > MAX_TASKS:
        raise DomainError("Workspace limit is 5,000 tasks")
    for t0 in incoming:
        # Imports always create fresh, untouched To do records.
        t = {
            **t0, "id": uid(), "status": "To do", "created": at, "updated": at, "completed": "",
            "blockReason": "", "dependencies": [],
            "steps": [{**s, "id": uid(), "done": False} for s in t0["steps"]],
        }
        assert_task(w, t)
        w["tasks"].append(t)
        record(t, "Imported", t["title"])
