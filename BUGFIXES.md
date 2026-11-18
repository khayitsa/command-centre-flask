# Bugs found and fixed

The original six domain tests all passed, so these lived in paths the tests did not reach.
"Confirmed" means reproduced against the original code (a probe run of `lib/work.ts` or a
real-browser run of the new build). Each fix has a regression test in `tests/` unless it is
UI-only (those were exercised in a real browser).

## Rules and permissions (server)

| # | Bug | Effect | Fix |
|---|---|---|---|
| 1 | Saving a task took `blockReason` from the browser | A Blocked task's reason could be wiped (Blocked with no reason), or a reason forged on a task that isn't blocked. *Confirmed.* | Server owns `blockReason`; only status changes set it. |
| 2 | The browser only receives prerequisites the user may see, but saving replaced the whole list | A restricted manager editing any task silently deleted prerequisites they couldn't see; they could also add ones they couldn't see. *Confirmed.* | Hidden prerequisites are preserved on save; adding hidden ones is refused. |
| 3 | Dates of Done / In-review tasks could be moved (Gantt bar) | Broke the rule that reviewed/completed work is frozen until reopened. *Confirmed.* | Refused with a clear message; the Gantt explains instead of opening the dialog. |
| 4 | "Shift dependants" with a 0-day change | Wrote "Shifted 0 days" history events for every dependant. *Confirmed.* | No-op shifts record nothing; messages read "Shifted +1 day". |
| 5 | Scoped (non-admin) workspace copy blanked the user's own access scope and omitted the person a task is "waiting on" | UI showed "Waiting on Unassigned". *Confirmed.* | Own scope kept; waiting-on person included. |
| 6 | Non-admins received admin "Access"/"Structure" events | Leaked names of people the member is not allowed to see. | Task-less events are admin-only. |
| 7 | CSV/JSON import kept `blockReason` and `done` step flags from the payload | An admin import could create tasks with forged block reasons or pre-completed handover steps. | Import resets both and gives steps new ids. |
| 8 | Validation errors were raw zod JSON blobs; emails weren't trimmed/lower-cased | Unreadable messages; `Pat@X.com` vs `pat@x.com` handled inconsistently. | Readable messages; emails normalised. |
| 9 | API status codes and parsing | Not-signed-in and bad JSON returned 403; `Content-Type: application/json; charset=utf-8` was rejected; a missing `action` crashed with a TypeError message. | 401/404/409/413 as appropriate, JSON errors everywhere, tolerant content type. |
| 10 | An empty `ownerId` in a scoped copy would match an empty actor id | Latent impersonation hazard. | `member()` never matches an empty id. |
| 11 | Dependency cycle check re-walked shared sub-graphs | Exponential time on dense graphs. | Linear-time check. |

## Interface

| # | Bug | Fix |
|---|---|---|
| 12 | Companies cards were labelled "Companie" (`slice(0,-1)` on "Companies") *Confirmed* | Proper labels. |
| 13 | **My work → Export CSV** exported every filtered task, not the ones listed *Confirmed* | Exports exactly what the heading counts. |
| 14 | CSV import could not resolve a project name used in two companies *Confirmed* | Projects are matched within the row's company. |
| 15 | Export → import corrupted text starting with `= + - @` (an apostrophe guard was added on export but never removed on import); the guard also missed tab/CR *Confirmed* | Import strips the guard; export covers tab/CR. |
| 16 | Reports silently applied the Status filter chosen in another view, with no control to clear it *Confirmed* | Reports ignore the status filter. |
| 17 | A task dialog stayed open and blank if the task disappeared after a refresh | Dialog closes. |
| 18 | `showModal()` on an already-open dialog (detail → edit) | Guarded. |
| 19 | Date inputs were controlled with `onInput` (React warning); milestone due date wasn't kept equal to its start, so saving failed server-side *Confirmed* | `onChange`; milestones mirror start (due is locked), also in "Move dates". |
| 20 | `crypto.randomUUID()` is missing on plain-http (e.g. LAN) pages, so creating tasks/steps/people threw | Safe UUID fallback. |
| 21 | Creating a new workspace kept the old workspace's filters/selection, so it looked empty | State reset. |
| 22 | A stale write (409) needed a manual refresh | Auto-refreshes and explains. *Confirmed* |
| 23 | CSV download link wasn't attached to the page (Firefox) | Attached. |
| 24 | Estimated-hours totals could show float noise (0.1 + 0.2) | Rounded. |

## New in the Flask edition

Email/password sign-in and sign-out (the sign-out button lives in the header so it works on
phones), same-origin CSRF checks, session cookies (HttpOnly, SameSite=Lax, Secure by default),
a Content-Security-Policy, login throttling (per process), and SQLite with an atomic
compare-and-swap on the revision.

## Judgement calls you may want to reverse

* Rescheduling a Done/In-review task is now refused (#3). The README of the original says such
  tasks must be reopened before content changes; dates were the exception only by accident.
* Non-admins no longer see structure/access events (#6).
* Reopening a Done task whose prerequisite was later reopened is still refused (unchanged).

## Not verified

Run in Chromium and with pytest only: not Firefox/Safari, and not on PythonAnywhere itself.
