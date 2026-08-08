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
| 1. Fidelity | **In progress** — parser (`a7280f6`) and resource model landed; VALARM/ATTACH/vCard structured values remain |
| 2. Time | **In progress** — date-time representation landed; expansion and free/busy remain |
| 3. Agent ergonomics | Not started |
| 4. Protocol completeness (client) | Not started |
| 5. Server | Not started |
| 6. Breadth | Not started |

Test count: 13 → 146.

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

- [x] **The resource model.** `VCalendarResource`/`VCardResource` in `m01_resource.py` are
      now the unit of GET/PUT/ETag/filename, so a recurring master and its `RECURRENCE-ID`
      overrides share one resource instead of colliding on `{uid}.ics` and overwriting each
      other. `RECURRENCE-ID` is parsed (it was not, so master and override were
      indistinguishable) and serialized by VEVENT/VTODO as well as VJOURNAL. `to_model()`
      still returns `list[Item]` as a compatibility view; `to_resource()` and
      `client.fetch_resource()` are the safe path when the result will be written back.
      `EXDATE`/`RDATE` were round-tripping verbatim here and are now modelled (see Phase 2).
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

- [x] **`TZID` and `VALUE=DATE`.** `DateTimeValue` in `m00_datetime.py` carries the wall-clock
      time, which of the four RFC 5545 forms it is (DATE / FLOATING / UTC / ZONED), and the
      TZID parameter *verbatim*. Applied to DTSTART, DTEND, DUE, RECURRENCE-ID and RRULE's
      UNTIL; DTSTAMP and COMPLETED stay plain datetimes, being UTC-only by RFC. `EXDATE` and
      `RDATE` are now modelled as value lists (a `VALUE=PERIOD` RDATE stays verbatim, being a
      range rather than a date-time). Plain `datetime`/`date` remain valid input via a
      coercing validator, so only *reading* changed. Zone resolution is a separate
      best-effort layer — `aware()`/`to_utc()` return None rather than guess when a TZID
      cannot be resolved.
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

### D1 — Resource model — **decided: wrapper + compatibility shim** ✅

Implemented. The deciding evidence against "master owns its overrides" was `TEST_VCALENDAR_MIXED`,
which carries two UIDs and two component types in one VCALENDAR — non-conformant as a CalDAV
resource (RFC 4791 4.1) but valid as an `.ics` file, and a client must read it rather than
reject it. A master-owns model cannot represent it; a resource wrapper can.

Revisit if the extra indirection proves annoying in practice — `to_model()` was kept as the
flat view specifically so the wrapper can stay out of the way for single-component resources.

### D2 — Date-time representation — **decided: `DateTimeValue`, storing wall time + verbatim TZID** ✅

Implemented. The blast radius turned out to be small: a `mode="before"` validator accepts
plain `datetime`, `date` and wire strings, and `__eq__` compares against `datetime`, so
construction and most assertions are unchanged. Two tests reached into datetime internals
(`.tzinfo`, `.year`) and now state their intent more precisely.

The load-bearing choice is storing **naive wall time plus the TZID string verbatim**, rather
than resolving to an aware datetime at parse time. Outlook emits TZIDs defined only by the
VTIMEZONE block inside the same file; resolving-then-reserializing would rewrite that
reference and break it against the VTIMEZONE Phase 1 preserved. Storing what was on the wire
round-trips regardless of whether this machine has ever heard of the zone.

Open follow-on: resolving a TZID against the file's *own* VTIMEZONE, which would make
Outlook-style custom zones computable rather than merely preserved.

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
