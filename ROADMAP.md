# AloeDAV Roadmap

## Why this exists

AloeDAV serves two goals:

1. **An AI agent maintains a user's calendar, tasks and contacts** against a CalDAV/CardDAV
   server, while the *same user also syncs that data with an ordinary client* — Apple
   Calendar, DAVx5, Thunderbird, Outlook.
2. **AloeDAV can act as a server**, not only a client, so the same models and storage
   contract serve both ends of the wire.

Goal 1 is the demanding one, and it sets the project's first principle.

## First principle: never destroy what you do not understand

The agent is not the only writer. Every edit it makes is a read-modify-write against data
some other client authored, so any property the model fails to represent is a property the
agent silently deletes on the user's behalf. A calendar library that loses 5% of each event
per edit is worse than no library, because the loss is invisible until the user notices
their reminders are gone.

Concretely, this ranks **fidelity above features**. Support for a property is worth less
than *not corrupting* a property. And partial support is the worst state of all: dropping
`BYDAY` from an `RRULE` does not lose detail, it changes which days the event recurs on.

Two corollaries that govern design decisions below:

- Round-trip tests are the primary safety net, not unit tests of individual getters.
- Where the model cannot represent something, it must carry it verbatim rather than drop it.

---

## Status

| Phase | State |
|---|---|
| 0. Correctness floor | **Done** — `38ebfe8` |
| 1. Fidelity | **In progress** — `a7280f6` landed the parser half |
| 2. Time | Not started |
| 3. Agent ergonomics | Not started |
| 4. Protocol completeness (client) | Not started |
| 5. Server | Not started |
| 6. Breadth | Not started |

Test count: 13 → 81.

---

## Phase 0 — Correctness floor ✅

Landed in `38ebfe8`. The serialize path emitted malformed data and `RemoteCollection` had
five methods that could not execute. Details in the commit message. Summary:

- CRLF throughout; RFC 5545/6350 text escaping; 75-octet folding; full `ADR`; parameter quoting
- `format_dt` emits `Z` for aware datetimes; `parse_dt` no longer substitutes "now"
- `RemoteCollection._refresh` tuple assignments, `delete_item`, `get_item`, `list_items`, `get_or_create`
- Status checks before parsing REPORT/PROPFIND bodies (a 401 returned `[]`)
- Percent-encoded URL building; XML-escaped collection names; one timeout-bearing request helper
- Inverted ETag check in `LocalCollection.update_item`

---

## Phase 1 — Fidelity 🔶

**Goal: an agent edit changes exactly the field it meant to change.**

### Done (`a7280f6`)

- **Unmodelled components no longer crash.** `BEGIN:VTIMEZONE` raised `AssertionError`
  through its nested `DAYLIGHT`/`STANDARD` blocks, making every non-UTC event from a
  mainstream client unreadable. Unknown components are captured verbatim with depth
  tracking and re-emitted.
- **Unmodelled properties no longer vanish.** `_context_item` was an `elif` chain with no
  `else`; `CREATED`, `LAST-MODIFIED`, `GEO`, `RESOURCES`, `CONTACT` were dropped on rewrite.
  Now kept as verbatim source lines, so nothing is re-escaped.
- **RRULE is no longer corrupted.** All fourteen RECUR parts modelled; unrecognised parts
  kept verbatim; `SECONDLY`/`MINUTELY`/`HOURLY` added to `RecurrenceFrequency`.
- **Structural errors raise `ParseError`,** not `assert` (which `python -O` strips).

### Remaining

- [ ] **The resource model.** A CalDAV resource is a VCALENDAR that may hold several
      components sharing a UID — a recurring master plus `RECURRENCE-ID` overrides.
      `to_model` flattens to one model per component, so both collide on `{uid}.ics` and
      serializing either destroys the sibling. `EXDATE`/`RDATE`/`RECURRENCE-ID` are not
      modelled at all. **This is the highest-consequence remaining defect**: an agent that
      touches any recurring event with an exception destroys the series. *Design decision
      open — see below.* **Effort: L**
- [ ] **`VALARM` fidelity.** Only relative negative triggers (`-PT15M`) survive. No absolute
      triggers, no positive offsets, no `REPEAT`/`DURATION`, no `ATTENDEE` on EMAIL alarms,
      no `RELATED=END`. Alarms are the thing users notice losing. **Effort: M**
- [ ] **Inline `ATTACH`.** Only URL attachments round-trip; `ENCODING=BASE64` payloads are
      dropped. **Effort: S**
- [ ] **vCard structured values.** `N` has five components, only two are modelled;
      `ADR` PO-box and extended-address are written empty. **Effort: S**

---

## Phase 2 — Time

**Goal: the agent can reason about *when*, and does not shift the user's events.**

- [ ] **`TZID` and `VALUE=DATE`.** `DTSTART;TZID=America/New_York:20260301T090000` parses to
      a naive datetime — after Phase 1 the VTIMEZONE definition survives but the *reference*
      to it does not, so the event floats. Separately, an all-day event is indistinguishable
      from midnight. Both need the same change: a date-time value must carry its timezone
      reference and its DATE-vs-DATE-TIME nature. *Design decision open — see below.*
      **Effort: L**
- [ ] **Recurrence expansion.** Given a master plus overrides, produce concrete instances
      over a window. **The single highest-leverage item in this document**: the agent needs
      it to answer "what is on Thursday" or "move next week's standup", and a server needs
      it to evaluate `time-range` filters. One piece of work, both goals. **Effort: L**
- [ ] **Free/busy computation** over expanded instances, so the agent can answer "when am I
      free". Builds directly on the above. **Effort: M**

---

## Phase 3 — Agent ergonomics

**Goal: the agent's intent survives contact with the API.**

- [ ] **`update()` cannot clear a field.** Every subclass uses `if update.field:` truthiness,
      so an agent cannot remove a location, blank a description, or set a priority to 0.
      Verified: all three are silently ignored. pydantic v2's `model_fields_set` gives the
      exact answer — apply precisely the fields the caller set — which also replaces ~90
      lines of hand-written checks across four files with one generic implementation.
      *Semantic change to a public method; needs sign-off.* **Effort: S**
- [ ] **Conflict handling.** `PreconditionFailed` is raised but there is no re-read-and-merge
      helper, so every caller reimplements the 412 dance. **Effort: M**
- [ ] **Idempotency.** Nothing stops an agent double-creating on retry; `upsert_object` does
      not distinguish create from update (`If-None-Match: *`). **Effort: S**
- [ ] **Query ergonomics.** `list_calendar_objects(start, end)` is the only filter. No "find
      by UID", no text search, no "tasks due this week". **Effort: M**

---

## Phase 4 — Protocol completeness (client)

- [ ] **Discovery.** No `.well-known/caldav`, `current-user-principal`, or home-set lookup —
      the caller must know its collection URLs. Required for anything but a hardcoded server.
      **Effort: M**
- [ ] **`calendar-multiget` / `addressbook-multiget`.** Currently N round trips where one
      would do. **Effort: S**
- [ ] **ctag fast path.** `get_ctag` exists and nothing uses it; every poll is a full sync.
      **Effort: S**
- [ ] **`sync-collection` edge cases.** No handling for 507 truncation (requires continuing)
      or an invalid token (requires full resync). **Effort: M**
- [ ] **Auth and transport.** Basic only — Google and Fastmail need OAuth2 bearer. No
      `requests.Session`, so no connection reuse. No retry/backoff. **Effort: M**
- [ ] **`PROPPATCH`.** Entirely absent; cannot rename a collection. **Effort: S**

---

## Phase 5 — Server

**The architecture already supports this.** `Collection` is the seam: `RemoteCollection`
turns Collection calls into HTTP requests; a server turns HTTP requests into Collection
calls. `LocalCollection.sync_table` is already a server-side RFC 6578 change log.

A payoff beyond the feature: `client → HTTP → server → LocalCollection` runs in-process,
and most of the Phase 0 bugs would have died instantly against that loop.

- [ ] **Multistatus generation** — the mirror of `client_util`'s getters. **Effort: M**
- [ ] **`PROPFIND` request parsing**, Depth 0/1, 200/404 propstat split. **Effort: M**
- [ ] **Discovery endpoints** — principal, home-sets, `.well-known`, `supported-report-set`.
      Small, but the most common reason a homegrown CalDAV server has no clients: get it
      wrong and nothing connects, with no useful error. **Effort: M**
- [ ] **`OPTIONS`** advertising `DAV: 1, 2, 3, calendar-access, addressbook`. **Effort: S**
- [ ] **`calendar-query` evaluation.** `comp-filter` is cheap; `time-range` depends on Phase 2
      recurrence expansion. *Scoping note: evaluating `comp-filter` and ignoring `time-range`
      returns a superset. Over-returning is non-conformant but harmless — clients re-filter
      locally. Under-returning is broken. This defers recurrence expansion out of v1.*
      **Effort: L**
- [ ] **`PROPPATCH` dead-property storage.** **Effort: M**
- [ ] **`LOCK`/`UNLOCK`** — only needed if serving file DAV, not for CalDAV. **Effort: M**

**Open scoping question:** single-user local server (for the agent) or multi-user with auth
and ACL? The former is a fraction of the work.

---

## Phase 6 — Breadth

- [ ] **vCard 4.0** (RFC 6350). Version 3.0 is hardcoded; modern CardDAV servers prefer 4.0.
      `PREF` semantics differ (`TYPE=PREF` vs `PREF=1`). **Effort: M**
- [ ] **Missing vCard properties**: `PHOTO`, `BDAY`, `ANNIVERSARY`, `IMPP`, `KIND`
      (person vs org), `MEMBER` (contact groups), `RELATED`, `TZ`, `GEO`, `ROLE`. **Effort: M**
- [ ] **`VFREEBUSY` / `VAVAILABILITY`** components. **Effort: M**
- [ ] **Scheduling (RFC 6638)** — inbox/outbox, iTIP. This is what makes *invitations* work;
      required if the agent should ever accept a meeting on the user's behalf. **Effort: L**

---

## Open design decisions

These need a call before the work they gate can start.

### D1 — Resource model (gates Phase 1, and Phase 5's storage layer)

How to represent a VCALENDAR holding a recurring master plus its `RECURRENCE-ID` overrides.
Three candidates:

- **Wrapper** — a new `VCalendarResource` owning `list[Item]`, becoming the unit of GET/PUT.
- **Master-owns** — `VEVENT.overrides: list[VEVENT]`; `to_model` returns one model per UID.
- **Raw-preserving** — model the component tree *plus* the original lines, and patch the tree
  rather than regenerate it, guaranteeing byte-level preservation.

*Being evaluated by a design panel; recommendation to follow.*

### D2 — Date-time representation (gates Phase 2)

A calendar date-time is one of three things: a UTC instant, a floating local time, or a
zoned wall-clock time (`TZID`) — plus DATE-only for all-day. Modelling all four as a bare
`datetime` cannot work. Options range from a `CalDateTime` value type (correct, wide blast
radius on every caller comparing `event.dtstart`) to carrying the original parameters
alongside for faithful *writing* without fixing *interpretation* (cheap, half a fix).

### D3 — `update()` semantics (gates Phase 3)

Switching to `model_fields_set` is the clean fix but changes behaviour for any caller that
passes a fully-populated object expecting only truthy fields to apply.

### D4 — Server scope (gates Phase 5)

Single-user local, or multi-user with auth and ACL?

---

## Housekeeping

- [ ] `src/client_test.py` — 687 stale lines importing modules that no longer exist
      (`aloedav.model.vcard`, `VCard`, `AloeDAV`). Breaks `pytest src`. Delete or archive.
- [ ] `README.md` is empty.
- [ ] No CI. The test suite is fast and would run on every push.
- [ ] Module-level `logging.info/error` rather than a named logger.

## Non-goals

- Being a general-purpose iCalendar library. Fidelity for the sync path is the target.
- A calendar UI.
- Timezone *database* maintenance — defer to the system tz data rather than parsing
  VTIMEZONE rules for offset computation (preserving them verbatim is enough).
